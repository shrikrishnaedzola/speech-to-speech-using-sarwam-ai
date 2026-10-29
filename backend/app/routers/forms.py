"""GET /api/forms, GET /api/forms/{id}, GET /api/options."""

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.models import Form

router = APIRouter(prefix="/api")


@router.get("/forms")
def list_forms(db: Session = Depends(get_db)):
    try:
        forms = db.scalars(select(Form).order_by(Form.name)).all()
        return [{"id": f.id, "name": f.name, "field_count": len(f.definition["fields"])} for f in forms]
    except Exception as e:
        logger.error(f"Failed to list forms from database: {e}")
        raise HTTPException(500, detail=f"Database error: {e}")


@router.get("/forms/{form_id}")
def get_form(form_id: str, db: Session = Depends(get_db)):
    try:
        form = db.get(Form, form_id)
        if form is None:
            raise HTTPException(404, "Form not found")
        return form.definition
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch form {form_id}: {e}")
        raise HTTPException(500, detail=f"Database error: {e}")


@router.get("/options")
def options():
    """Dropdown lists and default settings for the UI (no secrets here)."""
    return {
        "stt_models": config.STT_MODELS,
        "llm_models": config.LLM_MODELS,
        "tts_models": config.TTS_MODELS,
        "tts_voices": {"bulbul:v3": config.TTS_VOICES_V3, "bulbul:v4-flash": config.TTS_VOICES_V4},
        "languages": config.LANGUAGES,
        "v4_unsupported_languages": sorted(config.V4_UNSUPPORTED_LANGUAGES),
        "defaults": config.DEFAULT_CALL_SETTINGS,
        "api_key_configured": config.has_api_key(),
    }
