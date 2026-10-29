"""Request bodies for the API (pydantic)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CallSettings(BaseModel):
    """Everything the tester can choose in Column 1 and the Settings panel."""

    stt_model: Literal["saaras:v3-realtime", "saaras:v4"] = "saaras:v3-realtime"
    llm_model: Literal["sarvam-105b-conversations", "sarvam-105b"] = "sarvam-105b-conversations"
    tts_model: Literal["bulbul:v3", "bulbul:v4-flash"] = "bulbul:v3"
    tts_voice: str = "shubh"
    language: str = "auto"
    audio_quality: Literal["normal", "phone"] = "normal"
    stt_stream_type: Literal["fast", "balanced"] = "fast"
    turn_stop_timeout_ms: int = Field(70, ge=0, le=2000)
    vad_silence_ms: int = Field(500, ge=100, le=3000)
    reasoning: Literal["off", "low"] = "off"
    llm_max_tokens: int = Field(400, ge=50, le=4096)
    tts_pace: float = Field(1.0, ge=0.5, le=2.0)
    tts_min_buffer_size: int = Field(30, ge=1, le=200)
    record_agent_audio: bool = True  # agent voice only, for the report's speech-quality score
    rate_stt_per_min: float = 0.49
    rate_tts_v3_per_10k_chars: float = 30.0
    rate_tts_v4_per_10k_chars: float = 10.0
    rate_llm_input_per_1m: float = 15.0
    rate_llm_output_per_1m: float = 60.0


class SessionRequest(BaseModel):
    form_id: str
    settings: CallSettings = CallSettings()


class SimulateRequest(BaseModel):
    form_id: str
    settings: CallSettings = CallSettings()
    speed: float = Field(1.0, gt=0, le=20)  # 2.0 = twice as fast


class ToolRequest(BaseModel):
    call_id: str
    arguments: Any = None  # dict or JSON string, exactly as an LLM would send it


class ReviewItem(BaseModel):
    field_id: str
    verdict: Literal["correct", "wrong"] | None = None  # None removes the mark
    expected_value: str | None = None


class ReviewRequest(BaseModel):
    reviews: list[ReviewItem]
