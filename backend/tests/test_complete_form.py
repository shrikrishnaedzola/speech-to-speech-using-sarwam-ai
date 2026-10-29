"""Tool behaviour through the real API: save, reject, follow-ups, complete_form."""

from app.models import Call
from tests.conftest import save

ALL_REQUIRED = [
    ("caller_name", "Test User"),
    ("age", "35"),
    ("district", "Sample district"),
    ("attended_sessions", "yes"),
    ("sessions_attended_count", "teen"),
    ("number_of_children", "2"),
    ("children_ages", "5, 8"),
    ("satisfaction_rating", "4"),
    ("consent_to_followup", "haan"),
]


def complete(client, call_id):
    return client.post("/api/tools/complete_form", json={"call_id": call_id, "arguments": {}}).json()


def test_complete_form_lists_missing_required_only(client, call_id):
    result = complete(client, call_id)
    assert result["ok"] is False
    missing = {m["field_id"] for m in result["missing_fields"]}
    # Required, always-visible fields are missing...
    assert {"caller_name", "age", "consent_to_followup"} <= missing
    # ...but hidden follow-ups and optional fields are not asked for.
    assert not missing & {"reason_not_attended", "sessions_attended_count", "children_ages", "improvement_suggestion"}


def test_complete_form_succeeds_when_all_filled(client, call_id, db):
    for field_id, value in ALL_REQUIRED:
        assert save(client, call_id, field_id, value)["ok"], field_id
    result = complete(client, call_id)
    assert result["ok"] is True
    db.expire_all()
    assert db.get(Call, call_id).form_completed


def test_follow_up_becomes_required(client, call_id):
    save(client, call_id, "attended_sessions", "no")
    missing = {m["field_id"] for m in complete(client, call_id)["missing_fields"]}
    assert "reason_not_attended" in missing and "sessions_attended_count" not in missing


def test_low_confidence_counts_as_missing(client, call_id):
    for field_id, value in ALL_REQUIRED:
        save(client, call_id, field_id, value)
    save(client, call_id, "age", "35", confidence="low")
    result = complete(client, call_id)
    assert result["ok"] is False
    assert result["missing_fields"] == [{"field_id": "age", "question": "What is your age?", "status": "needs_confirmation"}]


def test_invalid_answer_is_rejected_with_reason(client, call_id):
    result = save(client, call_id, "age", "150")
    assert result["ok"] is False and "at most 100" in result["error"]
    state = client.get(f"/api/calls/{call_id}").json()["form"]["fields"]
    age = next(f for f in state if f["id"] == "age")
    assert age["status"] == "pending" and age["attempts"] == 1


def test_hidden_follow_up_cannot_be_saved(client, call_id):
    save(client, call_id, "number_of_children", "0")
    result = save(client, call_id, "children_ages", "5")
    assert result["ok"] is False and "does not apply" in result["error"]


def test_correction_rechecks_dependent_field(client, call_id):
    save(client, call_id, "number_of_children", "2")
    save(client, call_id, "children_ages", "5, 8")
    save(client, call_id, "number_of_children", "teen")  # caller corrects: 3 children
    fields = {f["id"]: f for f in client.get(f"/api/calls/{call_id}").json()["form"]["fields"]}
    assert fields["number_of_children"]["value"] == 3
    assert fields["children_ages"]["status"] == "needs_confirmation"


def test_skip_only_optional(client, call_id):
    url = "/api/tools/skip_field"
    required = client.post(url, json={"call_id": call_id, "arguments": {"field_id": "age", "reason": "no"}}).json()
    optional = client.post(url, json={"call_id": call_id,
                                      "arguments": {"field_id": "improvement_suggestion", "reason": "none"}}).json()
    assert required["ok"] is False and optional["ok"] is True


def test_request_clarification_marks_field(client, call_id):
    client.post("/api/tools/request_clarification",
                json={"call_id": call_id, "arguments": {"field_id": "district", "reason": "noisy line"}})
    fields = {f["id"]: f for f in client.get(f"/api/calls/{call_id}").json()["form"]["fields"]}
    assert fields["district"]["status"] == "needs_confirmation" and fields["district"]["note"] == "noisy line"


def test_malformed_json_counts_parse_failure(client, call_id):
    bad = '{"field_id": "age", "value": "35" "confidence": "high"}'
    result = client.post("/api/tools/save_answer", json={"call_id": call_id, "arguments": bad}).json()
    assert result["ok"] is False and "Invalid arguments" in result["error"]
    report = client.get(f"/api/calls/{call_id}").json()
    assert report["metrics"]["json_parse_failures"] == 1
    assert report["tool_calls"][-1]["success"] is False
