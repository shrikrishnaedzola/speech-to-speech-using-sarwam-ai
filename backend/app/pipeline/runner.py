"""Runs one voice call: browser WebRTC audio -> STT -> LLM (+tools) -> TTS -> browser.

Pipeline order (Pipecat):
    transport.input -> Sarvam STT -> user context -> Sarvam LLM -> Sarvam TTS
    -> transport.output -> assistant context

The browser connects with plain WebRTC (SmallWebRTCTransport runs inside this
FastAPI process, no extra media server). Live UI updates go over a separate
WebSocket (services/events.py), fed by the CallObserver.
"""

import asyncio
import json
import time
import wave

import pipecat.services.openai.base_llm as _openai_base_llm
from loguru import logger
from pipecat.frames.frames import LLMRunFrame, TTSUpdateSettingsFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app.config import SARVAM_API_KEY, V4_UNSUPPORTED_LANGUAGES
from app.db import SessionLocal
from app.models import Call, Form, utcnow
from app.pipeline.llm import make_llm
from app.pipeline.metrics import CallObserver
from app.pipeline.prompt import build_system_prompt
from app.pipeline.stt import make_stt, make_turn_strategies
from app.pipeline.tts import make_tts
from app.services.events import bus
from app.services.report_hook import RECORDINGS_DIR, schedule_report
from app.services.tool_schema import pipecat_tools
from app.services.tools import TOOL_NAMES, handle_tool_call

# call_id -> running pipeline worker, so "End Call" can stop it.
ACTIVE_CALLS: dict[str, PipelineWorker] = {}
# call_id -> agent-audio recorder, stopped before the pipeline so the last turn is kept.
ACTIVE_RECORDERS: dict[str, AudioBufferProcessor] = {}

# ---------------------------------------------------------------------------
# Keep malformed tool-call JSON instead of dropping it.
# Pipecat's OpenAI-compatible LLM service silently skips a tool call whose
# arguments are not valid JSON, so the agent would get no answer and we could
# not count it. This wrapper (only for that module) returns the raw text under
# RAW_ARGS_KEY; our parser then counts the failure and tells the LLM to retry.
# ---------------------------------------------------------------------------
RAW_ARGS_KEY = "__raw_arguments__"


class _KeepRawJSON:
    JSONDecodeError = json.JSONDecodeError

    def __getattr__(self, name):
        return getattr(json, name)

    @staticmethod
    def loads(text, *args, **kwargs):
        try:
            return json.loads(text, *args, **kwargs)
        except json.JSONDecodeError:
            return {RAW_ARGS_KEY: text}


_openai_base_llm.json = _KeepRawJSON()


def _sample_rate(settings: dict) -> int:
    """Phone mode = 8 kHz both ways (like a real phone line), else 16 kHz."""
    return 8000 if settings["audio_quality"] == "phone" else 16000


