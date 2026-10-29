"""Adapter for the Sarvam tester's SQLite database -> CallData.

Reads the tester's tables with plain SQL (no import of the tester's code), so
the report module stays independent:
    forms, calls, answers, reviews, turn_metrics, tool_calls

Usage (in the Sarvam backend):
    adapter = sarvam_adapter(engine, recordings_dir="data/recordings", scripts_dir="data/scenarios")
"""

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from report_module.adapters.base import as_utc, load_expected_script, seconds_since
from report_module.schema import CallData


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def sarvam_adapter(engine: Engine, recordings_dir: str | Path | None = None, scripts_dir: str | Path | None = None):
    def adapter(call_id: str) -> CallData | None:
        with engine.connect() as conn:
            call = conn.execute(text("SELECT * FROM calls WHERE id = :id"), {"id": call_id}).mappings().first()
            if call is None:
                return None
            form = _json(conn.execute(text("SELECT definition FROM forms WHERE id = :id"),
                                      {"id": call["form_id"]}).scalar())
            rows = lambda sql: [dict(r) for r in conn.execute(text(sql), {"id": call_id}).mappings()]  # noqa: E731
            answers = rows("SELECT * FROM answers WHERE call_id = :id")
            reviews = rows("SELECT * FROM reviews WHERE call_id = :id")
            turns = rows("SELECT * FROM turn_metrics WHERE call_id = :id ORDER BY turn_index")
            tools = rows("SELECT * FROM tool_calls WHERE call_id = :id ORDER BY id")

        settings = _json(call["settings"]) or {}
        started = as_utc(call["started_at"])
        ended = as_utc(call["ended_at"])
        duration = (ended - started).total_seconds() if ended else 0
        minutes = round(duration / 60, 4)

        transcript = [
            {"role": e["role"], "text": e["text"], "offset_s": seconds_since(started, e.get("ts")) or 0,
             "language": e.get("language"), "interrupted": bool(e.get("interrupted"))}
            for e in (_json(call["transcript"]) or [])
        ]
        tool_calls = []
        for t in tools:
            result = _json(t["result"]) or {}
            error = result.get("error") or ""
            tool_calls.append({
                "name": t["name"], "arguments": _json(t["arguments"]), "success": bool(t["success"]), "result": result,
                "duration_ms": t["duration_ms"], "offset_s": seconds_since(started, t["created_at"]),
                # The Sarvam tester reports broken JSON as "Invalid arguments for <tool>: ..."
                "parse_error": error.startswith("Invalid arguments"),
            })

        recording = Path(recordings_dir) / f"{call_id}.wav" if recordings_dir else None
        return CallData.model_validate({
            "call": {
                "call_id": call["id"], "provider": "sarvam", "model": settings.get("llm_model", "sarvam"),
                "models": {k: settings[f"{k}_model"] for k in ("stt", "llm", "tts") if settings.get(f"{k}_model")},
                "voice": settings.get("tts_voice"), "language_selected": settings.get("language", "auto"),
                "audio_mode": "phone_8khz" if settings.get("audio_quality") == "phone" else "normal",
                "started_at": started, "ended_at": ended, "duration_s": round(duration, 1),
                "form_id": form.get("id"), "form_name": form.get("name"), "mode": call["mode"],
            },
            "form_fields": [{k: f.get(k) for k in ("id", "label", "type", "required", "show_if")} for f in form["fields"]],
            "transcript": transcript,
            "answers": [{"field_id": a["field_id"], "value": _json(a["value"]), "status": a["status"],
                         "confidence": a["confidence"], "attempts": a["attempts"]} for a in answers],
            "reviews": [{"field_id": r["field_id"], "verdict": r["verdict"], "expected_value": r["expected_value"]}
                        for r in reviews],
            "turns": [{k: t[k] for k in ("turn_index", "total_ms", "stt_ms", "turn_wait_ms", "llm_ttft_ms",
                                         "tts_ttfb_ms", "tool_ms", "user_text", "agent_text")}
                      | {"interrupted": bool(t["interrupted"])} for t in turns],
            "tool_calls": tool_calls,
            "usage": {"call_minutes": minutes, "stt_minutes": minutes, "llm_input_tokens": call["llm_input_tokens"],
                      "llm_output_tokens": call["llm_output_tokens"], "tts_characters": call["tts_characters"],
                      "tts_model": settings.get("tts_model")},
            "interruptions": call["interruptions"],
            "form_completed": bool(call["form_completed"]),
            "recording_path": str(recording) if recording and recording.exists() else None,
            "expected_script": load_expected_script(scripts_dir, call_id),
            "errors": _json(call["errors"]) or [],
        })

    return adapter
