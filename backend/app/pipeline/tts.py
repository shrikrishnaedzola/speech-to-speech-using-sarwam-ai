"""Step 3: Text-to-speech with Sarvam Bulbul (WebSocket streaming).

Docs: https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/web-socket
      https://docs.sarvam.ai/api/getting-started/models/bulbul

- The WebSocket is opened once when the call starts and kept open (Pipecat
  pings it every 20 s; Sarvam closes idle sockets after 60 s), so no TLS
  handshake per turn.
- min_buffer_size (default 50 chars) is lowered to 30 for faster first audio.
- Output is linear16 PCM at the call's sample rate (8000 in phone mode).
- bulbul:v4-flash has no Malayalam/Odia, so those languages fall back to bulbul:v3.
"""

from pipecat.services.sarvam.tts import SarvamTTSService

from app.config import TTS_VOICES_V3, TTS_VOICES_V4, V4_UNSUPPORTED_LANGUAGES
from app.pipeline.stt import LANGUAGE_ENUMS

DEFAULT_VOICE = {"bulbul:v3": "shubh", "bulbul:v4-flash": "simran_en_customer"}


def resolve_tts_choice(settings: dict) -> tuple[str, str, str | None]:
    """Pick model and voice, applying fallbacks. Returns (model, voice, note)."""
    model, voice, note = settings["tts_model"], settings["tts_voice"], None
    if model == "bulbul:v4-flash" and settings["language"] in V4_UNSUPPORTED_LANGUAGES:
        model = "bulbul:v3"
        note = f"bulbul:v4-flash does not support {settings['language']}; using bulbul:v3."
    valid = TTS_VOICES_V3 if model == "bulbul:v3" else TTS_VOICES_V4
    # v4 has 200+ voices; accept any persona-style id even if not in our short list.
    if voice not in valid and not (model == "bulbul:v4-flash" and "_" in voice):
        voice = DEFAULT_VOICE[model]
        note = (note + " " if note else "") + f"Voice not valid for {model}; using {voice}."
    return model, voice, note


def make_tts(settings: dict, api_key: str, sample_rate: int) -> tuple[SarvamTTSService, str | None]:
    model, voice, note = resolve_tts_choice(settings)
    # In auto-detect mode we start in English (India); the runner switches the TTS
    # language whenever the caller's detected language changes.
    language = LANGUAGE_ENUMS.get(settings["language"], LANGUAGE_ENUMS["en-IN"])
    tts = SarvamTTSService(
        api_key=api_key,
        sample_rate=sample_rate,
        settings=SarvamTTSService.Settings(
            model=model,
            voice=voice,
            language=language,
            pace=float(settings["tts_pace"]),
            min_buffer_size=int(settings["tts_min_buffer_size"]),
        ),
    )
    return tts, note
