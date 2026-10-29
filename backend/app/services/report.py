"""Build the full call report: answers, transcript, turn metrics, scores and cost.

Used by GET /api/calls/{id} and by the JSON/CSV export.
"""

from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Call, ToolCall, TurnMetric
from app.services.tools import FILLED, NEEDS_CONFIRMATION, form_state


def _avg(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 1) if values else None


def _max(values):
    values = [v for v in values if v is not None]
    return round(max(values), 1) if values else None


def iso_utc(dt: datetime | None) -> str | None:
    """ISO time with a UTC marker (SQLite drops the timezone when storing)."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def call_duration_s(call: Call) -> float:
    start = call.started_at if call.started_at.tzinfo else call.started_at.replace(tzinfo=timezone.utc)
    end = call.ended_at or datetime.now(timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return round((end - start).total_seconds(), 1)


def estimate_cost(settings: dict, duration_s: float, llm_in: int, llm_out: int, tts_chars: int) -> dict:
    """Estimated cost in INR (rates from settings, editable in the UI).

    STT is billed per minute of streamed audio. The browser streams audio for
    the whole call, so call duration is used as the STT minutes estimate.
    """
    tts_rate = (
        settings["rate_tts_v4_per_10k_chars"]
        if settings.get("tts_model") == "bulbul:v4-flash"
        else settings["rate_tts_v3_per_10k_chars"]
    )
    stt = duration_s / 60 * settings["rate_stt_per_min"]
    llm = llm_in / 1e6 * settings["rate_llm_input_per_1m"] + llm_out / 1e6 * settings["rate_llm_output_per_1m"]
    tts = tts_chars / 10_000 * tts_rate
    return {
        "currency": "INR",
        "stt": round(stt, 4),
        "llm": round(llm, 4),
        "tts": round(tts, 4),
        "total": round(stt + llm + tts, 4),
    }


def scores(fields: list[dict]) -> dict:
    """Accuracy = correct / reviewed filled fields. Completion = filled required / visible required."""
    filled = [f for f in fields if f["visible"] and f["status"] in (FILLED, NEEDS_CONFIRMATION)]
    reviewed = [f for f in filled if f["review"]]
    correct = [f for f in reviewed if f["review"]["verdict"] == "correct"]
    required = [f for f in fields if f["visible"] and f["required"]]
    required_filled = [f for f in required if f["status"] == FILLED]
    return {
        "filled_fields": len(filled),
        "reviewed_fields": len(reviewed),
        "correct_fields": len(correct),
        # Accuracy uses reviewed fields only, so unreviewed answers don't count as wrong.
        "accuracy": round(len(correct) / len(reviewed), 3) if reviewed else None,
        "required_total": len(required),
        "required_filled": len(required_filled),
        "completion": round(len(required_filled) / len(required), 3) if required else None,
    }


def turn_dict(t: TurnMetric) -> dict:
    return {
        "turn_index": t.turn_index,
        "stt_ms": t.stt_ms,
        "llm_ttft_ms": t.llm_ttft_ms,
        "tts_ttfb_ms": t.tts_ttfb_ms,
        "total_ms": t.total_ms,
        "turn_wait_ms": t.turn_wait_ms,
        "tool_ms": t.tool_ms,
        "user_text": t.user_text,
        "agent_text": t.agent_text,
        "user_language": t.user_language,
        "interrupted": t.interrupted,
    }


def build_report(db: Session, call_id: str) -> dict | None:
    call = db.get(Call, call_id)
    if call is None:
        return None
    state = form_state(db, call_id)
    turns = db.scalars(select(TurnMetric).where(TurnMetric.call_id == call_id).order_by(TurnMetric.turn_index)).all()
    tools = db.scalars(select(ToolCall).where(ToolCall.call_id == call_id).order_by(ToolCall.id)).all()
    duration = call_duration_s(call)
    # Response-time stats use caller turns only (the greeting has no caller turn).
    caller_turns = [t for t in turns if t.stt_ms is not None]
    return {
        "call": {
            "call_id": call.id,
            "pipeline": "sarvam",
            "mode": call.mode,
            "status": call.status,
            "form_id": state["form_id"],
            "form_name": state["form_name"],
            "started_at": iso_utc(call.started_at),
            "ended_at": iso_utc(call.ended_at),
            "duration_s": duration,
            "form_completed": call.form_completed,
        },
        "settings": call.settings,
        "form": state,
        "transcript": call.transcript or [],
        "turns": [turn_dict(t) for t in turns],
        "tool_calls": [
            {"name": t.name, "arguments": t.arguments, "success": t.success, "result": t.result,
             "duration_ms": t.duration_ms, "created_at": iso_utc(t.created_at)}
            for t in tools
        ],
        "metrics": {
            "turns": len(turns),
            "interruptions": call.interruptions,
            "duration_s": duration,
            "avg_response_ms": _avg([t.total_ms for t in caller_turns]),
            "max_response_ms": _max([t.total_ms for t in caller_turns]),
            "avg_stt_ms": _avg([t.stt_ms for t in caller_turns]),
            "avg_llm_ttft_ms": _avg([t.llm_ttft_ms for t in turns]),
            "avg_tts_ttfb_ms": _avg([t.tts_ttfb_ms for t in turns]),
            "tool_calls": len(tools),
            "tool_calls_failed": sum(1 for t in tools if not t.success),
            "json_parse_failures": call.json_parse_failures,
            "llm_input_tokens": call.llm_input_tokens,
            "llm_output_tokens": call.llm_output_tokens,
            "tts_characters": call.tts_characters,
            **scores(state["fields"]),
            "cost": estimate_cost(
                call.settings, duration, call.llm_input_tokens, call.llm_output_tokens, call.tts_characters
            ),
        },
        "errors": call.errors or [],
    }
