"""Optional AI-written summary of the report (off by default).

Rules:
- Uses Claude through the official anthropic SDK. The key comes ONLY from the
  ANTHROPIC_API_KEY environment variable (.env). It is never logged or stored.
- The model only sees a "facts sheet" built from the computed metrics, plus
  the transcript AFTER phone/Aadhaar masking. Nothing else.
- Every number in the reply is checked against the facts sheet. If any number
  is not found there, the summary is marked "flagged" and the UI/PDF warn
  that it must not be used without checking.
- The text is labelled "AI-generated summary - review before sharing."

Install: pip install -e "report_module[summary]"
"""

import os

import regex

from report_module.schema import AiSummary, Report

SYSTEM_PROMPT = (
    "You write short, plain-English summaries of voice-AI test calls for an NGO technology team. "
    "Use ONLY the facts and transcript you are given. Copy every number exactly as it appears in the "
    "facts sheet (same digits, same units); never calculate, round or invent a number. "
    "If something is not in the facts, do not mention it. "
    "Write 4 to 6 short sentences in simple English, no lists, no headings: overall result, what went "
    "well, the main problems, and the single most useful next step."
)

_NUMBER = regex.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """All numbers in a text, normalised ("1,000" -> "1000", "95.0" -> "95")."""
    out = set()
    for raw in _NUMBER.findall(text):
        value = raw.replace(",", "")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        out.add(value)
    return out


def build_facts(report: Report) -> str:
    """The only data the model may use: a plain-text sheet of computed values."""
    r = report
    s, a, lat, m, c, lg, vq = r.summary, r.accuracy, r.latency, r.mishearings, r.cost, r.language, r.voice_quality
    lines = [
        f"Provider: {r.call.provider}. Model: {r.call.model}. Language selected: {r.call.language_selected}. "
        f"Audio: {r.call.audio_mode}. Duration: {round(r.call.duration_s)} seconds.",
        f"Overall score: {round(s.overall_score)} out of 100. Verdict: {s.verdict}.",
        "Section scores: " + ", ".join(f"{k} {round(v)}" if v is not None else f"{k} no data"
                                      for k, v in s.section_scores.items()) + ".",
        f"Strengths: {' '.join(s.strengths) or 'none'}",
        f"Problems: {' '.join(s.problems) or 'none'}",
        f"Mishearings: {m.total} found, {m.fixed} fixed during the call."
        + (f" Word error rate {m.wer * 100:.1f}%, character error rate {m.cer * 100:.1f}%." if m.wer is not None else ""),
        f"Average reply time {lat.average_ms / 1000:.2f} s, slowest {lat.max_ms / 1000:.2f} s, rating {lat.rating}."
        if lat.average_ms is not None else "Reply time: not measured.",
        f"Field accuracy: {a.correct} of {a.reviewed} checked answers correct. "
        f"Completion: {a.required_filled} of {a.required_total} required questions answered.",
        f"Replies in the correct language: {lg.agent_correct_language_pct:.0f}% of {lg.agent_turns_checked} turns."
        if lg.agent_correct_language_pct is not None else "Reply language: not checked.",
        f"Tester voice rating: {vq.rating_average:.1f} out of 5." if vq.rating_average is not None else "Tester voice rating: none.",
        f"Audio issues found: {len(vq.issues)}.",
        f"Cost of this call: INR {c.total_inr:.2f} (USD {c.total_usd:.4f}); INR {c.per_minute_inr or 0:.2f} per minute.",
        "Top issues: " + " ".join(f"[{i.severity}] {i.title}: {i.suggestion}" for i in r.issues[:3]),
    ]
    return "\n".join(lines)


def build_transcript(report: Report) -> str:
    return "\n".join(f"{t.role}: {t.text}" for t in report.transcript if t.role != "tool")


def unverified_numbers(summary: str, facts: str) -> list[str]:
    """Numbers in the summary that do not appear in the facts sheet."""
    return sorted(_numbers(summary) - _numbers(facts))


def write_summary(report: Report, settings: dict) -> AiSummary:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return AiSummary(status="error", text="ANTHROPIC_API_KEY is not set on the backend.")
    try:
        import anthropic
    except ImportError:
        return AiSummary(status="error", text='anthropic is not installed (pip install -e "report_module[summary]").')

    model = settings.get("ai_summary_model") or "claude-opus-5-5"
    facts = build_facts(report)
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},  # a short summary does not need deep thinking
            # If the model declines, the API re-runs the request on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{
                "role": "user",
                "content": f"FACTS SHEET:\n{facts}\n\nTRANSCRIPT (personal numbers already masked):\n"
                           f"{build_transcript(report)}\n\nWrite the summary now.",
            }],
        )
    except anthropic.APIStatusError as e:
        return AiSummary(status="error", text=f"Claude API error {e.status_code}.", model=model)
    except anthropic.APIConnectionError:
        return AiSummary(status="error", text="Could not reach the Claude API.", model=model)

    if response.stop_reason == "refusal":
        return AiSummary(status="error", text="The model declined to write a summary.", model=response.model)
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        return AiSummary(status="error", text="The model returned no text.", model=response.model)
    bad = unverified_numbers(text, facts)
    return AiSummary(status="flagged" if bad else "ok", text=text, model=response.model, unverified_numbers=bad)
