"""Database tables: forms, calls, answers, tool_calls, turn_metrics, reviews."""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Form(Base):
    __tablename__ = "forms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    definition: Mapped[dict] = mapped_column(JSON)  # the full form JSON (fields, rules)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    form_id: Mapped[str] = mapped_column(String(64), ForeignKey("forms.id"))
    mode: Mapped[str] = mapped_column(String(32), default="live")  # "live" or "simulate"
    status: Mapped[str] = mapped_column(String(32), default="connecting")
    settings: Mapped[dict] = mapped_column(JSON)  # models, voice, language, tuning, cost rates
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    interruptions: Mapped[int] = mapped_column(Integer, default=0)
    json_parse_failures: Mapped[int] = mapped_column(Integer, default=0)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tts_characters: Mapped[int] = mapped_column(Integer, default=0)
    transcript: Mapped[list] = mapped_column(JSON, default=list)  # chat bubbles
    errors: Mapped[list] = mapped_column(JSON, default=list)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("call_id", "field_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(64), ForeignKey("calls.id"), index=True)
    field_id: Mapped[str] = mapped_column(String(64))
    value: Mapped[object] = mapped_column(JSON, nullable=True)  # normalized value
    raw_value: Mapped[object] = mapped_column(JSON, nullable=True)  # what the LLM sent
    status: Mapped[str] = mapped_column(String(32), default="pending")  # filled / needs_confirmation / skipped
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # clarification / skip reason
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # save attempts incl. rejected ones
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(64), ForeignKey("calls.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[object] = mapped_column(JSON, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[dict] = mapped_column(JSON)
    duration_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TurnMetric(Base):
    __tablename__ = "turn_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(64), ForeignKey("calls.id"), index=True)
    turn_index: Mapped[int] = mapped_column(Integer)
    # The four timings asked for. None = not measured for this turn (e.g. greeting has no STT).
    stt_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tts_ttfb_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Extra detail: wait between final transcript and LLM request (turn-stop timeout),
    # and time spent inside tool calls (included in llm_ttft_ms).
    turn_wait_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    tool_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("call_id", "field_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(64), ForeignKey("calls.id"), index=True)
    field_id: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(32))  # "correct" or "wrong"
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
