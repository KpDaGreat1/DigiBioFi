# DigiBioFi — Secret Cleanup & Branch Sanitization Report

**Date:** 2026-05-04  
**Engineer:** Claude (Senior Git Security Engineer / Release Manager)  
**Repo:** https://github.com/KpDaGreat1/DigiBioFi  
**Status at close:** CLEAN — SAFE TO PROCEED (pending key rotation and VPS reclone)

---

## 1. Secrets Discovered

### Primary Incident — `.env` committed to early history

The file `.env` was committed in 3 early commits and then deleted in a later cleanup commit.
Deletion from the file tree does NOT remove secrets from git history — the objects remained readable.

| Commit | Subject | Secret Exposure |
|---|---|---|
| `9196c64` | Stabilize DigiBioFi app | LIVE `STRIPE_SECRET_KEY`, LIVE `STRIPE_WEBHOOK_SECRET`, LIVE `STRIPE_PUBLISHABLE_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY` |
| `f09fe9d` | Security improvements: Phase 2 | `SECRET_KEY`, `ADMIN_PASSWORD` |
| `f8e5c54` | Security & UX Phase 1 | `SECRET_KEY`, `ADMIN_PASSWORD` |

These commits were in the shared ancestry of `main`, `dev`, and `main-v1`. They were visible to anyone with read access to the GitHub repo.

### Secondary Incident — `gen_verify_token.py` on `origin/main-v1`

| Commit | Branch | Content |
|---|---|---|
| `33b80b2` | `origin/main-v1` only | Hardcoded `SECRET_KEY` (production JWT signing key), test user `id=3`, email `testuser_20260430@example.com` |

This commit existed only on `origin/main-v1`. It was never merged into `main` or `dev`. Eliminated by deleting `origin/main-v1`.

### Tertiary — `digibiofi.db` committed alongside `.env`

The SQLite database was committed in the same 3 commits as `.env`. This file contained live user data. Purged from history along with `.env`.

---

## 2. Keys Requiring Rotation

> **These must be rotated BEFORE considering the system secure.**
> Even after history rewrite, old objects may persist in GitHub's object store until GC runs.
> Any repository clone created before the rewrite retains the old history.

| Key | Risk Level | Action Required |
|---|---|---|
| `STRIPE_SECRET_KEY` (sk_live_**REDACTED**) | CRITICAL | Roll in Stripe Dashboard → API Keys |
| `STRIPE_WEBHOOK_SECRET` (whsec_**REDACTED**) | CRITICAL | Delete endpoint & recreate in Stripe Dashboard → Webhooks |
| `STRIPE_PUBLISHABLE_KEY` (pk_live_**REDACTED**) | HIGH | Roll in Stripe Dashboard → API Keys |
| `SECRET_KEY` / JWT signing secret | HIGH | Regenerate: `python3 -c "import secrets; print(secrets.token_hex(32))"` — invalidates all user sessions |
| `CSRF_SECRET_KEY` | HIGH | Regenerate same as SECRET_KEY |
| `ADMIN_PASSWORD` (**REDACTED**) | HIGH | Change in `.env` and DB immediately |
| `SECRET_KEY` in `gen_verify_token.py` (**REDACTED**) | HIGH | Same as SECRET_KEY above — same key |
| SMTP password | MEDIUM | Verify in production `.env`, rotate as precaution |
| Gemini/Google API key | MEDIUM | Check if in use, rotate via Google Cloud Console |

**Stripe key rotation sequence:**
1. Stripe Dashboard → Developers → API Keys → "Roll key" on the secret key
2. Update `.env` on VPS with new key
3. Stripe Dashboard → Developers → Webhooks → delete old endpoint → create new → copy new `whsec_`
4. Update `STRIPE_WEBHOOK_SECRET` in VPS `.env`
5. `docker compose restart` (or full rebuild)

---

## 3. Files Removed from History

`git filter-repo` was run with `--invert-paths` on the following paths, rewriting all 38 commits:

| Path | Reason |
|---|---|
| `.env` | Contained LIVE Stripe keys, admin password |
| `digibiofi.db` | Live SQLite database with user data |
| `.idea/` | IDE project files (was already in gitignore) |
| `qr_codes/` | QR code images committed at root (already in gitignore) |

Additionally, `gen_verify_token.py` was eliminated by **deleting `origin/main-v1`** (the only branch that contained it). The file was never in `main` or `dev`.

---

## 4. Branch Comparison Results

**Before rewrite:**
```
main:         743765e76ef755...  (38 commits)
dev:          743765e76ef755...  (38 commits, identical to main)
origin/main-v1: 30a6f25...      (includes secret commit 33b80b2)
```

**After rewrite:**
```
main:         712d0fb  (38 commits, history rewritten — .env/DB purged)
dev:          712d0fb  (identical to main)
origin/main-v1: DELETED
```

`git diff main dev` → empty  
`git log main..dev` → empty  
`git log dev..main` → empty  

