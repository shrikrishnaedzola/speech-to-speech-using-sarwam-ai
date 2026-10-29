"""Backend entry point for local execution and Vercel Serverless Function."""

import sys
from pathlib import Path

# Ensure the backend directory is in the Python search path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

# Expose app for ASGI / Uvicorn / Vercel
__all__ = ["app"]

