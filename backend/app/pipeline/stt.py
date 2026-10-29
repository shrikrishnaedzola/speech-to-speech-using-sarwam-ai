"""Step 1: Speech-to-text with Sarvam Saaras (realtime WebSocket).

Docs: https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming
      https://docs.sarvam.ai/api/integration/pipecat-production-guide

Latency settings applied (from the docs):
- stream_type="fast": 500 ms audio chunks ("balanced" = 1000 ms).
- Sarvam's server-side VAD decides when the caller stopped (no local Silero VAD,
  as the Pipecat production guide recommends).
- silence_duration_ms: Sarvam's VAD silence window (default 500), configurable.
- language None -> language_code=auto, so Hinglish / code-mixed speech is detected
  per utterance and each final transcript carries the detected language.
- sample_rate 8000 in phone mode (Sarvam accepts 8 kHz natively).
"""

from pipecat.services.sarvam.stt import SarvamRealtimeSTTService
from pipecat.transcriptions.language import Language
from pipecat.turns.user_start import ExternalUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

# Our dropdown codes -> Pipecat Language values (Pipecat maps them to Sarvam's codes).
LANGUAGE_ENUMS = {
    "en-IN": Language.EN_IN, "hi-IN": Language.HI_IN, "bn-IN": Language.BN_IN, "ta-IN": Language.TA_IN,
    "te-IN": Language.TE_IN, "kn-IN": Language.KN_IN, "ml-IN": Language.ML_IN, "mr-IN": Language.MR_IN,
    "gu-IN": Language.GU_IN, "pa-IN": Language.PA_IN, "od-IN": Language.OR_IN,
}


def make_stt(settings: dict, api_key: str, sample_rate: int) -> SarvamRealtimeSTTService:
    language = None if settings["language"] == "auto" else LANGUAGE_ENUMS[settings["language"]]
    return SarvamRealtimeSTTService(
        api_key=api_key,
        sample_rate=sample_rate,
        settings=SarvamRealtimeSTTService.Settings(
            model=settings["stt_model"],
            language=language,
            stream_type=settings["stt_stream_type"],
            mode="transcribe",
            silence_duration_ms=int(settings["vad_silence_ms"]),
        ),
    )


def make_turn_strategies(settings: dict) -> UserTurnStrategies:
    """Turn-taking driven by Sarvam's VAD events.

    The stop timeout is the short wait after Sarvam says "speech ended" before
    the LLM is called (the "endpointing delay"). Sarvam's LiveKit guide uses
    70 ms; its Pipecat guide uses 200 ms. Configurable in the UI.
    Barge-in: any caller speech start interrupts the agent.
    """
    return UserTurnStrategies(
        start=[ExternalUserTurnStartStrategy(enable_interruptions=True)],
        stop=[ExternalUserTurnStopStrategy(timeout=settings["turn_stop_timeout_ms"] / 1000, wait_for_transcript=True)],
    )
