from fastapi.templating import Jinja2Templates
from fastapi import Request
from app.core.security import generate_csrf_token

templates = Jinja2Templates(directory="app/templates")

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
