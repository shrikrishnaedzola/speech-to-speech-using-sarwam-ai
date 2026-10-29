"""Per-turn timing, live transcript and call status, measured from pipeline frames.

A Pipecat observer sees every frame that moves through the pipeline, with a
timestamp (ns). For each turn we record these moments:

    t_user_stop    Sarvam VAD says the caller stopped speaking (vad.speech_end)
    t_transcript   final transcript arrives                      -> STT time
    t_llm_start    LLM request sent (after the turn-stop wait)    -> turn wait
    t_llm_text     first LLM text token                          -> LLM time to first token
    t_tts_audio    first TTS audio chunk                         -> TTS time to first audio
    t_bot_start    agent audio starts playing                    -> Total

    stt_ms      = t_transcript - t_user_stop
    llm_ttft_ms = t_llm_text   - t_llm_start   (includes tool calls in that turn; see tool_ms)
    tts_ttfb_ms = t_tts_audio  - t_llm_text    (includes waiting for TTS min_buffer_size chars)
    total_ms    = t_bot_start  - t_user_stop
    turn_wait_ms= t_llm_start  - t_transcript  (the configurable turn-stop timeout)

Note: Sarvam sends vad.speech_end after its silence window (vad_silence_ms), so
the caller actually went quiet that much earlier. That window is a setting,
shown in the UI next to the totals, and is not part of total_ms.

Turn 0 is the agent's greeting (no caller speech, so no STT time).
"""

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    MetricsFrame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed

from app.db import SessionLocal
from app.models import Call, TurnMetric
from app.services.events import bus


def _ms(later, earlier):
    """Difference of two ns timestamps in ms, or None if either is missing."""
    if later is None or earlier is None:
        return None
    return round(max(0, later - earlier) / 1e6, 1)


class Turn:
    def __init__(self, index: int):
        self.index = index
        self.t_user_stop = self.t_transcript = self.t_llm_start = None
        self.t_llm_text = self.t_tts_audio = self.t_bot_start = None
        self.user_text: list[str] = []
        self.user_language: str | None = None
        self.agent_text: list[str] = []
        self.tool_ms = 0.0
        self.interrupted = False
        self.saved = False

    def timings(self) -> dict:
        start = self.t_user_stop if self.t_user_stop is not None else self.t_llm_start
        return {
            "turn_index": self.index,
            "stt_ms": _ms(self.t_transcript, self.t_user_stop),
            "turn_wait_ms": _ms(self.t_llm_start, self.t_transcript),
            "llm_ttft_ms": _ms(self.t_llm_text, self.t_llm_start),
            "tts_ttfb_ms": _ms(self.t_tts_audio, self.t_llm_text),
            "total_ms": _ms(self.t_bot_start, start),
            "tool_ms": round(self.tool_ms, 1) if self.tool_ms else None,
            "interrupted": self.interrupted,
            "user_text": " ".join(self.user_text) or None,
            "user_language": self.user_language,
            "agent_text": "".join(self.agent_text).strip() or None,
        }


