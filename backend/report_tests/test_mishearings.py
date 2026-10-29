"""Correction detection, number checks and the full mishearing finder."""

import pytest

from report_module.mishearing import find_mishearings, is_correction, values_equal
from tests.helpers import agent, call_data, caller, save


@pytest.mark.parametrize("text", [
    "No, I said forty five.",
    "I meant fifteen",
    "That's wrong, it is 45",
    "Nahi, maine pachees kaha tha",
    "maine kaha tha teen",
    "ye galat hai",
    "नहीं, मैंने पच्चीस कहा",
    "Illa, naan sonnadhu muppathu",
    "Kaadu, nenu cheppindi iravai",
])
def test_corrections_detected(text):
    assert is_correction(text)


@pytest.mark.parametrize("text", ["Haan ji, boliye.", "Yes, go ahead.", "Nahi, kuch nahi.", "Teen sessions."])
def test_not_corrections(text):
    assert not is_correction(text)


def test_values_equal():
    assert values_equal(35, "35")
    assert values_equal(35, "paintees")
    assert values_equal([5, 8], "5, 8")
    assert values_equal("Sample district", "sample district")
    assert not values_equal(54, 45)
    assert not values_equal("yes", "no")


def test_caller_correction_is_found_and_fixed():
    data = call_data(
        transcript=[agent("Aapki umar?", 1), caller("Pachaas.", 3), agent("Theek hai.", 4),
                    caller("Nahi, maine pachees kaha tha.", 6)],
        tool_calls=[save("age", "50", 3.5, 50), save("age", "25", 6.5, 25)],
        answers=[{"field_id": "age", "value": 25, "status": "filled", "attempts": 2}],
        reviews=[{"field_id": "age", "verdict": "correct"}],
    )
    result = find_mishearings(data)
    assert result.total == 1
    item = result.items[0]
    assert item.kind == "caller_correction"
    assert item.heard == "50" and item.field_id == "age" and item.fixed is True


def test_value_change_without_correction_phrase():
    data = call_data(
        transcript=[caller("Pachaas.", 3), caller("Pachees.", 6)],
        tool_calls=[save("age", "50", 3.5, 50), save("age", "25", 6.5, 25)],
        answers=[{"field_id": "age", "value": 25, "status": "filled"}],
    )
    assert [m.kind for m in find_mishearings(data).items] == ["value_changed"]


def test_number_misheard_fifteen_saved_as_50():
    data = call_data(
        transcript=[caller("Fifteen.", 3, "en-IN")],
        tool_calls=[save("age", "50", 3.5, 50)],
        answers=[{"field_id": "age", "value": 50, "status": "filled"}],
    )
    items = find_mishearings(data).items
    assert len(items) == 1 and items[0].kind == "number_misheard"
    assert items[0].said == "Fifteen." and items[0].heard == "50" and items[0].fixed is False


@pytest.mark.parametrize("said, saved", [("teen", 3), ("मेरी उम्र पैंतीस है", 35), ("moonu", 3), ("iravai aidu", 25)])
def test_correct_numbers_not_flagged(said, saved):
    data = call_data(transcript=[caller(said, 3)], tool_calls=[save("age", str(saved), 3.5, saved)],
                     answers=[{"field_id": "age", "value": saved, "status": "filled"}])
    assert find_mishearings(data).total == 0


def test_tamil_number_misheard():
    data = call_data(transcript=[caller("முப்பத்தி ரெண்டு.", 3, "ta-IN")], tool_calls=[save("age", "22", 3.5, 22)],
                     answers=[{"field_id": "age", "value": 22, "status": "filled"}])
    item = find_mishearings(data).items[0]
    assert item.kind == "number_misheard" and item.language == "ta-IN"


def test_number_list_misheard():
    data = call_data(transcript=[caller("Paanch aur aath.", 3)], tool_calls=[save("children_ages", "5, 9", 3.5, [5, 9])],
                     answers=[{"field_id": "children_ages", "value": [5, 9], "status": "filled"}])
    assert find_mishearings(data).items[0].kind == "number_misheard"


def test_transcription_error_against_script():
    data = call_data(
        transcript=[caller("Haan ji.", 2), caller("Pachaas saal.", 5)],
        tool_calls=[save("age", "50", 5.5, 50)],
        answers=[{"field_id": "age", "value": 50, "status": "filled"}],
        expected_script={"caller_turns": ["Haan ji.", "Pachees saal."], "expected_answers": {"age": 25}},
    )
    result = find_mishearings(data)
    assert result.script_available and result.aligned_turns == 2
    assert result.wer == pytest.approx(1 / 4)  # 4 reference words, 1 wrong
    kinds = {m.kind for m in result.items}
    assert "transcription" in kinds
    # Same root cause: the wrong final value is not listed a second time.
    assert "wrong_value" not in kinds
    assert all(m.fixed is False for m in result.items)


def test_wrong_value_from_tester_review():
    data = call_data(
        answers=[{"field_id": "attended_sessions", "value": "yes", "status": "filled"}],
        reviews=[{"field_id": "attended_sessions", "verdict": "wrong", "expected_value": "no"}],
    )
    item = find_mishearings(data).items[0]
    assert item.kind == "wrong_value" and item.said == "no" and item.heard == "yes" and item.fixed is False
