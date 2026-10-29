"""Simulate mode: replay a saved dummy call without a microphone or Sarvam.

Reads app/simulate/sample_call.json and plays it step by step:
- "agent"/"caller" steps become transcript bubbles,
- "tool" steps run the REAL tool code (validation, follow-ups, completion),
- agent "timing" values become turn metrics (made-up numbers, for the UI only),
- "interruption" counts a barge-in.
The UI receives exactly the same events as in a live call, at no cost.
"""

import asyncio
import json

from loguru import logger

from app.config import SIMULATE_DIR
from app.db import SessionLocal
from app.models import Call, TurnMetric, utcnow
from app.services.events import bus
from app.services.tools import handle_tool_call

SCRIPT_PATH = SIMULATE_DIR / "sample_call.json"


def _update_call(call_id: str, fn):
    with SessionLocal() as db:
        call = db.get(Call, call_id)
        fn(call)
        db.commit()
        return call


def _add_transcript(call_id: str, entry: dict):
    event = bus.publish(call_id, "transcript", entry)
    _update_call(call_id, lambda c: setattr(c, "transcript", [*(c.transcript or []), {**entry, "ts": event["ts"]}]))


async def _run(call_id: str, speed: float):
    steps = json.loads(SCRIPT_PATH.read_text(encoding="utf-8"))["steps"]

    async def pause(ms: float):
        await asyncio.sleep(ms / 1000 / speed)

    def set_status(status: str):
        _update_call(call_id, lambda c: setattr(c, "status", status))
        bus.publish(call_id, "status", {"status": status})

    set_status("connecting")
    await pause(600)
    set_status("listening")
    turn_index, last_caller = 0, None

    for step in steps:
        kind = step["type"]
        if kind == "caller":
            await pause(900)
            last_caller = step
            turn_index += 1
            set_status("thinking")
            _add_transcript(call_id, {"role": "caller", "text": step["text"], "language": step.get("language")})
        elif kind == "tool":
            await pause(150)
            with SessionLocal() as db:
                handle_tool_call(db, call_id, step["name"], step.get("raw_args", step.get("args")))
        elif kind == "interruption":
            call = _update_call(call_id, lambda c: setattr(c, "interruptions", c.interruptions + 1))
            bus.publish(call_id, "counters", {"interruptions": call.interruptions})
            set_status("listening")
        elif kind == "agent":
            timing = step.get("timing", {})
            parts = [timing.get(k) or 0 for k in ("stt_ms", "turn_wait_ms", "llm_ttft_ms", "tts_ttfb_ms")]
            total = sum(parts) + 40  # + a little transport time
            await pause(total)
            metrics = {
                "turn_index": turn_index,
                "stt_ms": timing.get("stt_ms"),
                "turn_wait_ms": timing.get("turn_wait_ms"),
                "llm_ttft_ms": timing.get("llm_ttft_ms"),
                "tts_ttfb_ms": timing.get("tts_ttfb_ms"),
                "total_ms": total,
                "tool_ms": timing.get("tool_ms"),
                "interrupted": bool(step.get("interrupted")),
                "user_text": last_caller["text"] if last_caller and turn_index else None,
                "user_language": last_caller.get("language") if last_caller and turn_index else None,
                "agent_text": step["text"],
            }
            with SessionLocal() as db:
                db.add(TurnMetric(call_id=call_id, **metrics))
                db.commit()
            bus.publish(call_id, "turn_metrics", metrics)
            set_status("speaking")
            _add_transcript(call_id, {"role": "agent", "text": step["text"], "interrupted": bool(step.get("interrupted"))})
            # Rough speaking time: ~60 ms per character.
            await pause(min(4000, 60 * len(step["text"])) if not step.get("interrupted") else 800)
            set_status("listening")

    # Dummy usage so the cost panel shows something.
    def usage(c: Call):
        c.llm_input_tokens, c.llm_output_tokens = 42_000, 1_900
        c.tts_characters = sum(len(s["text"]) for s in steps if s["type"] == "agent")

    call = _update_call(call_id, usage)
    bus.publish(call_id, "usage", {"llm_input_tokens": call.llm_input_tokens,
                                   "llm_output_tokens": call.llm_output_tokens,
                                   "tts_characters": call.tts_characters})
    _update_call(call_id, lambda c: (setattr(c, "status", "ended"), setattr(c, "ended_at", utcnow())))
    bus.publish(call_id, "status", {"status": "ended"})
    bus.publish(call_id, "call_ended", {})
    from app.services.report_hook import schedule_report

    schedule_report(call_id, "call ended")


_tasks: set[asyncio.Task] = set()


def start_simulation(call_id: str, speed: float = 1.0):
    async def runner():
        try:
            await _run(call_id, speed)
        except Exception as e:
            logger.exception("Simulation failed")
            bus.publish(call_id, "error", {"message": f"Simulation error: {e}", "fatal": True})

    task = asyncio.create_task(runner())
    _tasks.add(task)  # keep a reference so the task isn't garbage-collected
    task.add_done_callback(_tasks.discard)
