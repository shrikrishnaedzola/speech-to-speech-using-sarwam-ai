import csv
import io
import json

from app.models import TurnMetric
from app.services.export import CSV_COLUMNS, SARVAM_EXTRA_COLUMNS, TURN_COLUMNS
from tests.conftest import save


def _setup_call(client, db, call_id):
    save(client, call_id, "caller_name", "Test User")
    save(client, call_id, "age", "35")
    save(client, call_id, "attended_sessions", "no")
    db.add(TurnMetric(call_id=call_id, turn_index=1, stt_ms=150, turn_wait_ms=70, llm_ttft_ms=600,
                      tts_ttfb_ms=200, total_ms=1050, user_text="Test", agent_text="Ok"))
    db.add(TurnMetric(call_id=call_id, turn_index=2, stt_ms=250, turn_wait_ms=70, llm_ttft_ms=800,
                      tts_ttfb_ms=300, total_ms=1450))
    db.commit()
    client.post(f"/api/calls/{call_id}/review", json={"reviews": [
        {"field_id": "caller_name", "verdict": "correct"},
        {"field_id": "age", "verdict": "wrong", "expected_value": "36"},
    ]})


def test_csv_export(client, db, call_id):
    _setup_call(client, db, call_id)
    res = client.get(f"/api/calls/{call_id}/export?format=csv")
    assert res.status_code == 200
    rows = list(csv.DictReader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert CSV_COLUMNS[-len(SARVAM_EXTRA_COLUMNS):] == SARVAM_EXTRA_COLUMNS  # extras are last
    by_field = {r["field_id"]: r for r in rows}
    assert len(rows) == 12  # one row per form field
    assert by_field["age"]["review_verdict"] == "wrong" and by_field["age"]["expected_value"] == "36"
    assert by_field["sessions_attended_count"]["status"] == "not_applicable"
    assert by_field["reason_not_attended"]["status"] == "pending"
    assert by_field["age"]["accuracy"] == "0.5"  # 1 correct of 2 reviewed
    assert by_field["age"]["avg_stt_ms"] == "200.0"
    assert by_field["age"]["avg_response_ms"] == "1250.0"
    assert by_field["age"]["max_response_ms"] == "1450.0"


def test_turns_csv(client, db, call_id):
    _setup_call(client, db, call_id)
    res = client.get(f"/api/calls/{call_id}/export?format=csv&section=turns")
    rows = list(csv.DictReader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert list(rows[0].keys()) == TURN_COLUMNS
    assert [r["total_ms"] for r in rows] == ["1050.0", "1450.0"]


def test_json_export(client, db, call_id):
    _setup_call(client, db, call_id)
    data = json.loads(client.get(f"/api/calls/{call_id}/export?format=json").content)
    assert data["call"]["pipeline"] == "sarvam"
    assert len(data["rows"]) == 12 and len(data["turns"]) == 2
    assert data["metrics"]["completion"] is not None
    assert data["metrics"]["cost"]["currency"] == "INR"
    assert "SARVAM_API_KEY" not in json.dumps(data)


def test_review_can_be_removed(client, db, call_id):
    _setup_call(client, db, call_id)
    state = client.post(f"/api/calls/{call_id}/review",
                        json={"reviews": [{"field_id": "age", "verdict": None}]}).json()
    assert next(f for f in state["fields"] if f["id"] == "age")["review"] is None


def test_unknown_call_404(client):
    assert client.get("/api/calls/nope/export?format=csv").status_code == 404
