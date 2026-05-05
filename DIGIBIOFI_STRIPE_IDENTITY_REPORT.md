# DigiBioFi — Stripe Identity Implementation Report
**Date:** 2026-05-05

---

## Architecture

Stripe Identity is implemented webhook-first. No verification state is set except by the verified Stripe webhook event.

### Endpoint: `POST /dashboard/verify/create-session`
- Auth: `get_current_user` (session cookie required)
- CSRF: required
- Behavior:
  1. Returns 400 if `user.is_verified == True`
  2. Returns 503 if `STRIPE_SECRET_KEY` not set
  3. Calls `stripe.identity.VerificationSession.create(type="document", metadata={"user_id": str(user.id)})`
  4. Stores `session_id` on `users.stripe_verification_id`
  5. Sets `users.verification_status = "requires_input"`
  6. Returns `{"client_secret": "<stripe_client_secret>"}`

### Stripe.js Flow (Frontend)
1. User clicks "Verify My Identity" in `/settings`
2. JS calls `POST /dashboard/verify/create-session` with CSRF token
3. On success, calls `stripe.verifyIdentity(client_secret)` — opens Stripe hosted modal
4. User completes document + selfie flow within Stripe modal
5. Frontend shows "Pending Review…" — all final state comes from webhook

### Webhook Handler: `POST /webhook/stripe`

Same endpoint as billing webhooks. Events handled:

| Event | Action |
|-------|--------|
| `identity.verification_session.verified` | `is_verified = True`, `verification_status = verified`, creates Notification |
| `identity.verification_session.requires_input` | `verification_status = requires_input`, creates Notification with reason |
| `identity.verification_session.canceled` | `verification_status = canceled` |

**User Lookup Order:**
1. `metadata.user_id` from session metadata
2. Fallback: `users.stripe_verification_id == session_id`

**Idempotency:** All events deduplicated via `StripeEvent.event_id`.

---

## Database Schema

```sql
-- New columns on users table
stripe_verification_id  VARCHAR(200) NOT NULL DEFAULT ''
verification_status     VARCHAR(30)  NOT NULL DEFAULT ''
-- Valid values: '' | 'requires_input' | 'processing' | 'verified' | 'canceled' | 'failed'

-- New table
CREATE TABLE notifications (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    type       VARCHAR(30) NOT NULL DEFAULT 'system',
    title      VARCHAR(200) NOT NULL,
    body       TEXT NOT NULL DEFAULT '',
    link       VARCHAR(500) NOT NULL DEFAULT '',
    is_read    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Security Properties

| Property | Status |
|----------|--------|
| Stripe keys ENV-only | ✅ |
| Webhook signature verified | ✅ (`stripe.Webhook.construct_event`) |
| CSRF on session creation | ✅ |
| No PII stored on DigiBioFi | ✅ |
| No replay attacks | ✅ (StripeEvent dedup) |
| No shortcut verification | ✅ (webhook-only state change) |
| Auth required for session creation | ✅ |

---

## Testing

### Stripe CLI Test
```bash
# Test verified flow
stripe trigger identity.verification_session.verified \
  --override 'identity.verification_session:metadata.user_id=1'

# Test requires_input flow
stripe trigger identity.verification_session.requires_input \
  --override 'identity.verification_session:metadata.user_id=1'

# Test canceled flow
stripe trigger identity.verification_session.canceled \
  --override 'identity.verification_session:metadata.user_id=1'
```

### Expected Results After `verified` Event
- `users.is_verified = TRUE`
- `users.verification_status = 'verified'`
- Notification created: type=`verification`, title=`Identity Verified`
- Verified badge visible on `/p/<slug>`
- `/explore?filter=verified` includes user's profile
- Settings page shows green "Identity Verified" confirmation

---

## Files Changed

| File | Change |
|------|--------|
| `app/models/user.py` | +`stripe_verification_id`, +`verification_status` |
| `app/models/notification.py` | New file — Notification model |
| `app/models/__init__.py` | Import Notification |
| `app/services/stripe_service.py` | +`create_verification_session()` |
| `app/routers/dashboard.py` | +`/verify/create-session`, +`/verify/status`, +notifications routes |
| `app/main.py` | +identity webhook event handlers |
| `alembic/versions/g1a2b3c4d5e6_*.py` | Migration: identity fields + notifications table |
| `app/templates/dashboard/settings.html` | Verify Identity UI section + Stripe.js |
| `app/templates/dashboard/notifications.html` | New notifications page |
| `app/templates/layouts/dashboard.html` | Bell icon wired + Notifications nav item |
| `app/templates/dashboard/_nav.html` | Notifications mobile nav item |
| `app/routers/pages.py` | Explore filter support (verified, recruiter, freelance, elite) |
| `app/templates/pages/explore.html` | Filter chips + profile badges |

---

## Webhook Validation Proof

The existing `POST /webhook/stripe` endpoint (line ~712 of `app/main.py`) performs:

```python
event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
```

This validates the `Stripe-Signature` header using HMAC-SHA256 with the configured `STRIPE_WEBHOOK_SECRET`. Invalid signatures raise `stripe.error.SignatureVerificationError` → returns `400 invalid`.

No identity verification state change can occur without a cryptographically verified Stripe webhook delivery.
