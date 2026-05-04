"""
Development runner — start the app with hot-reload.

Usage:
    python run.py

Or directly:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""
import os

import uvicorn

if __name__ == "__main__":
    os.environ["APP_ENV"] = os.environ.get("APP_ENV", "development")
    if os.environ["APP_ENV"] == "development":
        os.environ.setdefault("DEBUG", "true")
        os.environ.setdefault("BASE_URL", "http://127.0.0.1:8000")
        os.environ.setdefault("TRUST_PROXY_HEADERS", "false")
        os.environ.setdefault("SECURE_COOKIES", "false")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        log_level="info",
    )
