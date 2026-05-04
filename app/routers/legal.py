"""Static legal pages."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.core.dependencies import get_current_user_optional
from app.core.templates import templates

router = APIRouter(tags=["legal"])


@router.get("/privacy", response_class=HTMLResponse)
def privacy(
    request: Request,
    user=Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        request=request, name="legal/privacy.html", context={"request": request, "user": user},
    )


@router.get("/terms", response_class=HTMLResponse)
def terms(
    request: Request,
    user=Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        request=request, name="legal/terms.html", context={"request": request, "user": user},
    )
