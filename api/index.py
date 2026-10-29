"""Vercel Serverless Function entry point.

Exports the FastAPI `app` instance from `backend.app.main`.
Configures `sys.path` so that `backend` and `report_module` are properly resolvable.
"""

import sys
from pathlib import Path

# Add project root, backend, and report_module directories to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"
REPORT_MODULE_DIR = ROOT_DIR / "report_module"

for path_obj in (BACKEND_DIR, REPORT_MODULE_DIR, ROOT_DIR):
    path_str = str(path_obj)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.main import app  # noqa: E402

