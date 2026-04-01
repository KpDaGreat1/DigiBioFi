from fastapi.templating import Jinja2Templates
from fastapi import Request
import time
from itsdangerous import URLSafeSerializer
from app.core.config import settings

templates = Jinja2Templates(directory="app/templates")

csrf_serializer = URLSafeSerializer(settings.csrf_secret_key)

def get_csrf_token(request) -> str:
    token = request.cookies.get("csrf_token")
    if not token:
        # Fallback for templates if cookie not yet set
        token = csrf_serializer.dumps(time.time())
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
    return request.session.pop("flash", [])

templates.env.globals["get_csrf_token"] = get_csrf_token
templates.env.globals["get_flashed_messages"] = get_flashed_messages
