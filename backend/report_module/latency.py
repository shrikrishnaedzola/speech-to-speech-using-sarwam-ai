"""Latency: average / median / p90 / max reply time, per-turn rating, slowest turns.

Reply time = caller stops speaking -> first agent audio (TurnTiming.total_ms).
Only caller turns are used for the statistics; the greeting has no caller turn.
For Sarvam (cascaded STT -> LLM -> TTS) the per-step split is also shown.
"""

import math

from report_module.schema import CallData, LatencySection, SlowTurn, ToolCallRecord, TurnLatency, TurnTiming

STEP_KEYS = ("stt_ms", "turn_wait_ms", "llm_ttft_ms", "tts_ttfb_ms")


def percentile(values: list[float], pct: float) -> float | None:
    """Percentile with linear interpolation (same as numpy's default)."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def rate(ms: float | None, settings: dict) -> str | None:
    if ms is None:
        return None
    lat = settings["latency"]
    if ms < lat["good_below_ms"]:
        return "Good"
    if ms <= lat["ok_below_ms"]:
        return "OK"
    return "Poor"


def latency_score(average_ms: float | None, settings: dict) -> float | None:
    """0-100. 100 below the 'good' limit, 50 at the 'OK' limit, 0 at zero_score_at_ms."""
    if average_ms is None:
        return None
    lat = settings["latency"]
    good, ok, zero = lat["good_below_ms"], lat["ok_below_ms"], lat["zero_score_at_ms"]
    if average_ms <= good:
        return 100.0
    if average_ms <= ok:
        return round(100 - 50 * (average_ms - good) / (ok - good), 1)
    return round(max(0.0, 50 - 50 * (average_ms - ok) / (zero - ok)), 1)


def is_caller_turn(t: TurnTiming) -> bool:
    return t.turn_index > 0 and t.total_ms is not None


def _reason(turn: TurnTiming, tools_in_turn: list[ToolCallRecord]) -> str:
    """Plain-English guess at why a turn was slow."""
    reasons = []
    steps = {k: getattr(turn, k) for k in STEP_KEYS if getattr(turn, k) is not None}
    if steps:
        name = {"stt_ms": "speech-to-text", "turn_wait_ms": "turn-end wait",
                "llm_ttft_ms": "LLM first token", "tts_ttfb_ms": "text-to-speech"}
        slowest = max(steps, key=steps.get)
        reasons.append(f"slowest step: {name[slowest]} ({steps[slowest]:.0f} ms)")
    if tools_in_turn:
        names = ", ".join(sorted({tc.name for tc in tools_in_turn}))
        failed = sum(1 for tc in tools_in_turn if not tc.success)
        reasons.append(f"{len(tools_in_turn)} tool call(s): {names}" + (f", {failed} failed" if failed else ""))
    elif turn.tool_ms:
        reasons.append(f"tool calls took {turn.tool_ms:.0f} ms")
    if turn.agent_text and len(turn.agent_text) > 160:
        reasons.append("long agent answer")
    if turn.user_text and len(turn.user_text) > 120:
        reasons.append("long caller answer")
    return "; ".join(reasons) or "no extra detail logged"


def analyse_latency(data: CallData, settings: dict) -> LatencySection:
    caller_turns = [t for t in data.turns if is_caller_turn(t)]
    totals = [t.total_ms for t in caller_turns]
    has_split = any(getattr(t, k) is not None for t in data.turns for k in STEP_KEYS)

    per_turn = []
    for t in sorted(data.turns, key=lambda t: t.turn_index):
        other = None
        if has_split and t.total_ms is not None:
            other = max(0.0, t.total_ms - sum(getattr(t, k) or 0 for k in STEP_KEYS))
        per_turn.append(TurnLatency(
            turn_index=t.turn_index, total_ms=t.total_ms, stt_ms=t.stt_ms, turn_wait_ms=t.turn_wait_ms,
            llm_ttft_ms=t.llm_ttft_ms, tts_ttfb_ms=t.tts_ttfb_ms, other_ms=other, rating=rate(t.total_ms, settings),
        ))

    # Tool calls that happened inside each slow turn: between the turn's caller text and the next one.
    def tools_for(turn: TurnTiming) -> list[ToolCallRecord]:
        caller_offsets = [u.offset_s for u in data.transcript if u.role == "caller"]
        if turn.turn_index - 1 >= len(caller_offsets):
            return []
        start = caller_offsets[turn.turn_index - 1]
        end = caller_offsets[turn.turn_index] if turn.turn_index < len(caller_offsets) else float("inf")
        return [tc for tc in data.tool_calls if tc.offset_s is not None and start <= tc.offset_s < end]

    slowest = sorted(caller_turns, key=lambda t: t.total_ms, reverse=True)[:3]
    average = sum(totals) / len(totals) if totals else None
    return LatencySection(
        average_ms=round(average, 1) if average is not None else None,
        median_ms=round(percentile(totals, 50), 1) if totals else None,
        p90_ms=round(percentile(totals, 90), 1) if totals else None,
        max_ms=round(max(totals), 1) if totals else None,
        rating=rate(average, settings),
        has_step_split=has_split,
        per_turn=per_turn,
        slowest=[SlowTurn(turn_index=t.turn_index, total_ms=t.total_ms, reason=_reason(t, tools_for(t))) for t in slowest],
    )
