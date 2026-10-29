"""Validate and normalize one answer against its field definition.

Field types: text, number, choice, yes_no, number_list.
Each check returns a ValidationResult. On failure, `error` is a short sentence
that goes back to the LLM so it can politely ask the question again.
"""

from dataclasses import dataclass
from typing import Any

from app.services.spoken_numbers import parse_number_list, parse_spoken_number

YES_WORDS = {
    "yes", "y", "yeah", "yep", "true", "haan", "han", "haa", "ha", "haanji", "ji", "ji haan", "bilkul",
    "hoy", "ho", "aamaa", "aama", "aamam", "amam", "avunu", "aunu", "sari", "theek hai", "okay", "ok",
    "हाँ", "हां", "हा", "जी", "जी हाँ", "होय", "हो", "ஆமா", "ஆமாம்", "சரி", "అవును", "హా",
}
NO_WORDS = {
    "no", "n", "nope", "false", "nahi", "nahin", "nai", "na", "naa", "ji nahi", "illai", "illa",
    "ledu", "kaadu", "kadu", "nako", "nahi ji",
    "नहीं", "नही", "ना", "नाही", "இல்லை", "இல்ல", "లేదు", "కాదు",
}

# Common spoken / native-script names for choice options (matched case-insensitively).
CHOICE_ALIASES = {
    "hindi": ["हिंदी", "हिन्दी", "hindee"],
    "english": ["angrezi", "angreji", "अंग्रेज़ी", "अंग्रेजी", "ஆங்கிலம்", "ఇంగ్లీష్"],
    "tamil": ["தமிழ்", "thamizh", "tamizh"],
    "telugu": ["తెలుగు", "telegu"],
    "marathi": ["मराठी"],
    "other": ["dusri", "doosri", "anya", "अन्य", "दूसरी"],
}

MAX_TEXT_LENGTH = 500


@dataclass
class ValidationResult:
    ok: bool
    value: Any = None
    error: str | None = None


def _fail(msg: str) -> ValidationResult:
    return ValidationResult(ok=False, error=msg)


def _check_range(n, low, high, label: str) -> str | None:
    if low is not None and n < low:
        return f"{label} must be at least {low}, but got {n}."
    if high is not None and n > high:
        return f"{label} must be at most {high}, but got {n}."
    return None


def validate_text(field: dict, value: Any) -> ValidationResult:
    if value is None or isinstance(value, (list, dict)):
        return _fail(f"{field['label']} must be a short text answer.")
    text = str(value).strip()
    if not text:
        return _fail(f"{field['label']} is empty. Please ask again.")
    if len(text) > MAX_TEXT_LENGTH:
        return _fail(f"{field['label']} is too long. Save a short summary instead.")
    return ValidationResult(ok=True, value=text)


def validate_number(field: dict, value: Any) -> ValidationResult:
    n = parse_spoken_number(value)
    if n is None:
        return _fail(f"Could not understand a single number for {field['label']} from '{value}'. Ask again.")
    if isinstance(n, float):
        if not n.is_integer():
            return _fail(f"{field['label']} must be a whole number, but got {n}.")
        n = int(n)
    err = _check_range(n, field.get("min"), field.get("max"), field["label"])
    return _fail(err + " Politely ask again.") if err else ValidationResult(ok=True, value=n)


def validate_yes_no(field: dict, value: Any) -> ValidationResult:
    if isinstance(value, bool):
        return ValidationResult(ok=True, value="yes" if value else "no")
    text = str(value).strip().lower().strip(".!?, ")
    if text in YES_WORDS:
        return ValidationResult(ok=True, value="yes")
    if text in NO_WORDS:
        return ValidationResult(ok=True, value="no")
    return _fail(f"{field['label']} must be yes or no, but got '{value}'. Ask again.")


def validate_choice(field: dict, value: Any) -> ValidationResult:
    text = str(value).strip().lower()
    choices = field.get("choices", [])
    for choice in choices:
        if text == choice.lower():
            return ValidationResult(ok=True, value=choice)
    for choice in choices:
        aliases = [a.lower() for a in CHOICE_ALIASES.get(choice.lower(), [])]
        aliases += [a.lower() for a in field.get("choice_aliases", {}).get(choice, [])]
        if text in aliases:
            return ValidationResult(ok=True, value=choice)
    return _fail(f"{field['label']} must be one of: {', '.join(choices)}. Got '{value}'. Ask again.")


def validate_number_list(field: dict, value: Any, values: dict) -> ValidationResult:
    numbers = parse_number_list(value)
    if not numbers:
        return _fail(f"Could not understand the numbers for {field['label']} from '{value}'. Ask again.")
    clean = []
    for n in numbers:
        if isinstance(n, float) and not n.is_integer():
            return _fail(f"{field['label']} must be whole numbers, but got {n}.")
        n = int(n)
        err = _check_range(n, field.get("item_min"), field.get("item_max"), f"Each value in {field['label']}")
        if err:
            return _fail(err + " Politely ask again.")
        clean.append(n)
    count_field = field.get("length_equals_field")
    if count_field and count_field in values:
        expected = values[count_field]
        if len(clean) != expected:
            return _fail(
                f"{field['label']} has {len(clean)} values but {count_field} is {expected}. "
                f"Ask again for exactly {expected} values, or confirm {count_field}."
            )
    return ValidationResult(ok=True, value=clean)


def validate_value(field: dict, value: Any, values: dict[str, Any]) -> ValidationResult:
    """Validate one answer.

    Args:
        field: The field definition from the form JSON.
        value: The raw value from the LLM tool call (or the API).
        values: Already-saved normalized values (for cross-field rules).
    """
    kind = field["type"]
    if kind == "text":
        return validate_text(field, value)
    if kind == "number":
        return validate_number(field, value)
    if kind == "yes_no":
        return validate_yes_no(field, value)
    if kind == "choice":
        return validate_choice(field, value)
    if kind == "number_list":
        return validate_number_list(field, value, values)
    return _fail(f"Unknown field type '{kind}'.")
