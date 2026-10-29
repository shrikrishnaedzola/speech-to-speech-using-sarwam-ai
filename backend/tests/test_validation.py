import pytest

from app.services.validation import validate_value


def field(form, field_id):
    return next(f for f in form["fields"] if f["id"] == field_id)


@pytest.mark.parametrize("value, expected", [("35", 35), (35, 35), ("paintees", 35), ("18", 18), ("100", 100)])
def test_age_valid(form, value, expected):
    result = validate_value(field(form, "age"), value, {})
    assert result.ok and result.value == expected


@pytest.mark.parametrize("value", ["150", "17", "abc", "35.5", "do ya teen"])
def test_age_invalid(form, value):
    result = validate_value(field(form, "age"), value, {})
    assert not result.ok and result.error


@pytest.mark.parametrize("value", ["0", "6"])
def test_rating_out_of_range(form, value):
    assert not validate_value(field(form, "satisfaction_rating"), value, {}).ok


@pytest.mark.parametrize(
    "value, expected",
    [("yes", "yes"), ("haan", "yes"), ("हाँ", "yes"), ("avunu", "yes"), (True, "yes"),
     ("no", "no"), ("nahi", "no"), ("illai", "no"), ("లేదు", "no"), (False, "no")],
)
def test_yes_no(form, value, expected):
    result = validate_value(field(form, "attended_sessions"), value, {})
    assert result.ok and result.value == expected


def test_yes_no_rejects_unclear(form):
    assert not validate_value(field(form, "attended_sessions"), "maybe", {}).ok


@pytest.mark.parametrize("value", ["Hindi", "hindi", "हिंदी", "HINDI"])
def test_choice_matches(form, value):
    result = validate_value(field(form, "preferred_language"), value, {})
    assert result.ok and result.value == "Hindi"


def test_choice_rejects_unknown(form):
    result = validate_value(field(form, "preferred_language"), "French", {})
    assert not result.ok and "Hindi" in result.error


def test_text(form):
    assert validate_value(field(form, "district"), "  Sample district ", {}).value == "Sample district"
    assert not validate_value(field(form, "district"), "   ", {}).ok
    assert not validate_value(field(form, "district"), "x" * 600, {}).ok


def test_children_ages_must_match_count(form):
    ages = field(form, "children_ages")
    assert validate_value(ages, "5, 8", {"number_of_children": 2}).value == [5, 8]
    mismatch = validate_value(ages, "5, 8", {"number_of_children": 3})
    assert not mismatch.ok and "3" in mismatch.error
    assert not validate_value(ages, "5, 80", {"number_of_children": 2}).ok  # out of item range
