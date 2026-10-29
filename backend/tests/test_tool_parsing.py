import pytest

from app.services.tool_schema import parse_tool_arguments, tool_definitions

FIELD_IDS = ["caller_name", "age"]


def test_dict_arguments():
    args, err = parse_tool_arguments("save_answer", {"field_id": "age", "value": "35", "confidence": "high"}, FIELD_IDS)
    assert err is None and args["value"] == "35"


def test_json_string_arguments():
    args, err = parse_tool_arguments("save_answer", '{"field_id": "age", "value": 35, "confidence": "low"}', FIELD_IDS)
    assert err is None and args["value"] == 35


def test_code_fenced_json_is_accepted():
    raw = '```json\n{"field_id": "age", "value": "35", "confidence": "high"}\n```'
    args, err = parse_tool_arguments("save_answer", raw, FIELD_IDS)
    assert err is None and args["field_id"] == "age"


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ('{"field_id": "age", "value": "35" "confidence": "high"}', "not valid JSON"),
        ('["age", "35"]', "JSON object"),
        ({"field_id": "age", "value": "35"}, "Missing required argument 'confidence'"),
        ({"field_id": "age", "value": "35", "confidence": "maybe"}, "confidence"),
        ({"field_id": "phone", "value": "x", "confidence": "high"}, "field_id"),
        ({"field_id": "age", "value": "35", "confidence": "high", "extra": 1}, "Unknown argument"),
        ({"field_id": 5, "value": "35", "confidence": "high"}, "field_id"),
    ],
)
def test_invalid_arguments(raw, fragment):
    args, err = parse_tool_arguments("save_answer", raw, FIELD_IDS)
    assert args is None and fragment in err


def test_unknown_tool():
    assert parse_tool_arguments("delete_everything", {}, FIELD_IDS)[1] == "Unknown tool 'delete_everything'."


@pytest.mark.parametrize("raw", [None, "", "{}", {}])
def test_complete_form_takes_no_arguments(raw):
    assert parse_tool_arguments("complete_form", raw, FIELD_IDS) == ({}, None)


def test_schema_limits_field_ids_to_the_form():
    save = next(t for t in tool_definitions(FIELD_IDS) if t["name"] == "save_answer")
    assert save["parameters"]["properties"]["field_id"]["enum"] == FIELD_IDS
    assert save["parameters"]["required"] == ["field_id", "value", "confidence"]
