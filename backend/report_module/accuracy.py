"""Form-data accuracy: field accuracy, completion, follow-ups, error recovery, tool calls.

- Field accuracy = correct fields / filled fields whose correctness is known
  (tester marks, or the expected answers of a test scenario).
- Completion     = required fields filled / required fields that apply.
- Follow-ups     = asked when their condition was true, not asked when false.
"""

from report_module.mishearing import FinalValues, value_to_text
from report_module.schema import AccuracySection, CallData, FieldRow, MishearingSection

FILLED = ("filled", "needs_confirmation")

_OPS = {
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b, "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b, "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
}


def condition_true(rule: dict | None, values: dict) -> bool:
    """Same follow-up rule format as the tester forms: {"field", "op", "value"}."""
    if not rule:
        return True
    if rule["field"] not in values:
        return False
    try:
        return bool(_OPS[rule["op"]](values[rule["field"]], rule["value"]))
    except (TypeError, KeyError):
        return False


def analyse_accuracy(data: CallData, mishearings: MishearingSection) -> AccuracySection:
    final = FinalValues(data)
    answers = {a.field_id: a for a in data.answers}
    values = final.values
    attempted = {tc.arguments.get("field_id") for tc in data.tool_calls
                 if tc.name in ("save_answer", "skip_field", "request_clarification") and isinstance(tc.arguments, dict)}

    rows, followup_issues = [], []
    filled = reviewed = correct = required_total = required_filled = 0
    followups_total = followups_ok = 0
    for f in data.form_fields:
        applies = condition_true(f.show_if, values)
        answer = answers.get(f.id)
        status = answer.status if answer else "pending"
        is_correct = final.is_correct(f.id) if status in FILLED else None

        if f.show_if:
            followups_total += 1
            asked = f.id in attempted or (answer is not None and (answer.attempts > 0 or status != "pending"))
            if asked == applies:
                followups_ok += 1
            elif applies:
                followup_issues.append(f"'{f.label}' should have been asked but was not.")
            else:
                followup_issues.append(f"'{f.label}' was asked although its condition was not met.")

        if applies and status in FILLED:
            filled += 1
            if is_correct is not None:
                reviewed += 1
                correct += int(is_correct)
        if applies and f.required:
            required_total += 1
            required_filled += int(status == "filled")

        notes = []
        if not applies:
            notes.append("not applicable (follow-up condition false)")
        if status == "needs_confirmation":
            notes.append("needs confirmation")
        if status == "skipped":
            notes.append("skipped")
        if answer and answer.confidence == "low":
            notes.append("low confidence")
        if answer and answer.attempts > 1:
            notes.append(f"{answer.attempts} save attempts")
        if applies and f.required and status == "pending":
            notes.append("required but missing")
        expected = final.expected_for(f.id)
        rows.append(FieldRow(
            field_id=f.id, label=f.label,
            expected=value_to_text(expected) if expected is not None else None,
            saved=value_to_text(answer.value) if answer and status in FILLED else None,
            correct=is_correct, notes="; ".join(notes),
        ))

    # Error recovery: answers the backend rejected, and whether the field was saved later.
    saves = [tc for tc in data.tool_calls if tc.name == "save_answer"]
    validation_failures = [tc for tc in saves if not tc.success and not tc.parse_error]
    fixed = 0
    for bad in validation_failures:
        fid = bad.arguments.get("field_id") if isinstance(bad.arguments, dict) else None
        later = [tc for tc in saves if tc.success and isinstance(tc.arguments, dict)
                 and tc.arguments.get("field_id") == fid and (tc.offset_s or 0) >= (bad.offset_s or 0)]
        fixed += int(bool(later))

    total_tools = len(data.tool_calls)
    return AccuracySection(
        field_accuracy=round(correct / reviewed, 4) if reviewed else None,
        completion=round(required_filled / required_total, 4) if required_total else None,
        filled=filled, reviewed=reviewed, correct=correct,
        required_total=required_total, required_filled=required_filled,
        followups_correct=followups_ok, followups_total=followups_total, followup_issues=followup_issues,
        invalid_answers=len(validation_failures), invalid_answers_fixed=fixed,
        corrections_saved=sum(1 for m in mishearings.items if m.kind in ("caller_correction", "value_changed")),
        tool_calls_total=total_tools,
        tool_success_rate=round(sum(tc.success for tc in data.tool_calls) / total_tools, 4) if total_tools else None,
        invalid_tool_calls=sum(1 for tc in data.tool_calls if tc.parse_error),
        validation_errors=sum(1 for tc in data.tool_calls if not tc.success and not tc.parse_error),
        table=rows,
    )


def accuracy_score(acc: AccuracySection) -> float | None:
    """0-100: 60% field accuracy, 25% completion, 15% follow-up correctness (re-weighted if unknown)."""
    parts = []
    if acc.field_accuracy is not None:
        parts.append((0.60, acc.field_accuracy))
    if acc.completion is not None:
        parts.append((0.25, acc.completion))
    if acc.followups_total:
        parts.append((0.15, acc.followups_correct / acc.followups_total))
    if not parts:
        return None
    total_weight = sum(w for w, _ in parts)
    return round(100 * sum(w * v for w, v in parts) / total_weight, 1)
