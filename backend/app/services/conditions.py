"""Follow-up question logic.

A field can have a "show_if" rule in the form JSON, for example:
    "show_if": {"field": "attended_sessions", "op": "eq", "value": "no"}
The field is only asked (and only shown in the UI) when the rule is true.
If the field it depends on has no answer yet, the follow-up stays hidden.
"""

from typing import Any

OPERATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
}


def is_visible(field: dict, values: dict[str, Any]) -> bool:
    """True if the field should be asked, given the saved values so far.

    Args:
        field: One field from the form definition.
        values: field_id -> saved (normalized) value, only for filled fields.
    """
    rule = field.get("show_if")
    if not rule:
        return True
    if rule["field"] not in values:
        return False
    try:
        return bool(OPERATORS[rule["op"]](values[rule["field"]], rule["value"]))
    except (TypeError, KeyError):
        # Wrong types (e.g. comparing text with a number) -> treat as hidden.
        return False


def visible_fields(form: dict, values: dict[str, Any]) -> list[dict]:
    """The fields that should currently be asked, in form order."""
    return [f for f in form["fields"] if is_visible(f, values)]


def dependents_of(form: dict, field_id: str) -> list[dict]:
    """Fields whose show_if rule or length rule depends on field_id."""
    return [
        f
        for f in form["fields"]
        if (f.get("show_if") or {}).get("field") == field_id or f.get("length_equals_field") == field_id
    ]