class CallObserver(BaseObserver):
    """Turns pipeline frames into turn metrics, transcript bubbles, status and counters."""

    def __init__(self, call_id: str, on_language_detected=None):
        # Only the first push of each frame, so a frame passing many processors counts once.
        super().__init__(observe_every_push=False)
        self.call_id = call_id
        self.turn = Turn(0)  # greeting
        self.bot_speaking = False
        self.interrupted_this_reply = False
        self.on_language_detected = on_language_detected
        self._agent_reply: list[str] = []

    # --- helpers ---------------------------------------------------------

    def _status(self, status: str):
        bus.publish(self.call_id, "status", {"status": status})

    def _update_call(self, fn):
        with SessionLocal() as db:
            call = db.get(Call, self.call_id)
            fn(call)
            db.commit()
            return call

    def _add_transcript(self, entry: dict):
        event = bus.publish(self.call_id, "transcript", entry)
        entry = {**entry, "ts": event["ts"]}
        self._update_call(lambda c: setattr(c, "transcript", [*(c.transcript or []), entry]))

    def add_tool_time(self, ms: float):
        self.turn.tool_ms += ms

    def _save_turn(self):
        """Store the current turn (once) and publish its final numbers."""
        t = self.turn
        if t.t_bot_start is None and t.t_user_stop is None:
            return  # nothing happened in this turn
        data = t.timings()
        with SessionLocal() as db:
            row = db.query(TurnMetric).filter_by(call_id=self.call_id, turn_index=t.index).one_or_none()
            if row is None:
                row = TurnMetric(call_id=self.call_id, turn_index=t.index)
                db.add(row)
            for key, value in data.items():
                if key != "turn_index":
                    setattr(row, key, value)
            db.commit()
        t.saved = True
        bus.publish(self.call_id, "turn_metrics", data)

    def finish(self):
        """Call end: save the last turn."""
        self._save_turn()

    # --- frame handling --------------------------------------------------

    async def on_push_frame(self, data: FramePushed):
        frame, ts = data.frame, data.timestamp
        t = self.turn

        if isinstance(frame, (ProposedUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
            if self.bot_speaking and not self.interrupted_this_reply:
                # Caller spoke over the agent: a barge-in.
                self.interrupted_this_reply = True
                t.interrupted = True
                call = self._update_call(lambda c: setattr(c, "interruptions", c.interruptions + 1))
                bus.publish(self.call_id, "counters", {"interruptions": call.interruptions})

        elif isinstance(frame, (ProposedUserStoppedSpeakingFrame, UserStoppedSpeakingFrame)):
            if t.t_bot_start is not None or (t.index == 0 and t.t_user_stop is None):
                # Previous turn is finished: store it and start a new caller turn.
                self._save_turn()
                self.turn = t = Turn(t.index + 1)
            if t.t_user_stop is None or t.t_llm_start is not None:
                # First stop of this turn, or the caller spoke again before the agent replied.
                t.t_user_stop = ts
            self._status("thinking")

        elif isinstance(frame, InterimTranscriptionFrame):
            bus.publish(self.call_id, "transcript_partial", {"role": "caller", "text": frame.text})

        elif isinstance(frame, TranscriptionFrame):
            t.t_transcript = ts
            t.user_text.append(frame.text)
            language = str(frame.language) if frame.language else None
            t.user_language = language
            self._add_transcript({"role": "caller", "text": frame.text, "language": language})
            if language and self.on_language_detected:
                await self.on_language_detected(language)

        elif isinstance(frame, LLMFullResponseStartFrame):
            if t.t_llm_start is None:
                t.t_llm_start = ts
            self._agent_reply = []

        elif isinstance(frame, LLMTextFrame):
            if t.t_llm_text is None:
                t.t_llm_text = ts
            t.agent_text.append(frame.text)
            self._agent_reply.append(frame.text)
            bus.publish(self.call_id, "transcript_partial", {"role": "agent", "text": "".join(self._agent_reply)})

        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._agent_reply).strip()
            if text:
                self._add_transcript({"role": "agent", "text": text, "interrupted": self.interrupted_this_reply})
            self._agent_reply = []

        elif isinstance(frame, TTSAudioRawFrame):
            if t.t_tts_audio is None:
                t.t_tts_audio = ts

        elif isinstance(frame, BotStartedSpeakingFrame):
            if not self.bot_speaking:
                self.bot_speaking = True
                self.interrupted_this_reply = False
                self._status("speaking")
                if t.t_bot_start is None:
                    t.t_bot_start = ts
                    # Publish provisional timings now so the bar appears immediately.
                    bus.publish(self.call_id, "turn_metrics", t.timings())

        elif isinstance(frame, BotStoppedSpeakingFrame):
            if self.bot_speaking:
                self.bot_speaking = False
                self._status("listening")

        elif isinstance(frame, InterruptionFrame):
            if self.bot_speaking:
                self.bot_speaking = False
                self._status("listening")

        elif isinstance(frame, MetricsFrame):
            self._handle_usage(frame)

        elif isinstance(frame, ErrorFrame):
            message = str(frame.error)
            bus.publish(self.call_id, "error", {"message": message, "fatal": bool(getattr(frame, "fatal", False))})
            self._update_call(lambda c: setattr(c, "errors", [*(c.errors or []), message]))

    def _handle_usage(self, frame: MetricsFrame):
        tokens_in = tokens_out = chars = 0
        for item in frame.data:
            if isinstance(item, LLMUsageMetricsData):
                tokens_in += item.value.prompt_tokens
                tokens_out += item.value.completion_tokens
            elif isinstance(item, TTSUsageMetricsData):
                chars += item.value
        if not (tokens_in or tokens_out or chars):
            return

        def add(c: Call):
            c.llm_input_tokens += tokens_in
            c.llm_output_tokens += tokens_out
            c.tts_characters += chars

        call = self._update_call(add)
        bus.publish(
            self.call_id,
            "usage",
            {"llm_input_tokens": call.llm_input_tokens, "llm_output_tokens": call.llm_output_tokens,
             "tts_characters": call.tts_characters},
        )
