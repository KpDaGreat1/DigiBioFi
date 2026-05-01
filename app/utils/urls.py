"""Helpers for generating stable external URLs behind reverse proxies."""

from fastapi import Request


def external_base_url(request: Request) -> str:
    from app.core.config import settings

    if not settings.use_proxy_headers:
        return str(request.base_url).rstrip("/")

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
    forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip()

    if forwarded_host:
        scheme = forwarded_proto or request.url.scheme
        return f"{scheme}://{forwarded_host}".rstrip("/")

    return str(request.base_url).rstrip("/")