async def run_call(webrtc_connection, call_id: str):
    """Build and run the pipeline for one call. Returns when the call ends."""
    with SessionLocal() as db:
        call = db.get(Call, call_id)
        settings = dict(call.settings)
        form = db.get(Form, call.form_id).definition

    rate = _sample_rate(settings)
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=rate,
            audio_out_sample_rate=rate,
        ),
    )

    stt = make_stt(settings, SARVAM_API_KEY, rate)
    llm = make_llm(settings, SARVAM_API_KEY)
    tts, tts_note = make_tts(settings, SARVAM_API_KEY, rate)
    if tts_note:
        bus.publish(call_id, "log", {"message": tts_note})

    # Auto-detect mode: switch the TTS language when the caller's language changes.
    tts_language = {"current": "en-IN" if settings["language"] == "auto" else settings["language"]}

    async def on_language_detected(language: str):
        if settings["language"] != "auto" or language == tts_language["current"]:
            return
        if settings["tts_model"] == "bulbul:v4-flash" and language in V4_UNSUPPORTED_LANGUAGES:
            return
        try:
            lang_enum = Language(language)
        except ValueError:
            return
        tts_language["current"] = language
        await worker.queue_frame(TTSUpdateSettingsFrame(delta=SarvamTTSService.Settings(language=lang_enum)))
        bus.publish(call_id, "log", {"message": f"TTS language switched to {language}"})

    observer = CallObserver(call_id, on_language_detected=on_language_detected)

    # --- tools: the LLM calls these; results go back to the LLM ---
    async def tool_handler(params: FunctionCallParams):
        raw = params.arguments
        if isinstance(raw, dict) and RAW_ARGS_KEY in raw:
            raw = raw[RAW_ARGS_KEY]  # malformed JSON from the model; the parser will report it
        start = time.perf_counter()
        with SessionLocal() as db:
            result = handle_tool_call(db, call_id, params.function_name, raw)
        observer.add_tool_time((time.perf_counter() - start) * 1000)
        await params.result_callback(result)

    for name in TOOL_NAMES:
        llm.register_function(name, tool_handler)

    context = LLMContext(
        messages=[{"role": "system", "content": build_system_prompt(form, settings["language"])}],
        tools=pipecat_tools([f["id"] for f in form["fields"]]),
    )
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(user_turn_strategies=make_turn_strategies(settings)),
    )

    # Agent-audio recording (dummy test calls only) for the report's optional speech-quality
    # score. Only the agent's speech turns are kept: no caller audio, no silent gaps.
    recorder = AudioBufferProcessor(enable_turn_audio=True) if settings.get("record_agent_audio", True) else None
    agent_audio = bytearray()
    if recorder:
        ACTIVE_RECORDERS[call_id] = recorder

        @recorder.event_handler("on_bot_turn_audio")
        async def on_bot_turn_audio(processor, data):
            agent_audio.extend(data.audio)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            *([recorder] if recorder else []),
            aggregators.assistant(),
        ]
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=rate,
            audio_out_sample_rate=rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[observer],
        enable_rtvi=False,  # UI updates use our own events WebSocket
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, connection):
        _set_status(call_id, "listening")
        if recorder:
            await recorder.start_recording()
        await worker.queue_frames([LLMRunFrame()])  # the agent speaks first (greeting)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, connection):
        await _stop_recorder(call_id)
        await worker.cancel()

    ACTIVE_CALLS[call_id] = worker
    try:
        await PipelineRunner(handle_sigint=False).run(worker)
    except Exception as e:  # keep the server alive; show the error in the UI
        logger.exception(f"Call {call_id} failed")
        bus.publish(call_id, "error", {"message": f"Pipeline error: {e}", "fatal": True})
    finally:
        ACTIVE_CALLS.pop(call_id, None)
        ACTIVE_RECORDERS.pop(call_id, None)
        observer.finish()
        if agent_audio:
            _save_wav(call_id, bytes(agent_audio), rate)
        _end_call_record(call_id)
        schedule_report(call_id, "call ended")


def _save_wav(call_id: str, pcm: bytes, sample_rate: int):
    """Save the agent's speech as 16-bit mono WAV in data/recordings/<call_id>.wav."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with wave.open(str(RECORDINGS_DIR / f"{call_id}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)


async def _stop_recorder(call_id: str):
    """Flush the last agent turn into the recording before the pipeline stops."""
    recorder = ACTIVE_RECORDERS.get(call_id)
    if recorder:
        try:
            await recorder.stop_recording()
        except Exception as e:
            logger.warning(f"Could not stop recorder for {call_id}: {e}")


def _set_status(call_id: str, status: str):
    with SessionLocal() as db:
        call = db.get(Call, call_id)
        call.status = status
        db.commit()
    bus.publish(call_id, "status", {"status": status})


def _end_call_record(call_id: str):
    with SessionLocal() as db:
        call = db.get(Call, call_id)
        call.status, call.ended_at = "ended", utcnow()
        db.commit()
    bus.publish(call_id, "status", {"status": "ended"})
    bus.publish(call_id, "call_ended", {})


async def end_call(call_id: str) -> bool:
    worker = ACTIVE_CALLS.get(call_id)
    if worker is None:
        return False
    await _stop_recorder(call_id)
    await worker.cancel()
    return True


def start_call_task(webrtc_connection, call_id: str) -> asyncio.Task:
    return asyncio.create_task(run_call(webrtc_connection, call_id))
