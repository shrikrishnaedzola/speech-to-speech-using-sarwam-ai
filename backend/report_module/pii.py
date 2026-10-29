"""Mask anything that looks like a phone number or Aadhaar number.

Runs on the CallData BEFORE any metric, export or AI summary, so masked
values can never reach a report, a PDF or an LLM.

Detected (digits may be separated by spaces or dashes, and may be written
in Indian-script digits such as ९८७६...):
- Phone:   10 digits starting 6-9, optionally prefixed by +91 / 91 / 0
- Aadhaar: 12 digits starting 2-9 (usually written 4-4-4)

Numbers spoken as words ("nau aath saat ...") are not detected.
"""

import re
from typing import Any

from report_module.schema import CallData

_NATIVE_DIGITS = "०१२३४५६७८९০১২৩৪৫৬৭৮৯੦੧੨੩੪੫੬੭੮੯૦૧૨૩૪૫૬૭૮૯୦୧୨୩୪୫୬୭୮୯௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯೦೧೨೩೪೫೬೭೮೯൦൧൨൩൪൫൬൭൮൯"
# Every native digit maps to one ASCII digit, so string positions stay the same.
_TO_ASCII = str.maketrans({ch: str(i % 10) for i, ch in enumerate(_NATIVE_DIGITS)})

# A run of digits with optional single spaces/dashes between them, optional leading "+".
_DIGIT_RUN = re.compile(r"(?<![\d])\+?\d(?:[ \-]?\d){8,15}(?![\d])")

PHONE_MASK = "[PHONE MASKED]"
AADHAAR_MASK = "[AADHAAR MASKED]"


PHONE_PREFIXES = ("", "0", "91", "091", "0091")  # trunk / country code before a 10-digit mobile


def _classify(digits: str) -> str | None:
    for prefix in PHONE_PREFIXES:
        rest = digits[len(prefix):]
        if digits.startswith(prefix) and len(rest) == 10 and rest[0] in "6789":
            return "phone"
    if len(digits) == 12 and digits[0] in "23456789":
        return "aadhaar"
    return None


def mask_text(text: str) -> tuple[str, list[str]]:
    """Return (masked text, list of kinds found e.g. ["phone"])."""
    if not text:
        return text, []
    ascii_view = text.translate(_TO_ASCII)
    found: list[str] = []
    pieces, last = [], 0
    for m in _DIGIT_RUN.finditer(ascii_view):
        kind = _classify(re.sub(r"\D", "", m.group()))
        if kind is None:
            continue
        found.append(kind)
        pieces.append(text[last : m.start()])
        pieces.append(PHONE_MASK if kind == "phone" else AADHAAR_MASK)
        last = m.end()
    if not found:
        return text, []
    pieces.append(text[last:])
    return "".join(pieces), found


def _mask_any(value: Any, found: list[str]) -> Any:
    """Mask strings anywhere inside dicts/lists (tool arguments, results...)."""
    if isinstance(value, str):
        masked, kinds = mask_text(value)
        found.extend(kinds)
        return masked
    if isinstance(value, int) and not isinstance(value, bool):
        masked, kinds = mask_text(str(value))
        if kinds:
            found.extend(kinds)
            return masked
        return value
    if isinstance(value, list):
        return [_mask_any(v, found) for v in value]
    if isinstance(value, dict):
        return {k: _mask_any(v, found) for k, v in value.items()}
    return value


def mask_call_data(data: CallData) -> tuple[CallData, list[str]]:
    """Return a masked copy of the call data and the kinds of PII found."""
    found: list[str] = []
    raw = data.model_dump(mode="json")
    for key in ("transcript", "answers", "reviews", "turns", "tool_calls", "expected_script", "errors"):
        raw[key] = _mask_any(raw[key], found)
    return CallData.model_validate(raw), found


def pii_warnings(found: list[str]) -> list[str]:
    if not found:
        return []
    phones, aadhaars = found.count("phone"), found.count("aadhaar")
    parts = []
    if phones:
        parts.append(f"{phones} phone-like number(s)")
    if aadhaars:
        parts.append(f"{aadhaars} Aadhaar-like number(s)")
    return [
        f"Masked {' and '.join(parts)} in this call. Test calls must use dummy data only - "
        "check the call and do not share the raw recording or database."
    ]
