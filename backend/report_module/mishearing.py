"""Find places where the AI misheard or misunderstood the caller.

Five checks (each produces Mishearing items):
1. transcription   - the caller followed an expected script, and the transcript
                     differs from it (per-turn CER above a small threshold).
2. caller_correction / value_changed
                   - a field was saved, then saved again with a different value.
                     If the caller's turn sounds like a correction ("No, I said...",
                     "nahi, maine kaha...") it is a caller_correction.
3. number_misheard - the caller said a number, but a different number was saved
                     (e.g. "fifteen" saved as 50).
4. wrong_value     - the final saved value differs from the expected value
                     (tester review or expected script).
Also: Word Error Rate (WER) and Character Error Rate (CER) against the script.

CER counts graphemes (visible letters), which is fairer for Indian scripts.
Caller turn n is compared with expected turn n (in order).
"""

import regex

from report_module.number_words import extract_numbers, parse_number_list, parse_spoken_number
from report_module.schema import CallData, Mishearing, MishearingSection, ToolCallRecord, Utterance
from report_module.textutil import fmt_time, graphemes, normalize, short, words

# A caller turn whose CER against the script is above this counts as a transcription error.
TRANSCRIPTION_CER_THRESHOLD = 0.15

# Phrases a caller uses to correct the agent (English, Hinglish/Hindi, Tamil, Telugu).
CORRECTION_PATTERNS = [
    r"\bno,? i (said|meant|told)\b",
    r"\bi (said|meant)\b",
    r"\bthat'?s (not|wrong)\b",
    r"\bnot \w+,? (it'?s|but)\b",
    r"\bwrong\b",
    r"\bcorrection\b",
    r"\bnahi?n?,? (maine|mai|main)\b",
    r"\bmaine (kaha|bola)\b",
    r"\bgalat\b",
    r"\bsahi nahi\b",
    r"\billa,? naan\b",
    r"\bnaan sonnadhu\b",
    r"\bkaadu,? nenu\b",
    r"\bnenu cheppindi\b",
    r"नहीं,? मैंने",
    r"मैंने (कहा|बोला)",
    r"गलत",
]
_CORRECTION_RE = [regex.compile(p, regex.IGNORECASE) for p in CORRECTION_PATTERNS]


# ---------------------------------------------------------------------------
# WER / CER
# ---------------------------------------------------------------------------


def edit_distance(ref: list, hyp: list) -> int:
    """Levenshtein distance (substitutions + deletions + insertions)."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    ref = words(reference)
    return edit_distance(ref, words(hypothesis)) / len(ref) if ref else 0.0


def cer(reference: str, hypothesis: str) -> float:
    ref = graphemes(reference)
    return edit_distance(ref, graphemes(hypothesis)) / len(ref) if ref else 0.0


def corpus_rates(pairs: list[tuple[str, str]]) -> tuple[float | None, float | None]:
    """WER and CER over many (reference, hypothesis) pairs: total edits / total reference length."""
    w_err = w_len = c_err = c_len = 0
    for ref, hyp in pairs:
        rw, rc = words(ref), graphemes(ref)
        w_err += edit_distance(rw, words(hyp))
        w_len += len(rw)
        c_err += edit_distance(rc, graphemes(hyp))
        c_len += len(rc)
    return (round(w_err / w_len, 4) if w_len else None, round(c_err / c_len, 4) if c_len else None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_correction(text: str) -> bool:
    return any(p.search(text or "") for p in _CORRECTION_RE)


def value_to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def values_equal(a, b) -> bool:
    """Compare a saved value with an expected one, loosely ("35" == 35, "5, 8" == [5, 8])."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, list) or isinstance(b, list):
        return parse_number_list(a) == parse_number_list(b)
    is_num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    if is_num(a) or is_num(b):
        # One side is a number: compare as numbers ("35", "paintees" and 35 are equal).
        na, nb = parse_spoken_number(a), parse_spoken_number(b)
        return na is not None and na == nb
    return normalize(str(a)) == normalize(str(b))


def saved_value(tc: ToolCallRecord):
    """The value a successful save_answer stored (normalized if the backend says so)."""
    args = tc.arguments if isinstance(tc.arguments, dict) else {}
    result = tc.result if isinstance(tc.result, dict) else {}
    saved = result.get("saved")
    if isinstance(saved, dict) and args.get("field_id") in saved:
        return saved[args["field_id"]]
    return args.get("value")


def successful_saves(data: CallData) -> list[ToolCallRecord]:
    return [
        tc for tc in data.tool_calls
        if tc.name == "save_answer" and tc.success and isinstance(tc.arguments, dict) and tc.arguments.get("field_id")
    ]


def caller_before(transcript: list[Utterance], offset_s: float | None) -> Utterance | None:
    """The last caller utterance at or before a moment in the call."""
    if offset_s is None:
        return None
    before = [u for u in transcript if u.role == "caller" and u.offset_s <= offset_s + 0.001]
    return before[-1] if before else None


