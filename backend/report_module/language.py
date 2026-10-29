"""Language support: selected vs detected languages, and whether the agent replied in the right one.

How the agent's reply language is guessed (no extra model needed):
- By script: Devanagari -> Hindi/Marathi, Tamil script -> Tamil, etc.
- Latin script: if it contains several common romanized-Hindi words
  ("hai", "aap", "kya"...) it counts as Hindi (Hinglish), otherwise English.
This is an approximation; the method note in the report says so.

"Correct language" for each agent turn = the selected language (auto mode:
the caller's latest detected language), or the language the caller just
used. Romanized Hinglish counts as Hindi.
"""

from collections import Counter

import regex

from report_module.schema import CallData, LanguageCount, LanguageSection, MishearingSection
from report_module.textutil import fmt_time, short

SCRIPTS = [
    (r"\p{Devanagari}", "hi"),  # Hindi or Marathi (same script)
    (r"\p{Bengali}", "bn"),  # Bengali (also Assamese)
    (r"\p{Tamil}", "ta"),
    (r"\p{Telugu}", "te"),
    (r"\p{Kannada}", "kn"),
    (r"\p{Malayalam}", "ml"),
    (r"\p{Gujarati}", "gu"),
    (r"\p{Gurmukhi}", "pa"),
    (r"\p{Oriya}", "od"),
]
_SCRIPT_RES = [(regex.compile(p), code) for p, code in SCRIPTS]

ROMAN_HINDI_WORDS = {
    "hai", "hain", "aap", "aapka", "aapki", "aapke", "kya", "kitne", "kitni", "nahi", "nahin", "haan", "ji",
    "mein", "main", "ka", "ki", "ke", "ko", "se", "bhi", "aur", "theek", "dhanyavaad", "shukriya", "kripya",
    "batayiye", "bataiye", "kaunsi", "kahan", "hoon", "tha", "thi", "kar", "sakte", "rehte", "umar", "naam",
}

# Bengali and Assamese share a script, as do Hindi and Marathi: compare on these groups.
SAME_SCRIPT = {"mr": "hi", "as": "bn", "or": "od"}


def base_language(code: str | None) -> str | None:
    """'hi-IN' -> 'hi'; maps languages that share a script to one group."""
    if not code or code == "auto":
        return None
    base = code.split("-")[0].lower()
    return SAME_SCRIPT.get(base, base)


def guess_language(text: str) -> str | None:
    """Guess a reply's language group from its script (see module docstring)."""
    counts = Counter()
    for pattern, code in _SCRIPT_RES:
        n = len(pattern.findall(text))
        if n:
            counts[code] = n
    latin = len(regex.findall(r"\p{Latin}", text))
    if counts and max(counts.values()) >= latin * 0.3:
        return counts.most_common(1)[0][0]
    if latin == 0:
        return None
    tokens = regex.findall(r"\p{Latin}+", text.lower())
    hindi_hits = sum(1 for t in tokens if t in ROMAN_HINDI_WORDS)
    return "hi" if tokens and hindi_hits / len(tokens) >= 0.2 else "en"


def analyse_language(data: CallData, mishearings: MishearingSection, code_mixing_rating: int | None) -> LanguageSection:
    selected = data.call.language_selected
    detected = Counter(u.language or "unknown" for u in data.transcript if u.role == "caller")

    checked = correct = 0
    wrong = []
    caller_lang = None  # language detected in the caller's latest turn
    caller_langs: set[str] = set()  # every language the caller has used so far
    for u in data.transcript:
        if u.role == "caller":
            caller_lang = base_language(u.language) or caller_lang
            if caller_lang:
                caller_langs.add(caller_lang)
            continue
        expected = base_language(selected) if selected != "auto" else caller_lang
        got = guess_language(u.text)
        if expected is None or got is None:
            continue
        checked += 1
        # Replying in the language the caller just used is also fine (e.g. caller switched to English).
        # In auto mode, any language the caller has used in this call is fine (a Hindi caller who
        # says one English place name still expects Hindi replies).
        ok = got == expected or got == caller_lang or (selected == "auto" and got in caller_langs)
        correct += int(ok)
        if not ok:
            wrong.append({"time": fmt_time(u.offset_s), "text": short(u.text, 90), "expected": expected, "got": got})

    by_language = Counter(m.language or "unknown" for m in mishearings.items if m.offset_s is not None)
    return LanguageSection(
        selected=selected,
        detected=[LanguageCount(language=lang, caller_turns=n) for lang, n in detected.most_common()],
        agent_turns_checked=checked,
        agent_correct_language_pct=round(100 * correct / checked, 1) if checked else None,
        wrong_language_turns=wrong,
        code_mixing_rating=code_mixing_rating,
        mishearings_by_language=dict(by_language),
        method_note=("Agent reply language is guessed from its script, and for Latin text from common "
                     "romanized Hindi words (Hinglish counts as Hindi). A reply in the caller's own latest "
                     "language also counts as correct. Approximate."),
    )


def language_score(lang: LanguageSection) -> float | None:
    """0-100: 80% correct-language replies, 20% tester code-mixing rating (re-weighted if missing)."""
    parts = []
    if lang.agent_correct_language_pct is not None:
        parts.append((0.8, lang.agent_correct_language_pct / 100))
    if lang.code_mixing_rating is not None:
        parts.append((0.2, (lang.code_mixing_rating - 1) / 4))
    if not parts:
        return None
    return round(100 * sum(w * v for w, v in parts) / sum(w for w, _ in parts), 1)
