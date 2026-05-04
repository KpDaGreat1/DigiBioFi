import json
import logging

import fitz  # PyMuPDF
from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        logger.error(f"Failed to parse PDF {pdf_path}: {e}")
        raise ValueError("Failed to extract text from PDF")

def parse_resume_with_gemini(text: str) -> dict:
    """Send resume text to Gemini to extract structured JSON data."""
    if not settings.gemini_api_key:
        logger.warning("Gemini API key is not configured.")
        return {}

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        
        prompt = (
            "Extract the following information from the resume text into JSON format:\n"
            "{\n"
            '  "headline": "A professional headline (max 100 chars)",\n'
            '  "bio": "A professional summary (max 1000 chars)",\n'
            '  "location": "The candidate\'s location, if available",\n'
            '  "skills": ["skill 1", "skill 2"],\n'
            '  "experience": [{"company": "...", "role": "...", "start_date": "YYYY-MM", "end_date": "YYYY-MM or Present", "description": "..."}],\n'
            '  "education": [{"institution": "...", "degree": "...", "field_of_study": "...", "start_date": "YYYY-MM", "end_date": "YYYY-MM"}]\n'
            "}\n"
            "\nResume text:\n"
            f"{text}"
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        return json.loads(response.text)
    except Exception as e:
        logger.error(f"Gemini API parsing failed: {e}", exc_info=True)
        return {}

def process_resume(pdf_path: str) -> dict:
    """Process a PDF resume and return extracted structured data."""
    try:
        text = extract_text_from_pdf(pdf_path)
        if not text.strip():
            logger.warning(f"No text extracted from PDF: {pdf_path}")
            return {}
        return parse_resume_with_gemini(text)
    except Exception as e:
        logger.error(f"Resume processing failed: {e}")
        return {}
