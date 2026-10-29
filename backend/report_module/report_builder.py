"""Build a Report from CallData. This is the one function every tester calls.

    report = build_report(call_data, ratings, settings)

Steps:
1. Mask phone/Aadhaar-like numbers (before anything else sees the data).
2. Compute each section: mishearings, accuracy, latency, language, voice, cost.
3. Score each section 0-100, then the weighted overall score and verdict.
4. Rule-based strengths, problems, issues and suggestions.
5. Optional AI-written summary (only from the numbers computed above).
"""

from datetime import datetime, timezone

from report_module.accuracy import accuracy_score, analyse_accuracy
from report_module.cost import analyse_cost, cost_score
from report_module.language import analyse_language, language_score
from report_module.latency import analyse_latency, latency_score
from report_module.mishearing import find_mishearings
from report_module.pii import mask_call_data, pii_warnings
from report_module.schema import (
    AiSummary, CallData, MishearingSection, PiiInfo, Ratings, Report, TranscriptItem,
)
from report_module.scoring import build_issues, build_summary, mishearing_score, strengths_and_problems
from report_module.textutil import fmt_time, short
from report_module.voice_quality import analyse_voice_quality, voice_quality_score


def build_transcript(data: CallData, mishearings: MishearingSection) -> list[TranscriptItem]:
    """Chat bubbles + tool calls in time order, with colour highlights."""
    misheard_at = {m.offset_s for m in mishearings.items if m.offset_s is not None}
    items: list[TranscriptItem] = []
    for u in data.transcript:
        highlights = []
        if u.role == "caller" and u.offset_s in misheard_at:
            highlights.append("mishearing")
        if u.role == "agent" and u.interrupted:
            highlights.append("interruption")
        items.append(TranscriptItem(role=u.role, text=u.text, offset_s=u.offset_s, time=fmt_time(u.offset_s),
                                    language=u.language if u.role == "caller" else None,
                                    interrupted=u.interrupted, highlights=highlights))
    for tc in data.tool_calls:
        if tc.offset_s is None:
            continue
        args = tc.arguments if isinstance(tc.arguments, dict) else {"raw": tc.arguments}
        error = tc.result.get("error") if isinstance(tc.result, dict) else None
        label = f"{tc.name}({', '.join(f'{k}={v}' for k, v in args.items())})"
        items.append(TranscriptItem(role="tool", text=short(label, 140), offset_s=tc.offset_s, time=fmt_time(tc.offset_s),
                                    highlights=["tool"],
                                    tool={"name": tc.name, "success": tc.success, "error": error, "parse_error": tc.parse_error}))
    # Tool calls sort after the caller turn that triggered them and before the agent reply.
    order = {"caller": 0, "tool": 1, "agent": 2}
    items.sort(key=lambda i: (i.offset_s, order[i.role]))

    # Re-asked: an agent turn that follows a rejected answer or a clarification request.
    # (A tool call with broken JSON is retried silently, so it does not count.)
    pending_reask = False
    for item in items:
        if item.role == "caller":
            pending_reask = False
        elif item.role == "tool" and item.tool:
            rejected = item.tool["name"] == "save_answer" and not item.tool["success"] and not item.tool["parse_error"]
            if rejected or item.tool["name"] == "request_clarification":
                pending_reask = True
        elif item.role == "agent" and pending_reask:
            item.highlights.append("reasked")
            pending_reask = False
    return items


def build_report(data: CallData, ratings: Ratings | None, settings: dict, with_ai_summary: bool = True) -> Report:
    ratings = ratings or Ratings()
    data, found = mask_call_data(data)
    pii = PiiInfo(masked_count=len(found), warnings=pii_warnings(found))

    mishearings = find_mishearings(data)
    accuracy = analyse_accuracy(data, mishearings)
    latency = analyse_latency(data, settings)
    language = analyse_language(data, mishearings, ratings.code_mixing)
    voice = analyse_voice_quality(data, ratings, settings)
    cost = analyse_cost(data, settings)

    has_caller = any(u.role == "caller" for u in data.transcript)
    scores = {
        "accuracy": accuracy_score(accuracy),
        "mishearings": mishearing_score(mishearings, has_caller),
        "latency": latency_score(latency.average_ms, settings),
        "voice_quality": voice_quality_score(voice),
        "language": language_score(language),
        "cost": cost_score(cost, settings),
    }
    strengths, problems = strengths_and_problems(accuracy, mishearings, latency, language, voice, cost, settings)

    report = Report(
        generated_at=datetime.now(timezone.utc),
        call=data.call,
        pii=pii,
        summary=build_summary(scores, settings, strengths, problems),
        transcript=build_transcript(data, mishearings),
        mishearings=mishearings,
        voice_quality=voice,
        latency=latency,
        language=language,
        accuracy=accuracy,
        cost=cost,
        issues=build_issues(accuracy, mishearings, latency, language, voice, cost, pii, settings),
        ai_summary=AiSummary(status="off"),
    )
    if with_ai_summary and settings.get("ai_summary_enabled"):
        from report_module.summary_llm import write_summary

        report.ai_summary = write_summary(report, settings)
    return report
