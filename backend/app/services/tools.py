"""The four voice-agent tools: save_answer, request_clarification, skip_field, complete_form.

Used by both the live pipeline (LLM function calls) and POST /api/tools/{name}
(Simulate mode and tests), so behaviour is identical everywhere.

Every result is a small dict that goes back to the LLM:
    {"ok": True, ...}                      -> carry on
    {"ok": False, "error": "...", ...}     -> the agent should re-ask / fix it
After each call the full form state is published to the UI.
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Answer, Call, Form, Review, ToolCall, utcnow
from app.services.conditions import dependents_of, is_visible
from app.services.events import bus
from app.services.tool_schema import parse_tool_arguments
from app.services.validation import validate_value

TOOL_NAMES = ["save_answer", "request_clarification", "skip_field", "complete_form"]

# Statuses shown on the form cards.
PENDING, FILLED, NEEDS_CONFIRMATION, SKIPPED = "pending", "filled", "needs_confirmation", "skipped"


def get_form(db: Session, call: Call) -> dict:
    return db.get(Form, call.form_id).definition


def _answers(db: Session, call_id: str) -> dict[str, Answer]:
    rows = db.scalars(select(Answer).where(Answer.call_id == call_id)).all()
    return {a.field_id: a for a in rows}


def filled_values(answers: dict[str, Answer]) -> dict:
    """field_id -> value for answers that count as given (filled or needs confirmation)."""
    return {fid: a.value for fid, a in answers.items() if a.status in (FILLED, NEEDS_CONFIRMATION)}


def _get_or_create(db: Session, answers: dict[str, Answer], call_id: str, field_id: str) -> Answer:
    if field_id not in answers:
        answers[field_id] = Answer(call_id=call_id, field_id=field_id, status=PENDING, attempts=0)
        db.add(answers[field_id])
    return answers[field_id]


def next_question(form: dict, answers: dict[str, Answer]) -> dict | None:
    """The first visible field that still needs an answer (a hint for the LLM)."""
    values = filled_values(answers)
    for f in form["fields"]:
        a = answers.get(f["id"])
        if is_visible(f, values) and (a is None or a.status in (PENDING, NEEDS_CONFIRMATION)):
            return {"field_id": f["id"], "question": f.get("question", f["label"])}
    return None


def form_state(db: Session, call_id: str) -> dict:
    """Everything the Form Data column needs: one entry per field."""
    call = db.get(Call, call_id)
    form = get_form(db, call)
    answers = _answers(db, call_id)
    reviews = {r.field_id: r for r in db.scalars(select(Review).where(Review.call_id == call_id)).all()}
    values = filled_values(answers)
    fields = []
    for f in form["fields"]:
        a, r = answers.get(f["id"]), reviews.get(f["id"])
        fields.append(
            {
                "id": f["id"],
                "label": f["label"],
                "type": f["type"],
                "required": f.get("required", False),
                "conditional": "show_if" in f,
                "visible": is_visible(f, values),
                "status": a.status if a else PENDING,
                "value": a.value if a else None,
                "confidence": a.confidence if a else None,
                "note": a.note if a else None,
                "attempts": a.attempts if a else 0,
                "review": {"verdict": r.verdict, "expected_value": r.expected_value} if r else None,
            }
        )
    return {"form_id": form["id"], "form_name": form["name"], "completed": call.form_completed, "fields": fields}


def _recheck_dependents(db: Session, form: dict, answers: dict[str, Answer], changed_field: str):
    """After an answer changes, re-check follow-ups that depend on it.

    Example: number_of_children changes from 2 to 3 -> children_ages (2 values)
    no longer matches, so it is marked "needs confirmation".
    """
    values = filled_values(answers)
    for dep in dependents_of(form, changed_field):
        a = answers.get(dep["id"])
        if a is None or a.status not in (FILLED, NEEDS_CONFIRMATION):
            continue
        if not is_visible(dep, values):
            continue  # hidden follow-ups are ignored in completion and exports
        check = validate_value(dep, a.value, {k: v for k, v in values.items() if k != dep["id"]})
        if not check.ok:
            a.status, a.note, a.updated_at = NEEDS_CONFIRMATION, check.error, utcnow()


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


def save_answer(db: Session, call: Call, form: dict, args: dict) -> dict:
    field = next((f for f in form["fields"] if f["id"] == args["field_id"]), None)
    if field is None:
        return {"ok": False, "error": f"Unknown field_id '{args['field_id']}'."}
    answers = _answers(db, call.id)
    values = filled_values(answers)
    if not is_visible(field, values):
        return {
            "ok": False,
            "error": f"'{field['id']}' does not apply because of earlier answers. Do not ask it.",
            "next_question": next_question(form, answers),
        }

    answer = _get_or_create(db, answers, call.id, field["id"])
    answer.attempts += 1
    answer.raw_value = args["value"]
    answer.updated_at = utcnow()
    check = validate_value(field, args["value"], {k: v for k, v in values.items() if k != field["id"]})
    if not check.ok:
        answer.note = check.error
        db.commit()
        return {"ok": False, "error": check.error, "field_id": field["id"]}

    answer.value = check.value
    answer.confidence = args.get("confidence", "high")
    answer.status = FILLED if answer.confidence == "high" else NEEDS_CONFIRMATION
    answer.note = None if answer.status == FILLED else "Low confidence - please confirm."
    _recheck_dependents(db, form, answers, field["id"])
    db.commit()
    return {
        "ok": True,
        "saved": {field["id"]: check.value},
        "status": answer.status,
        "next_question": next_question(form, answers),
    }


def request_clarification(db: Session, call: Call, form: dict, args: dict) -> dict:
    if not any(f["id"] == args["field_id"] for f in form["fields"]):
        return {"ok": False, "error": f"Unknown field_id '{args['field_id']}'."}
    answers = _answers(db, call.id)
    answer = _get_or_create(db, answers, call.id, args["field_id"])
    answer.status, answer.note, answer.updated_at = NEEDS_CONFIRMATION, args["reason"], utcnow()
    db.commit()
    return {"ok": True, "message": "Marked as needs confirmation. Ask the caller to repeat or confirm."}


def skip_field(db: Session, call: Call, form: dict, args: dict) -> dict:
    field = next((f for f in form["fields"] if f["id"] == args["field_id"]), None)
    if field is None:
        return {"ok": False, "error": f"Unknown field_id '{args['field_id']}'."}
    if field.get("required"):
        return {"ok": False, "error": f"'{field['id']}' is required and cannot be skipped. Ask it politely."}
    answers = _answers(db, call.id)
    answer = _get_or_create(db, answers, call.id, field["id"])
    answer.status, answer.value, answer.note, answer.updated_at = SKIPPED, None, args["reason"], utcnow()
    db.commit()
    return {"ok": True, "next_question": next_question(form, answers)}


def missing_required(form: dict, answers: dict[str, Answer]) -> list[dict]:
    """Visible required fields that are not filled yet (needs-confirmation counts as missing)."""
    values = filled_values(answers)
    missing = []
    for f in form["fields"]:
        if not f.get("required") or not is_visible(f, values):
            continue
        a = answers.get(f["id"])
        if a is None or a.status != FILLED:
            missing.append(
                {
                    "field_id": f["id"],
                    "question": f.get("question", f["label"]),
                    "status": a.status if a else PENDING,
                }
            )
    return missing


def complete_form(db: Session, call: Call, form: dict, args: dict) -> dict:
    missing = missing_required(form, _answers(db, call.id))
    if missing:
        return {
            "ok": False,
            "error": "Some required answers are missing or not confirmed. Ask these, one at a time.",
            "missing_fields": missing,
        }
    call.form_completed = True
    db.commit()
    return {"ok": True, "message": "Form complete. Thank the caller warmly and say goodbye."}


HANDLERS = {
    "save_answer": save_answer,
    "request_clarification": request_clarification,
    "skip_field": skip_field,
    "complete_form": complete_form,
}


def handle_tool_call(db: Session, call_id: str, name: str, raw_args) -> dict:
    """Parse, run and log one tool call, then publish the new form state.

    Args:
        db: Database session.
        call_id: The call this tool call belongs to.
        name: Tool name.
        raw_args: Arguments as a dict or JSON string, exactly as the LLM sent them.
    """
    start = time.perf_counter()
    call = db.get(Call, call_id)
    if call is None:
        return {"ok": False, "error": f"Unknown call '{call_id}'."}
    form = get_form(db, call)

    args, parse_error = parse_tool_arguments(name, raw_args, [f["id"] for f in form["fields"]])
    if parse_error:
        call.json_parse_failures += 1
        result = {"ok": False, "error": f"Invalid arguments for {name}: {parse_error} Call it again with valid JSON."}
    else:
        result = HANDLERS[name](db, call, form, args)

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    db.add(
        ToolCall(
            call_id=call_id,
            name=name,
            arguments=args if args is not None else raw_args,
            success=bool(result.get("ok")),
            result=result,
            duration_ms=duration_ms,
        )
    )
    db.commit()

    bus.publish(
        call_id,
        "tool_call",
        {"name": name, "arguments": args if args is not None else raw_args, "success": bool(result.get("ok")),
         "result": result, "duration_ms": duration_ms, "parse_error": parse_error},
    )
    bus.publish(call_id, "form_state", form_state(db, call_id))
    if parse_error:
        bus.publish(call_id, "counters", {"json_parse_failures": call.json_parse_failures})
    if name == "complete_form" and result.get("ok"):
        from app.services.report_hook import schedule_report  # late import: avoids an import cycle

        schedule_report(call_id, "form completed")
    return result
