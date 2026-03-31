from fastapi.templating import Jinja2Templates
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

templates.env.globals["get_csrf_token"] = get_csrf_token
