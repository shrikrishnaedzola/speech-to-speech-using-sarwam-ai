from report_module.accuracy import accuracy_score, analyse_accuracy, condition_true
from report_module.mishearing import find_mishearings
from tests.helpers import call_data, save


def analyse(data):
    return analyse_accuracy(data, find_mishearings(data))


def test_condition_true():
    rule = {"field": "n", "op": "gt", "value": 0}
    assert condition_true(rule, {"n": 2}) and not condition_true(rule, {"n": 0}) and not condition_true(rule, {})
    assert condition_true(None, {})


def test_accuracy_and_completion():
    data = call_data(
        answers=[{"field_id": "age", "value": 30, "status": "filled"},
                 {"field_id": "attended_sessions", "value": "yes", "status": "filled"},
                 {"field_id": "children_ages", "value": [3], "status": "filled"}],
        reviews=[{"field_id": "age", "verdict": "correct"},
                 {"field_id": "attended_sessions", "verdict": "wrong", "expected_value": "no"}],
    )
    acc = analyse(data)
    assert acc.filled == 3 and acc.reviewed == 2 and acc.correct == 1
    assert acc.field_accuracy == 0.5
    # attended = yes -> "reason" does not apply -> 2 required fields, both filled
    assert acc.required_total == 2 and acc.completion == 1.0
    row = next(r for r in acc.table if r.field_id == "attended_sessions")
    assert row.expected == "no" and row.saved == "yes" and row.correct is False


def test_followup_needed_but_not_asked():
    data = call_data(answers=[{"field_id": "attended_sessions", "value": "no", "status": "filled"}])
    acc = analyse(data)
    assert acc.followups_total == 1 and acc.followups_correct == 0
    assert "should have been asked" in acc.followup_issues[0]
    # Required fields that apply: age, attended, reason -> only "attended" is filled.
    assert acc.required_total == 3 and acc.required_filled == 1
    assert acc.completion == round(1 / 3, 4)


def test_followup_asked_when_not_needed():
    data = call_data(
        answers=[{"field_id": "attended_sessions", "value": "yes", "status": "filled"},
                 {"field_id": "reason_not_attended", "value": "x", "status": "filled", "attempts": 1}],
    )
    acc = analyse(data)
    assert "was asked although" in acc.followup_issues[0]


def test_error_recovery_and_tool_stats():
    data = call_data(
        tool_calls=[save("age", "150", 1, ok=False), save("age", "35", 2, 35),
                    {"name": "save_answer", "arguments": "{bad json", "success": False, "parse_error": True, "offset_s": 3}],
        answers=[{"field_id": "age", "value": 35, "status": "filled", "attempts": 2}],
    )
    acc = analyse(data)
    assert acc.invalid_answers == 1 and acc.invalid_answers_fixed == 1
    assert acc.invalid_tool_calls == 1 and acc.validation_errors == 1
    assert acc.tool_calls_total == 3 and abs(acc.tool_success_rate - 1 / 3) < 1e-3


def test_accuracy_score_weights():
    data = call_data(answers=[{"field_id": "age", "value": 30, "status": "filled"},
                              {"field_id": "attended_sessions", "value": "yes", "status": "filled"}],
                     reviews=[{"field_id": "age", "verdict": "correct"}, {"field_id": "attended_sessions", "verdict": "correct"}])
    acc = analyse(data)
    # accuracy 1.0, completion 1.0, follow-ups 1/1 -> 100
    assert accuracy_score(acc) == 100
