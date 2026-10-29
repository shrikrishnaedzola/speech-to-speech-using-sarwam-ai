"""FastAPI app entry point.

Run (from the backend folder):
    .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8010
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text

from app.config import CORS_ORIGINS, has_api_key
from app.db import SessionLocal, ensure_db_initialized, init_db
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
    await session.close_webrtc_handler()


app = FastAPI(title="Zolabs Voice Form Tester - Sarvam Pipeline", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for module in (forms, session, tools, calls):
    app.include_router(module.router)
# Post-call report (shared module): /api/calls/{id}/report, /ratings, /report/export, /api/report/settings
app.include_router(make_report_router(report_service))


@app.get("/api/health")
def health():
    db_ok = True
    db_error = None
    try:
        ensure_db_initialized()
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = False
        db_error = str(e)
    return {
        "ok": True,
        "database": {"connected": db_ok, "error": db_error},
        "api_key_configured": has_api_key(),
    }


# Single-service deploys (Render/Docker): serve the built frontend from the same origin,
# so the browser's relative /api calls and the events WebSocket need no CORS or base URL.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and FRONTEND_DIST in file.parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")  # SPA routes such as /report/<id>
