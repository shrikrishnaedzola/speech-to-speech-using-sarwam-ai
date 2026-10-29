"""Shared test setup: a throwaway SQLite database and helpers.

Tests never call Sarvam and never need an API key.
"""

import os
import tempfile
import uuid

# Point the app at a temporary database BEFORE importing it.
_tmp_dir = tempfile.mkdtemp(prefix="sarvam_tester_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import DEFAULT_CALL_SETTINGS  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Call, Form  # noqa: E402
from app.services.forms_loader import load_seed_forms  # noqa: E402

FORM_ID = "program_feedback_survey_test"


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    with SessionLocal() as db:
        load_seed_forms(db)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def form(db):
    return db.get(Form, FORM_ID).definition


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def call_id(db):
    """A fresh call row for each test."""
    cid = uuid.uuid4().hex[:12]
    db.add(Call(id=cid, form_id=FORM_ID, mode="simulate", status="listening",
                settings=dict(DEFAULT_CALL_SETTINGS), transcript=[], errors=[]))
    db.commit()
    return cid


def save(client, call_id, field_id, value, confidence="high"):
    """Shortcut: run save_answer through the API, like the LLM would."""
    return client.post(
        "/api/tools/save_answer",
        json={"call_id": call_id, "arguments": {"field_id": field_id, "value": value, "confidence": confidence}},
    ).json()
