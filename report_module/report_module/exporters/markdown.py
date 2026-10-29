"""Markdown export (templates/report.md.j2)."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from report_module.schema import Report

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

LABELS = {"accuracy": "Accuracy", "mishearings": "Mishearings", "latency": "Latency",
          "voice_quality": "Voice quality", "language": "Language support", "cost": "Cost"}
KINDS = {"transcription": "Transcription error", "caller_correction": "Caller corrected it",
         "value_changed": "Answer changed", "wrong_value": "Wrong saved value", "number_misheard": "Number misheard"}
ISSUE_KINDS = {"long_silence": "Long silence", "talk_over": "Talking over", "cut_off": "Cut-off sentence",
               "repeated_phrase": "Repeated phrase"}
MARKS = {"mishearing": "🔴 mishearing", "reasked": "🟠 re-asked", "interruption": "🟣 interrupted", "tool": ""}
RATING_LABELS = [("naturalness", "Naturalness"), ("clarity", "Clarity"), ("pronunciation", "Pronunciation"),
                 ("accent_fit", "Accent fit"), ("politeness", "Politeness / tone"), ("code_mixing", "Code-mixing")]


def ms(v):
    return "-" if v is None else (f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.0f} ms")


def pct(v, digits=0):
    return "-" if v is None else f"{v * 100:.{digits}f}%"


def cell(text) -> str:
    """Make text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(report: Report) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), trim_blocks=False, lstrip_blocks=False, autoescape=False)
    env.filters["cell"] = cell
    return env.get_template("report.md.j2").render(
        r=report, labels=LABELS, kinds=KINDS, issue_kinds=ISSUE_KINDS, marks=MARKS,
        rating_labels=RATING_LABELS, ms=ms, pct=pct,
    )
