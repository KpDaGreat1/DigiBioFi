from fastapi.templating import Jinja2Templates
from fastapi import Request
from app.core.security import generate_csrf_token
from app.core.config import settings

templates = Jinja2Templates(directory="app/templates")


def role_badge_meta(role: str | None) -> dict[str, str]:
    normalized = (role or "user").strip().lower()
    styles = {
        "admin": {
            "label": "Admin",
            "class_name": "bg-violet-500/15 text-violet-200 border border-violet-400/30",
        },
        "business": {
            "label": "Business",
            "class_name": "bg-blue-500/15 text-blue-200 border border-blue-400/30",
        },
        "freelancer": {
            "label": "Freelancer",
            "class_name": "bg-emerald-500/15 text-emerald-200 border border-emerald-400/30",
        },
        "user": {
            "label": "User",
            "class_name": "bg-slate-500/15 text-slate-200 border border-slate-400/20",
        },
    }
    return styles.get(normalized, styles["user"])

def get_csrf_token(request: Request) -> str:
    token = request.cookies.get("csrf_token")
    if not token:
        token = getattr(request.state, "csrf_token", None)
    if not token:
        token = generate_csrf_token(request)
        request.state.csrf_token = token
    return token

def flash(request: Request, message: str, category: str = "info"):
    """
    Store a flash message in the session.
    Requires SessionMiddleware to be enabled in main.py.
    """
    if "flash" not in request.session:
        request.session["flash"] = []
    request.session["flash"].append({"message": message, "category": category})

def get_flashed_messages(request: Request):
    """
    Retrieve and clear all flash messages from the session.
    """
    messages = request.session.pop("flash", []); print(f"FLASH MESSAGES IN TEMPLATE: {messages}"); return messages

templates.env.globals["get_csrf_token"] = get_csrf_token
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals["adsense_client_id"] = settings.adsense_client_id
templates.env.globals["adsense_public_inline_slot"] = settings.adsense_public_inline_slot
templates.env.globals["adsense_public_sidebar_slot"] = settings.adsense_public_sidebar_slot
templates.env.globals["adsense_dashboard_slot"] = settings.adsense_dashboard_slot
templates.env.globals["base_url"] = settings.base_url
templates.env.globals["role_badge_meta"] = role_badge_meta
