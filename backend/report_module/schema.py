"""The two fixed data shapes of the report module.

CallData  = INPUT.  Every tester app (OpenAI, Sarvam, Gemini, ElevenLabs) has a
            small adapter that fills this from its own database.
Report    = OUTPUT. Identical for all providers, so the comparison tool can
            import any report JSON directly. Bump SCHEMA_VERSION on any
            breaking change.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

Provider = Literal["openai", "sarvam", "gemini", "elevenlabs"]
Severity = Literal["High", "Medium", "Low"]


# ===========================================================================
# INPUT: CallData
# ===========================================================================


class CallInfo(BaseModel):
    call_id: str
    provider: Provider
    model: str  # main model shown in the report, e.g. "gpt-realtime" or "sarvam-105b-conversations"
    models: dict[str, str] = Field(default_factory=dict)  # optional detail: {"stt": ..., "llm": ..., "tts": ...}
    voice: str | None = None
    language_selected: str = "auto"  # BCP-47 code like "hi-IN", or "auto"
    audio_mode: Literal["normal", "phone_8khz"] = "normal"
    started_at: datetime
    ended_at: datetime | None = None
    duration_s: float = 0
    form_id: str | None = None
    form_name: str | None = None
    mode: Literal["live", "simulate"] = "live"


class FormField(BaseModel):
    id: str
    label: str
    type: str  # text / number / choice / yes_no / number_list
    required: bool = False
    show_if: dict | None = None  # follow-up rule, e.g. {"field": "attended_sessions", "op": "eq", "value": "no"}


class Utterance(BaseModel):
    role: Literal["caller", "agent"]
    text: str
    offset_s: float  # seconds since call start
    language: str | None = None  # detected language (caller turns)
    interrupted: bool = False  # agent turn cut off by the caller


class Answer(BaseModel):
    field_id: str
    value: Any = None
    status: str = "pending"  # pending / filled / needs_confirmation / skipped
    confidence: str | None = None
    attempts: int = 0


class Review(BaseModel):
    field_id: str
    verdict: Literal["correct", "wrong"]
    expected_value: str | None = None


class TurnTiming(BaseModel):
    turn_index: int
    total_ms: float | None = None  # caller stops speaking -> first agent audio
    # Sarvam (cascaded pipeline) only; None for speech-to-speech providers.
    stt_ms: float | None = None
    turn_wait_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None
    tool_ms: float | None = None
    interrupted: bool = False
    user_text: str | None = None
    agent_text: str | None = None


class ToolCallRecord(BaseModel):
    name: str
    arguments: Any = None
    success: bool
    result: Any = None
    duration_ms: float | None = None
    offset_s: float | None = None  # seconds since call start
    parse_error: bool = False  # tool arguments were not valid JSON


class Usage(BaseModel):
    """Raw usage. Each provider fills what it has; cost.py picks the right ones."""

    call_minutes: float = 0
    stt_minutes: float = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_cached_input_tokens: int = 0
    audio_input_tokens: int = 0  # speech-to-speech models (OpenAI realtime, Gemini live)
    audio_output_tokens: int = 0
    tts_characters: int = 0
    tts_model: str | None = None


class ExpectedScript(BaseModel):
    """Optional test scenario: what the caller was supposed to say and the correct answers."""

    scenario_id: str | None = None
    caller_turns: list[str] = Field(default_factory=list)  # in order; caller turn n <-> expected turn n
    expected_answers: dict[str, Any] = Field(default_factory=dict)


class CallData(BaseModel):
    schema_version: str = SCHEMA_VERSION
    call: CallInfo
    form_fields: list[FormField] = Field(default_factory=list)
    transcript: list[Utterance] = Field(default_factory=list)
    answers: list[Answer] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    turns: list[TurnTiming] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    interruptions: int = 0
    form_completed: bool = False
    recording_path: str | None = None  # agent audio WAV (dummy test calls only)
    expected_script: ExpectedScript | None = None
    errors: list[str] = Field(default_factory=list)


# ===========================================================================
# Tester ratings (filled in after the call)
# ===========================================================================


class Ratings(BaseModel):
    naturalness: int | None = Field(None, ge=1, le=5)
    clarity: int | None = Field(None, ge=1, le=5)
    pronunciation: int | None = Field(None, ge=1, le=5)
    accent_fit: int | None = Field(None, ge=1, le=5)
    politeness: int | None = Field(None, ge=1, le=5)
    code_mixing: int | None = Field(None, ge=1, le=5)  # used in Language support, not Voice quality
    notes: str | None = None


# ===========================================================================
# OUTPUT: Report
# ===========================================================================


class PiiInfo(BaseModel):
    masked_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SummarySection(BaseModel):
    overall_score: float
    verdict: Literal["Good", "Needs improvement", "Poor"]
    section_scores: dict[str, float | None]  # None = no data for this section
    weights_used: dict[str, float]  # after re-sharing weights of sections with no data
    missing_sections: list[str]
    strengths: list[str]
    problems: list[str]


class TranscriptItem(BaseModel):
    role: Literal["caller", "agent", "tool"]
    text: str
    offset_s: float
    time: str  # "mm:ss" from call start
    language: str | None = None
    interrupted: bool = False
    highlights: list[Literal["mishearing", "reasked", "tool", "interruption"]] = Field(default_factory=list)
    tool: dict | None = None  # for role == "tool": name, success, error


class Mishearing(BaseModel):
    offset_s: float | None
    time: str | None
    kind: Literal["transcription", "caller_correction", "value_changed", "wrong_value", "number_misheard"]
    said: str  # what the caller said (or should have said)
    heard: str  # what the AI transcribed / saved
    field_id: str | None = None
    fixed: bool | None = None  # None = not applicable / unknown
    language: str | None = None
    detail: str | None = None


class MishearingSection(BaseModel):
    items: list[Mishearing]
    total: int
    fixed: int
    script_available: bool
    wer: float | None = None
    cer: float | None = None
    aligned_turns: int = 0


class AudioIssue(BaseModel):
    kind: Literal["long_silence", "talk_over", "cut_off", "repeated_phrase"]
    offset_s: float | None = None
    time: str | None = None
    detail: str


class MosScore(BaseModel):
    model: str
    sig: float
    bak: float
    ovrl: float


class VoiceQualitySection(BaseModel):
    ratings: Ratings
    rating_average: float | None
    mos: MosScore | None = None
    mos_status: str  # "off" / "ok" / "no recording" / error text
    issues: list[AudioIssue]


class TurnLatency(BaseModel):
    turn_index: int
    total_ms: float | None
    stt_ms: float | None = None
    turn_wait_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None
    other_ms: float | None = None
    rating: Literal["Good", "OK", "Poor"] | None = None


class SlowTurn(BaseModel):
    turn_index: int
    total_ms: float
    reason: str


class LatencySection(BaseModel):
    average_ms: float | None
    median_ms: float | None
    p90_ms: float | None
    max_ms: float | None
    rating: Literal["Good", "OK", "Poor"] | None
    has_step_split: bool
    per_turn: list[TurnLatency]
    slowest: list[SlowTurn]


class LanguageCount(BaseModel):
    language: str
    caller_turns: int


class LanguageSection(BaseModel):
    selected: str
    detected: list[LanguageCount]
    agent_turns_checked: int
    agent_correct_language_pct: float | None
    wrong_language_turns: list[dict]  # {time, text, expected, got}
    code_mixing_rating: int | None
    mishearings_by_language: dict[str, int]
    method_note: str


class FieldRow(BaseModel):
    field_id: str
    label: str
    expected: str | None
    saved: str | None
    correct: bool | None  # None = not reviewed
    notes: str


class AccuracySection(BaseModel):
    field_accuracy: float | None  # correct / reviewed filled fields
    completion: float | None  # required filled / required (visible)
    filled: int
    reviewed: int
    correct: int
    required_total: int
    required_filled: int
    followups_correct: int
    followups_total: int
    followup_issues: list[str]
    invalid_answers: int  # rejected by backend validation
    invalid_answers_fixed: int
    corrections_saved: int
    tool_calls_total: int
    tool_success_rate: float | None
    invalid_tool_calls: int  # bad JSON arguments
    validation_errors: int
    table: list[FieldRow]


class CostItem(BaseModel):
    label: str
    quantity: float
    unit: str
    rate: float
    rate_currency: Literal["USD", "INR"]
    cost_usd: float
    cost_inr: float


class CostSection(BaseModel):
    items: list[CostItem]
    total_usd: float
    total_inr: float
    per_minute_usd: float | None
    per_minute_inr: float | None
    per_completed_form_usd: float | None
    per_completed_form_inr: float | None
    projection_1000_usd: float
    projection_1000_inr: float
    usd_to_inr: float
    rates_last_updated: str
    note: str


class Issue(BaseModel):
    severity: Severity
    title: str
    detail: str
    suggestion: str


class AiSummary(BaseModel):
    status: Literal["off", "ok", "flagged", "error"]
    text: str | None = None
    model: str | None = None
    unverified_numbers: list[str] = Field(default_factory=list)
    label: str = "AI-generated summary - review before sharing."


class Report(BaseModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: datetime
    test_mode_notice: str = "TEST MODE - dummy data only"
    review_notice: str = "AI-assisted test report - must be reviewed by a team member before sharing outside EdZola."
    call: CallInfo
    pii: PiiInfo
    summary: SummarySection
    transcript: list[TranscriptItem]
    mishearings: MishearingSection
    voice_quality: VoiceQualitySection
    latency: LatencySection
    language: LanguageSection
    accuracy: AccuracySection
    cost: CostSection
    issues: list[Issue]
    ai_summary: AiSummary
