"""FastAPI app entry point.

Run (from the backend folder):
    .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8010
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import CORS_ORIGINS, has_api_key
from app.db import SessionLocal, init_db
from report_module.router import make_report_router

from app.routers import calls, forms, session, tools
from app.services.forms_loader import load_seed_forms
from app.services.report_hook import report_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        count = load_seed_forms(db)
    logger.info(f"Loaded {count} form(s) from seed_forms/")
    if not has_api_key():
        logger.warning("SARVAM_API_KEY is not set: live calls are disabled, Simulate mode still works.")
    yield
    await session.webrtc_handler.close()


app = FastAPI(title="Zolabs Voice Form Tester - Sarvam Pipeline", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for module in (forms, session, tools, calls):
    app.include_router(module.router)
# Post-call report (shared module): /api/calls/{id}/report, /ratings, /report/export, /api/report/settings
app.include_router(make_report_router(report_service))


@app.get("/api/health")
def health():
    return {"ok": True, "api_key_configured": has_api_key()}
