"""Tiny builders for test CallData (all fake data)."""

from datetime import datetime, timezone
from pathlib import Path

from report_module.schema import CallData

SAMPLES = Path(__file__).resolve().parent.parent / "report_module" / "sample_data"

FIELDS = [
    {"id": "age", "label": "Age", "type": "number", "required": True},
    {"id": "attended_sessions", "label": "Attended", "type": "yes_no", "required": True},
    {"id": "reason_not_attended", "label": "Reason", "type": "text", "required": True,
     "show_if": {"field": "attended_sessions", "op": "eq", "value": "no"}},
    {"id": "children_ages", "label": "Children's ages", "type": "number_list", "required": False},
]


def call_data(provider="sarvam", **overrides) -> CallData:
    base = {
        "call": {"call_id": "t1", "provider": provider, "model": "m", "language_selected": "hi-IN",
                 "started_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "duration_s": 120},
        "form_fields": FIELDS,
    }
    base.update(overrides)
    return CallData.model_validate(base)


def caller(text, at, lang="hi-IN"):
    return {"role": "caller", "text": text, "offset_s": at, "language": lang}


def agent(text, at, interrupted=False):
    return {"role": "agent", "text": text, "offset_s": at, "interrupted": interrupted}


def save(field_id, value, at, saved=None, ok=True):
    result = {"ok": True, "saved": {field_id: saved if saved is not None else value}} if ok else {"ok": False, "error": "bad"}
    return {"name": "save_answer", "arguments": {"field_id": field_id, "value": value, "confidence": "high"},
            "success": ok, "result": result, "offset_s": at}


def load_sample(name: str) -> CallData:
    return CallData.model_validate_json((SAMPLES / f"sample-{name}-01.json").read_text(encoding="utf-8"))
