"""Overall score, verdict, strengths/problems, and the issues + recommendations list.

All rule-based (no LLM), so every number can be traced back to the metrics.

Overall score = weighted average of the section scores (0-100 each).
Weights come from settings (default: accuracy 35, mishearings 15, latency 20,
voice quality 15, language 10, cost 5). A section with no data (e.g. no
ratings yet) is left out and the other weights are scaled up to 100%.
"""

from report_module.schema import (
    AccuracySection, CostSection, Issue, LanguageSection, LatencySection, MishearingSection,
    PiiInfo, SummarySection, VoiceQualitySection,
)

SECTION_LABELS = {
    "accuracy": "Accuracy", "mishearings": "Mishearings", "latency": "Latency",
    "voice_quality": "Voice quality", "language": "Language support", "cost": "Cost",
}
LANGUAGE_NAMES = {"hi": "Hindi", "en": "English", "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "kn": "Kannada",
                  "ml": "Malayalam", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "od": "Odia", "or": "Odia"}


def lang_name(code: str | None) -> str:
    if not code:
        return "unknown"
    return LANGUAGE_NAMES.get(code.split("-")[0].lower(), code)


def mishearing_score(m: MishearingSection, has_caller_turns: bool) -> float | None:
    """100 minus 15 per unfixed and 5 per fixed mishearing; capped by (1 - CER) when a script exists."""
    if not has_caller_turns:
        return None
    unfixed = sum(1 for i in m.items if not i.fixed)
    score = 100 - 15 * unfixed - 5 * (m.total - unfixed)
    if m.cer is not None:
        score = min(score, 100 * (1 - m.cer))
    return round(max(0.0, score), 1)


def overall(section_scores: dict[str, float | None], settings: dict) -> tuple[float, str, dict, list[str]]:
    weights = settings["weights"]
    present = {k: weights[k] for k, v in section_scores.items() if v is not None and weights.get(k, 0) > 0}
    missing = [k for k, v in section_scores.items() if v is None]
    total_w = sum(present.values())
    if total_w == 0:
        return 0.0, "Poor", {}, missing
    used = {k: round(100 * w / total_w, 1) for k, w in present.items()}
    score = round(sum(section_scores[k] * w for k, w in present.items()) / total_w, 1)
    v = settings["verdict"]
    verdict = "Good" if score >= v["good_min"] else "Needs improvement" if score >= v["needs_improvement_min"] else "Poor"
    return score, verdict, used, missing


def _secs(ms: float | None) -> str:
    return f"{ms / 1000:.2f} s" if ms is not None else "-"


def strengths_and_problems(acc: AccuracySection, mis: MishearingSection, lat: LatencySection,
                           lang: LanguageSection, vq: VoiceQualitySection, cost: CostSection,
                           settings: dict) -> tuple[list[str], list[str]]:
    """Pick up to 3 strengths and 3 problems, most important first."""
    good, bad = [], []
    if acc.field_accuracy is not None:
        if acc.field_accuracy >= 0.9:
            good.append(f"{acc.correct} of {acc.reviewed} checked answers were saved correctly.")
        elif acc.field_accuracy < 0.8:
            bad.append(f"Only {acc.correct} of {acc.reviewed} checked answers were saved correctly.")
    if acc.completion is not None:
        if acc.completion == 1:
            good.append(f"All {acc.required_total} required questions were answered.")
        else:
            bad.append(f"{acc.required_total - acc.required_filled} required question(s) were not completed.")
    unfixed = sum(1 for i in mis.items if not i.fixed)
    if mis.total == 0:
        good.append("No mishearings were found.")
    elif unfixed:
        bad.append(f"{unfixed} mishearing(s) were not fixed during the call.")
    if lat.rating == "Good":
        good.append(f"Replies were fast (average {_secs(lat.average_ms)}).")
    elif lat.rating == "Poor":
        bad.append(f"Replies were slow (average {_secs(lat.average_ms)}, slowest {_secs(lat.max_ms)}).")
    if lang.agent_correct_language_pct is not None:
        if lang.agent_correct_language_pct >= 95:
            good.append(f"The agent replied in the right language in {lang.agent_correct_language_pct:.0f}% of turns.")
        elif lang.agent_correct_language_pct < 85:
            bad.append(f"The agent used the wrong language in {len(lang.wrong_language_turns)} turn(s).")
    if acc.followups_total:
        if not acc.followup_issues:
            good.append("Follow-up questions were asked only when needed.")
        else:
            bad.append(f"{len(acc.followup_issues)} follow-up question(s) were handled wrongly.")
    if acc.invalid_answers and acc.invalid_answers_fixed == acc.invalid_answers:
        good.append(f"All {acc.invalid_answers} invalid answer(s) were re-asked and fixed.")
    if acc.invalid_tool_calls:
        bad.append(f"{acc.invalid_tool_calls} tool call(s) had invalid arguments.")
    if vq.rating_average is not None:
        if vq.rating_average >= 4:
            good.append(f"Testers rated the voice {vq.rating_average:.1f} out of 5.")
        elif vq.rating_average <= 2.5:
            bad.append(f"Testers rated the voice only {vq.rating_average:.1f} out of 5.")
    if len(vq.issues) >= 3:
        bad.append(f"{len(vq.issues)} audio issues were found (silences, overlaps, cut-offs or repeats).")
    if cost.per_minute_inr is not None and cost.total_usd > 0:
        target = settings["cost_target_inr_per_min"]
        if cost.per_minute_inr <= target:
            good.append(f"Cost was ₹{cost.per_minute_inr:.2f} per minute, within the ₹{target:.2f} target.")
        elif cost.per_minute_inr > 2 * target:
            bad.append(f"Cost was ₹{cost.per_minute_inr:.2f} per minute, over twice the ₹{target:.2f} target.")
    return good[:3], bad[:3]


