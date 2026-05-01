"""Resume extraction helpers for staged AI-assisted profile prefill."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.resume_ai import ResumeInfo
from app.utils.validators import validate_pdf_upload

logger = logging.getLogger(__name__)


class ResumeAIUnavailable(Exception):
    """Raised when AI resume extraction is unavailable."""


class ResumeAIExtractionError(Exception):
    """Raised when extraction fails safely."""


def is_resume_ai_available() -> bool:
    if not settings.gemini_api_key.strip():
        return False
    try:
        import google.genai  # noqa: F401
        import pymupdf4llm  # noqa: F401
    except Exception:
        return False
    return True


def _verify_pdf(upload: UploadFile) -> None:
    validate_pdf_upload(upload)
    upload.file.seek(0)
    signature = upload.file.read(5)
    upload.file.seek(0)
    if signature != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume must be a valid PDF file.",
        )


def _extract_markdown(upload: UploadFile) -> str:
    try:
        import pymupdf4llm
    except Exception as exc:
        raise ResumeAIUnavailable("AI resume extraction dependencies are not installed.") from exc

    suffix = Path(upload.filename or "resume.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        upload.file.seek(0)
        temp_file.write(upload.file.read())
        temp_path = temp_file.name

    try:
        markdown = pymupdf4llm.to_markdown(temp_path)
    except Exception as exc:
        raise ResumeAIExtractionError("We couldn't read that PDF. Try a cleaner exported resume.") from exc
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to delete temporary resume file: %s", temp_path)

    if not markdown or not markdown.strip():
        raise ResumeAIExtractionError("The uploaded PDF did not contain readable resume text.")

    return markdown[:120_000]


def _generate_resume_info(markdown: str) -> ResumeInfo:
    if not settings.gemini_api_key.strip():
        raise ResumeAIUnavailable("AI resume extraction is not configured.")

    try:
        from google import genai
    except Exception as exc:
        raise ResumeAIUnavailable("AI resume extraction dependencies are not installed.") from exc

    prompt = (
        "Extract resume information into structured JSON for a professional profile editor.\n"
        "Only include facts clearly supported by the resume text.\n"
        "Do not invent employers, dates, links, metrics, or credentials.\n"
        "Keep summaries concise and professional.\n"
        "Return empty strings or empty arrays when information is missing.\n\n"
        f"Resume Markdown:\n{markdown}"
    )

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": ResumeInfo,
        },
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, ResumeInfo):
        return parsed

    if parsed:
        return ResumeInfo.model_validate(parsed)

    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise ResumeAIExtractionError("The AI response was empty.")

    try:
        return ResumeInfo.model_validate_json(text)
    except Exception:
        return ResumeInfo.model_validate(json.loads(text))


def extract_resume_info(upload: UploadFile) -> ResumeInfo:
    _verify_pdf(upload)
    markdown = _extract_markdown(upload)
    try:
        return _generate_resume_info(markdown)
    except ResumeAIUnavailable:
        raise
    except ResumeAIExtractionError:
        raise
    except Exception as exc:
        logger.exception("Resume AI extraction failed")
        raise ResumeAIExtractionError(
            "We couldn't analyze that resume right now. Please try again later."
        ) from exc
