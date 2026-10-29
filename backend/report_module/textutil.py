"""Small text helpers shared by the metric modules."""

import unicodedata

import regex  # supports \X (grapheme clusters) and \p{...} classes


def normalize(text: str) -> str:
    """Lowercase, Unicode NFC, punctuation removed, single spaces.

    Used before comparing texts, so "Haan, ji!" equals "haan ji".
    """
    text = unicodedata.normalize("NFC", text or "").lower()
    text = regex.sub(r"[\p{P}\p{S}]+", " ", text)  # punctuation incl. Hindi danda (।)
    return " ".join(text.split())


def words(text: str) -> list[str]:
    return normalize(text).split()


def graphemes(text: str) -> list[str]:
    """User-perceived characters, spaces removed.

    In Indian scripts one visible letter is often several code points
    (consonant + vowel sign, conjuncts). Counting graphemes keeps CER fair.
    Example: "कि" is 2 code points but 1 grapheme.
    """
    return [g for g in regex.findall(r"\X", normalize(text)) if not g.isspace()]


def fmt_time(offset_s: float | None) -> str | None:
    """Seconds since call start -> "mm:ss"."""
    if offset_s is None:
        return None
    offset_s = max(0, int(round(offset_s)))
    return f"{offset_s // 60:02d}:{offset_s % 60:02d}"


def short(text: str, limit: int = 120) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
