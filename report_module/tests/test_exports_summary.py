"""Exports (JSON/Markdown/PDF), file names, sample reports and the AI-summary number check."""

import json

import pytest

from report_module.exporters.json_schema import report_json_schema, to_json
from report_module.exporters.markdown import to_markdown
from report_module.exporters.pdf import to_pdf
from report_module.report_builder import build_report
from report_module.schema import Ratings, Report
from report_module.service import export_filename
from report_module.settings import DEFAULTS
from report_module.summary_llm import build_facts, unverified_numbers
from tests.helpers import call_data, caller, load_sample

PROVIDERS = ["sarvam", "openai", "gemini", "elevenlabs"]


@pytest.fixture(scope="module")
def reports():
    return {p: build_report(load_sample(p), Ratings(naturalness=4, clarity=4), DEFAULTS) for p in PROVIDERS}


def test_all_samples_build_same_shape(reports):
    keys = {p: set(json.loads(to_json(r)).keys()) for p, r in reports.items()}
    assert len({frozenset(k) for k in keys.values()}) == 1  # identical top-level shape for every provider
    for r in reports.values():
        assert r.schema_version == "1.0" and 0 <= r.summary.overall_score <= 100


def test_json_round_trip_and_schema(reports):
    for r in reports.values():
        assert Report.model_validate_json(to_json(r)) == r
    schema = report_json_schema()
    assert schema["title"] and "summary" in schema["properties"]


def test_markdown_has_all_sections_and_notices(reports):
    md = to_markdown(reports["gemini"])
    for n in range(1, 11):
        assert f"## {n}." in md
    assert "TEST MODE - dummy data only" in md and "must be reviewed by a team member" in md
    assert "முப்பத்தி ரெண்டு" in md  # Tamil text kept


def test_pdf_renders(reports):
    pdf = to_pdf(reports["elevenlabs"])
    assert pdf[:5] == b"%PDF-" and len(pdf) > 20_000


def test_export_filename(reports):
    name = export_filename(reports["sarvam"], "pdf")
    assert name == "report_sarvam_sarvam-105b-conversations_auto_2026-10-27_sample-sarvam-01.pdf"
    assert ":" not in export_filename(reports["openai"], "md")


def test_no_pii_reaches_any_export():
    data = call_data(transcript=[caller("Mera number 98765 43210 hai, Aadhaar 2345 6789 0123", 1)])
    r = build_report(data, None, DEFAULTS)
    for text in (to_json(r), to_markdown(r)):
        assert "98765" not in text and "2345 6789" not in text
    assert r.pii.masked_count == 2 and r.issues[0].title == "Possible real personal data"


def test_summary_number_check(reports):
    facts = build_facts(reports["sarvam"])
    good = f"The call scored {round(reports['sarvam'].summary.overall_score)} out of 100."
    assert unverified_numbers(good, facts) == []
    assert unverified_numbers("The call scored 12345 out of 100.", facts) == ["12345"]


def test_summary_off_by_default(reports):
    assert reports["sarvam"].ai_summary.status == "off"
