"""Load form definitions from JSON files into the database.

To add a form: drop a new .json file in app/seed_forms/ (same shape as
program_feedback_survey.json) and restart the backend.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import SEED_FORMS_DIR
from app.models import Form, utcnow

VALID_TYPES = {"text", "number", "choice", "yes_no", "number_list"}


def check_form(form: dict) -> None:
    """Raise ValueError if the form JSON is malformed (caught at startup, not mid-call)."""
    for key in ("id", "name", "fields"):
        if key not in form:
            raise ValueError(f"Form is missing '{key}'")
    ids = [f["id"] for f in form["fields"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Form {form['id']} has duplicate field ids")
    for f in form["fields"]:
        if f.get("type") not in VALID_TYPES:
            raise ValueError(f"Field {f['id']} has unknown type {f.get('type')}")
        if f["type"] == "choice" and not f.get("choices"):
            raise ValueError(f"Choice field {f['id']} has no choices")
        rule = f.get("show_if")
        if rule and rule.get("field") not in ids:
            raise ValueError(f"Field {f['id']} show_if refers to unknown field {rule.get('field')}")


def load_seed_forms(db: Session, folder: Path = SEED_FORMS_DIR) -> int:
    """Insert or update every form JSON in the folder. Returns how many were loaded."""
    count = 0
    for path in sorted(folder.glob("*.json")):
        form = json.loads(path.read_text(encoding="utf-8"))
        check_form(form)
        row = db.get(Form, form["id"])
        if row is None:
            db.add(Form(id=form["id"], name=form["name"], definition=form))
        else:
            row.name, row.definition, row.updated_at = form["name"], form, utcnow()
        count += 1
    db.commit()
    return count