def build_issues(acc: AccuracySection, mis: MishearingSection, lat: LatencySection, lang: LanguageSection,
                 vq: VoiceQualitySection, cost: CostSection, pii: PiiInfo, settings: dict) -> list[Issue]:
    """Problems found, each with a simple suggestion. Sorted High -> Medium -> Low."""
    issues: list[Issue] = []

    def add(severity, title, detail, suggestion):
        issues.append(Issue(severity=severity, title=title, detail=detail, suggestion=suggestion))

    if pii.masked_count:
        add("High", "Possible real personal data", pii.warnings[0] if pii.warnings else "",
            "Use only dummy test data. Delete the raw recording and database rows for this call.")

    # Numbers misheard, per language
    numbers: dict[str, int] = {}
    for m in mis.items:
        if m.kind == "number_misheard":
            numbers[lang_name(m.language)] = numbers.get(lang_name(m.language), 0) + 1
    for language, n in numbers.items():
        add("High" if n >= 2 else "Medium", f"Numbers misheard in {language}",
            f"The agent misheard numbers in {language} {n} time(s).",
            f"Add a number confirmation step for {language} calls (read the number back and ask the caller to confirm).")
    unfixed = [m for m in mis.items if not m.fixed and m.kind != "number_misheard"]
    if unfixed:
        fields = ", ".join(sorted({m.field_id for m in unfixed if m.field_id})) or "transcript"
        add("High", "Mishearings not fixed", f"{len(unfixed)} mishearing(s) stayed wrong ({fields}).",
            "Read back key answers before complete_form, and ask the caller to confirm each one.")
    if mis.cer is not None and mis.cer > 0.15:
        add("Medium", "High transcription error rate",
            f"Character error rate was {mis.cer:.0%} against the test script (WER {mis.wer:.0%}).",
            "Try another STT model or a fixed language instead of auto-detect for this language.")

    if acc.completion is not None and acc.completion < 1:
        missing = [r.label for r in acc.table if "required but missing" in r.notes]
        add("High", "Form not completed", f"Missing required answers: {', '.join(missing) or 'see table'}.",
            "Make sure the agent calls complete_form and asks every missing field it returns.")
    for text in acc.followup_issues:
        add("High", "Follow-up logic error", text, "Check the follow-up rules in the prompt and in the backend form definition.")
    if acc.invalid_tool_calls:
        add("Medium", "Invalid tool calls", f"{acc.invalid_tool_calls} tool call(s) had arguments that were not valid JSON.",
            "Simplify the tool schema and add an example call to the system prompt.")
    if acc.invalid_answers and acc.invalid_answers_fixed < acc.invalid_answers:
        add("Medium", "Invalid answers left unfixed",
            f"{acc.invalid_answers - acc.invalid_answers_fixed} answer(s) rejected by validation were never saved.",
            "Tell the agent to re-ask a question immediately when save_answer returns an error.")
    if acc.field_accuracy is not None and acc.field_accuracy < 0.8:
        add("High", "Low answer accuracy", f"Field accuracy was {acc.field_accuracy:.0%}.",
            "Review the wrong fields in the accuracy table; add confirmation for those question types.")

    if lat.rating == "Poor":
        slow = lat.slowest[0].reason if lat.slowest else ""
        add("High" if (lat.average_ms or 0) > 2000 else "Medium", "Slow replies",
            f"Average reply time {_secs(lat.average_ms)} (p90 {_secs(lat.p90_ms)}). Slowest turn: {slow}.",
            "Lower the turn-end wait, use a faster model, and keep replies to one or two short sentences.")
    elif lat.p90_ms and lat.p90_ms > settings["latency"]["ok_below_ms"]:
        add("Low", "Some slow replies", f"10% of replies took over {_secs(lat.p90_ms)}.",
            "Check the slowest turns: tool calls and long answers are the usual cause.")
    if lat.has_step_split and lat.per_turn:
        steps = {"stt_ms": "speech-to-text", "llm_ttft_ms": "LLM", "tts_ttfb_ms": "text-to-speech"}
        avg = {}
        for key in steps:
            vals = [getattr(t, key) for t in lat.per_turn if getattr(t, key) is not None]
            if vals:
                avg[key] = sum(vals) / len(vals)
        if avg and lat.average_ms and lat.average_ms > settings["latency"]["good_below_ms"]:
            worst = max(avg, key=avg.get)
            add("Low", f"Slowest step: {steps[worst]}", f"{steps[worst]} averaged {avg[worst]:.0f} ms per turn.",
                {"stt_ms": "Use stream_type 'fast' and a lower VAD silence window.",
                 "llm_ttft_ms": "Use the conversations model with reasoning off, and a shorter prompt.",
                 "tts_ttfb_ms": "Lower the TTS min buffer size and keep the TTS connection warm."}[worst])

    if lang.agent_correct_language_pct is not None and lang.agent_correct_language_pct < 90:
        add("Medium", "Wrong reply language",
            f"Agent replied in the expected language in {lang.agent_correct_language_pct:.0f}% of turns.",
            "State the reply language more firmly in the system prompt, or fix the language instead of auto-detect.")

    kinds = {}
    for i in vq.issues:
        kinds[i.kind] = kinds.get(i.kind, 0) + 1
    if kinds.get("long_silence"):
        add("Medium", "Long silences", f"{kinds['long_silence']} reply(ies) came after more than "
            f"{settings['audio_issues']['long_silence_ms'] / 1000:.0f} s of silence.",
            "Play a short filler phrase while tools run, and reduce latency (see above).")
    if kinds.get("talk_over"):
        add("Low", "Agent and caller talked over each other", f"{kinds['talk_over']} overlap(s).",
            "Tune barge-in: require a few words before interrupting, and keep agent turns short.")
    if kinds.get("cut_off"):
        add("Low", "Cut-off sentences", f"{kinds['cut_off']} reply(ies) ended mid-sentence.",
            "Check max tokens and TTS errors in the raw log.")
    if kinds.get("repeated_phrase"):
        add("Low", "Repeated phrases", f"{kinds['repeated_phrase']} phrase(s) were repeated.",
            "Ask the agent to rephrase when it re-asks a question, so it sounds less robotic.")
    if vq.mos is not None and vq.mos.ovrl < 3:
        add("Medium", "Low automatic audio quality score", f"DNSMOS overall {vq.mos.ovrl:.2f} / 5.",
            "Try another voice or a higher sample rate; check for noise or distortion in the recording.")
    if vq.rating_average is None:
        add("Low", "No tester ratings yet", "Voice quality is not part of the score until a tester rates the call.",
            "Fill in the 1-5 ratings on the report page, then regenerate the report.")
    if acc.reviewed == 0 and acc.filled:
        add("Low", "Answers not reviewed", "No answers were marked Correct/Wrong, so field accuracy is unknown.",
            "Mark each filled answer in the tester, then regenerate the report.")

    if cost.per_minute_inr is not None and cost.total_usd > 0 and cost.per_minute_inr > settings["cost_target_inr_per_min"]:
        add("Low", "Cost above target", f"₹{cost.per_minute_inr:.2f} per minute (target ₹{settings['cost_target_inr_per_min']:.2f}).",
            "Compare cheaper model/voice options for this provider.")

    order = {"High": 0, "Medium": 1, "Low": 2}
    issues.sort(key=lambda i: order[i.severity])
    return issues


def build_summary(scores: dict[str, float | None], settings: dict, strengths: list[str], problems: list[str]) -> SummarySection:
    score, verdict, used, missing = overall(scores, settings)
    return SummarySection(overall_score=score, verdict=verdict, section_scores=scores, weights_used=used,
                          missing_sections=missing, strengths=strengths, problems=problems)
