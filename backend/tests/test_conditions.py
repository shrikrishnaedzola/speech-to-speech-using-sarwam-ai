from app.pipeline.prompt import build_system_prompt
from app.services.conditions import dependents_of, is_visible, visible_fields


def field(form, field_id):
    return next(f for f in form["fields"] if f["id"] == field_id)


def test_follow_ups_hidden_until_parent_answered(form):
    assert not is_visible(field(form, "reason_not_attended"), {})
    assert not is_visible(field(form, "sessions_attended_count"), {})
    assert not is_visible(field(form, "children_ages"), {})


def test_attended_no_shows_reason_only(form):
    values = {"attended_sessions": "no"}
    assert is_visible(field(form, "reason_not_attended"), values)
    assert not is_visible(field(form, "sessions_attended_count"), values)


def test_attended_yes_shows_count_only(form):
    values = {"attended_sessions": "yes"}
    assert is_visible(field(form, "sessions_attended_count"), values)
    assert not is_visible(field(form, "reason_not_attended"), values)


def test_children_ages_only_when_children(form):
    assert not is_visible(field(form, "children_ages"), {"number_of_children": 0})
    assert is_visible(field(form, "children_ages"), {"number_of_children": 2})


def test_wrong_type_is_hidden_not_crash(form):
    assert not is_visible(field(form, "children_ages"), {"number_of_children": "two"})


def test_visible_fields_in_order(form):
    ids = [f["id"] for f in visible_fields(form, {"attended_sessions": "yes", "number_of_children": 1})]
    assert ids.index("sessions_attended_count") == ids.index("attended_sessions") + 1
    assert "children_ages" in ids and "reason_not_attended" not in ids


def test_dependents(form):
    assert {f["id"] for f in dependents_of(form, "attended_sessions")} == {"reason_not_attended", "sessions_attended_count"}
    assert [f["id"] for f in dependents_of(form, "number_of_children")] == ["children_ages"]


def test_prompt_is_built_from_form(form):
    prompt = build_system_prompt(form, "ta-IN")
    assert "Speak in Tamil" in prompt
    for f in form["fields"]:
        assert f["id"] in prompt
    assert 'ask ONLY if attended_sessions is "no"' in prompt
    assert "18 to 100" in prompt
    assert "caller's language" in build_system_prompt(form, "auto")
