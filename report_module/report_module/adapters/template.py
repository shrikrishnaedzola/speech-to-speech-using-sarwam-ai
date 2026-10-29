"""TEMPLATE: copy this file to write the adapter for another tester (OpenAI, Gemini, ElevenLabs).

An adapter is one function: call_id -> CallData (or None if the call does not exist).
Fill each field from your tester's own tables. Leave out what you do not have:
every field except `call` has a safe default.

Checklist:
- offset_s everywhere = seconds since the call started (transcript, tool calls).
- TurnTiming.total_ms = caller stops speaking -> first agent audio. Turn 0 = greeting.
- ToolCallRecord.parse_error = True when the model sent invalid JSON arguments.
- Usage: speech-to-speech providers fill audio_input_tokens / audio_output_tokens;
  ElevenLabs fills call_minutes. cost.py picks the right fields per provider.
- If your tester saves agent audio, set recording_path (16-bit PCM WAV) for the MOS score.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from report_module.adapters.base import as_utc, seconds_since
from report_module.schema import CallData


def my_tester_adapter(engine: Engine):
    def adapter(call_id: str) -> CallData | None:
        with engine.connect() as conn:
            call = conn.execute(text("SELECT * FROM calls WHERE id = :id"), {"id": call_id}).mappings().first()
            if call is None:
                return None
            # ... read transcript, answers, reviews, turn timings, tool calls, usage ...

        started = as_utc(call["started_at"])
        return CallData.model_validate({
            "call": {
                "call_id": call_id,
                "provider": "openai",  # openai / gemini / elevenlabs
                "model": "MODEL-NAME",
                "language_selected": "auto",
                "audio_mode": "normal",  # or "phone_8khz"
                "started_at": started,
                "ended_at": as_utc(call["ended_at"]),
                "duration_s": 0,
            },
            "form_fields": [],  # [{"id", "label", "type", "required", "show_if"}]
            "transcript": [],  # [{"role": "caller"/"agent", "text", "offset_s": seconds_since(started, ts), "language"}]
            "answers": [],  # [{"field_id", "value", "status", "confidence", "attempts"}]
            "reviews": [],  # [{"field_id", "verdict": "correct"/"wrong", "expected_value"}]
            "turns": [],  # [{"turn_index", "total_ms"}]
            "tool_calls": [],  # [{"name", "arguments", "success", "result", "duration_ms", "offset_s", "parse_error"}]
            "usage": {},  # see schema.Usage
            "interruptions": 0,
            "form_completed": False,
        })

    return adapter


__all__ = ["my_tester_adapter", "seconds_since"]