---

## 5. Confirmation: main == dev

```
main:  712d0fb  security: harden .gitignore with key/cert/secrets patterns
dev:   712d0fb  security: harden .gitignore with key/cert/secrets patterns
```

**CONFIRMED IDENTICAL.**

---

## 6. Confirmation: main-v1 Deleted

```
git push origin --delete main-v1
→ - [deleted]         main-v1
```

**Remote `origin/main-v1` DELETED.**  
Local `main-v1` branch also deleted.  
Final remote branches: `origin/main`, `origin/dev` only.

---

## 7. .gitignore Updates

Added to `# DigiBioFi specific ignores (critical)` section:

```gitignore
*.pem
*.key
*.crt
*.p12
*.pfx
secrets/
credentials/
```

Pre-existing protections (already in `.gitignore` before this pass):
- `.env`, `.env.*`, `!.env.example`
- `*.db`, `*.sqlite`, `*.sqlite3`
- `.idea/`
- `uploads/`, `qr_codes/`
- `.venv/`, `venv/`

---

## 8. .env.example Status

**CLEAN.** No real secrets. All values are placeholders:

```
SECRET_KEY=CHANGE-ME-generate-a-64-char-hex-string-with-secrets-token-hex
STRIPE_SECRET_KEY=sk_test_REPLACE_WITH_REAL_KEY
STRIPE_WEBHOOK_SECRET=whsec_...
ADMIN_PASSWORD=CHANGE-ME
```

`.env.example` is safe to commit and remain in version control.

---

## 9. Force-Push Status

```
git push origin --force main dev
→ + 743765e...4ed62d9 main -> main (forced update)
→ + 743765e...4ed62d9 dev -> dev (forced update)

git push origin main   (gitignore commit)
→ 4ed62d9..712d0fb main -> main

git push origin dev    (fast-forward)
→ 4ed62d9..712d0fb dev -> dev
```

All pushes succeeded. Remote history is now the clean rewritten history.

---

## 10. Required VPS Reclone Steps

**The VPS is currently running the old (contaminated) history clone. It must be replaced.**

```bash
# SSH into VPS, then:

# 1. Stop the running application
cd ~/apps/DigiBioFi   # adjust to your actual path
docker compose down --remove-orphans

# 2. Move old clone aside (do NOT delete yet — keep until new clone is verified)
cd ~/apps
mv DigiBioFi DigiBioFi_OLD_COMPROMISED_$(date +%Y%m%d)

# 3. Fresh clone from rewritten main
git clone -b main https://github.com/KpDaGreat1/DigiBioFi.git
cd DigiBioFi

# 4. Recreate .env manually with ROTATED keys
cp .env.example .env
nano .env   # or vim/vi
# Fill in all values — use NEW rotated Stripe keys, new SECRET_KEY, new CSRF_SECRET_KEY

# 5. Verify the clone does NOT contain old secrets
git log --oneline -5    # SHAs should start with 712d0fb or earlier rewritten SHAs
git show HEAD -- .env   # Should show: error: path '.env' is not in 'HEAD'

# 6. Rebuild Docker with no cache
docker compose build --no-cache
docker compose up -d

# 7. Run migrations
docker compose exec web alembic upgrade head

# 8. Health check
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# 9. After verifying new clone works, delete old backup
# rm -rf ~/apps/DigiBioFi_OLD_COMPROMISED_*
```

**Also:** Contact GitHub Support to request immediate purge of orphaned git objects containing the old `.env`. While the branch references are gone, GitHub's object store may retain orphaned blobs until GC runs (typically within 90 days). Use the GitHub contact form → "Security" category.

---

## 11. Final Verdict

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CLEAN — SAFE TO PROCEED
  (pending key rotation and VPS reclone)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Completed:**
- [x] `.env` purged from all 38 commits in history
- [x] `digibiofi.db` purged from all 38 commits in history
- [x] `gen_verify_token.py` eliminated (via `origin/main-v1` deletion)
- [x] `origin/main-v1` deleted — no more legacy branch
- [x] Clean history force-pushed to `origin/main` and `origin/dev`
- [x] `main == dev` confirmed at `712d0fb`
- [x] App imports cleanly — 116 routes verified
- [x] Current working tree scanned — no real secrets found
- [x] Full history scanned — no Stripe keys, no admin password found
- [x] `.gitignore` hardened with cert/key/secrets patterns
- [x] `.env.example` confirmed clean (placeholders only)

**Remaining (your action required):**
- [ ] Rotate STRIPE_SECRET_KEY (LIVE — highest priority)
- [ ] Rotate STRIPE_WEBHOOK_SECRET (LIVE)
- [ ] Rotate STRIPE_PUBLISHABLE_KEY
- [ ] Regenerate SECRET_KEY and CSRF_SECRET_KEY
- [ ] Change ADMIN_PASSWORD
- [ ] Reclone repo on VPS with new .env
- [ ] Contact GitHub Support for immediate object purge