class FinalValues:
    """Final saved values and whether each one is known to be correct."""

    def __init__(self, data: CallData):
        self.values = {a.field_id: a.value for a in data.answers if a.status in ("filled", "needs_confirmation")}
        self.reviews = {r.field_id: r for r in data.reviews}
        self.expected = (data.expected_script.expected_answers if data.expected_script else {}) or {}

    def expected_for(self, field_id: str):
        review = self.reviews.get(field_id)
        if review and review.verdict == "wrong" and review.expected_value:
            return review.expected_value
        return self.expected.get(field_id)

    def is_correct(self, field_id: str) -> bool | None:
        """True/False if we know, None if nobody reviewed it and there is no expected answer."""
        review = self.reviews.get(field_id)
        if review:
            return review.verdict == "correct"
        if field_id in self.expected:
            return values_equal(self.values.get(field_id), self.expected[field_id])
        return None


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def find_mishearings(data: CallData) -> MishearingSection:
    final = FinalValues(data)
    fields = {f.id: f for f in data.form_fields}
    callers = [u for u in data.transcript if u.role == "caller"]
    saves = successful_saves(data)
    items: list[Mishearing] = []

    def add(item: Mishearing):
        # One item per (field, heard value): keep the first, more specific finding.
        for existing in items:
            if item.field_id and existing.field_id == item.field_id and existing.heard == item.heard:
                return
        items.append(item)

    def field_saved_after(caller: Utterance) -> str | None:
        nxt = [u.offset_s for u in callers if u.offset_s > caller.offset_s]
        end = nxt[0] if nxt else float("inf")
        for tc in saves:
            if tc.offset_s is not None and caller.offset_s <= tc.offset_s < end:
                return tc.arguments["field_id"]
        return None

    # 1. Transcription errors against the expected script
    pairs: list[tuple[str, str]] = []
    script = data.expected_script.caller_turns if data.expected_script else []
    for expected, caller in zip(script, callers):
        pairs.append((expected, caller.text))
        turn_cer = cer(expected, caller.text)
        if turn_cer > TRANSCRIPTION_CER_THRESHOLD:
            field_id = field_saved_after(caller)
            add(Mishearing(
                offset_s=caller.offset_s, time=fmt_time(caller.offset_s), kind="transcription",
                said=expected, heard=caller.text, field_id=field_id,
                fixed=final.is_correct(field_id) if field_id else None, language=caller.language,
                detail=f"Turn CER {turn_cer:.0%}",
            ))
    wer_value, cer_value = corpus_rates(pairs) if pairs else (None, None)

    # 2. Number checks and value changes, in call order
    last_value: dict[str, object] = {}
    for tc in saves:
        field_id = tc.arguments["field_id"]
        value = saved_value(tc)
        caller = caller_before(data.transcript, tc.offset_s)
        field = fields.get(field_id)

        if caller and field and field.type in ("number", "number_list"):
            spoken = extract_numbers(caller.text)
            saved_numbers = parse_number_list(value) if field.type == "number_list" else [parse_spoken_number(value)]
            if spoken and saved_numbers and any(n is not None and n not in spoken for n in saved_numbers):
                later_fixed = final.is_correct(field_id)
                add(Mishearing(
                    offset_s=caller.offset_s, time=fmt_time(caller.offset_s), kind="number_misheard",
                    said=caller.text, heard=value_to_text(value), field_id=field_id,
                    fixed=later_fixed if later_fixed is not None else not values_equal(final.values.get(field_id), value),
                    language=caller.language, detail=f"Caller said {value_to_text(spoken)}",
                ))

        old = last_value.get(field_id)
        grew = isinstance(old, list) and isinstance(value, list) and set(old) < set(value)
        if grew:
            # A list that only gained items (ages [5, 8] -> [5, 8, 2] after "3 children") is
            # new information, not a mishearing.
            last_value[field_id] = value
            continue
        if field_id in last_value and not values_equal(old, value):
            correct = final.is_correct(field_id)
            # If this change fixes a mishearing we already found for this field, update that item
            # instead of listing the same mistake twice.
            earlier = next((m for m in items if m.field_id == field_id
                            and m.kind in ("transcription", "number_misheard")), None)
            if earlier is not None:
                earlier.fixed = correct if correct is not None else True
                earlier.detail = f"{earlier.detail}; corrected at {fmt_time(caller.offset_s if caller else tc.offset_s)} " \
                                 f"from {value_to_text(last_value[field_id])} to {value_to_text(value)}"
                last_value[field_id] = value
                continue
            add(Mishearing(
                offset_s=caller.offset_s if caller else tc.offset_s,
                time=fmt_time(caller.offset_s if caller else tc.offset_s),
                kind="caller_correction" if caller and is_correction(caller.text) else "value_changed",
                said=caller.text if caller else "", heard=value_to_text(last_value[field_id]), field_id=field_id,
                fixed=correct if correct is not None else True,
                language=caller.language if caller else None,
                detail=f"Changed from {value_to_text(last_value[field_id])} to {value_to_text(value)}",
            ))
        last_value[field_id] = value

    # 3. Final value differs from the expected value
    for field_id, value in final.values.items():
        if final.is_correct(field_id) is False:
            already = [m for m in items if m.field_id == field_id]
            if already:  # the cause is already listed: just make sure it shows as not fixed
                for m in already:
                    m.fixed = False
                continue
            expected = final.expected_for(field_id)
            add(Mishearing(
                offset_s=None, time=None, kind="wrong_value",
                said=value_to_text(expected) if expected is not None else "(marked wrong by tester)",
                heard=value_to_text(value), field_id=field_id, fixed=False,
                detail="Final saved value is wrong",
            ))

    items.sort(key=lambda m: (m.offset_s is None, m.offset_s or 0))
    return MishearingSection(
        items=items,
        total=len(items),
        fixed=sum(1 for m in items if m.fixed),
        script_available=bool(script),
        wer=wer_value,
        cer=cer_value,
        aligned_turns=len(pairs),
    )


__all__ = ["find_mishearings", "wer", "cer", "corpus_rates", "is_correction", "values_equal", "short"]
