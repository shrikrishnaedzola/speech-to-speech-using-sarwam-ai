"""PDF export (fpdf2).

Indian scripts need "text shaping" (joining letters and vowel signs correctly).
fpdf2 does this with HarfBuzz (uharfbuzz) when set_text_shaping(True) is on.
Fonts: Noto Sans for Latin, plus one Noto font per Indian script as fallback
(SIL Open Font License, see templates/fonts/OFL.txt).

Every page has the footer:
  "TEST MODE - dummy data only" + the "AI-assisted test report..." review notice.
"""

import io
from pathlib import Path

from fpdf import FPDF, FontFace
from fpdf.enums import XPos, YPos

try:
    from report_module.exporters.charts import latency_chart, section_scores_chart
except ImportError:  # matplotlib is optional (left out of the slim Vercel build): PDF is built without charts
    def latency_chart(r):
        return None

    def section_scores_chart(r):
        return None

from report_module.exporters.markdown import ISSUE_KINDS, KINDS, LABELS, RATING_LABELS, ms, pct
from report_module.schema import Report

FONTS = Path(__file__).resolve().parent.parent / "templates" / "fonts"
SCRIPT_FONTS = ["Devanagari", "Tamil", "Telugu", "Bengali", "Gujarati", "Gurmukhi", "Kannada", "Malayalam", "Oriya"]

# Text colours (RGB). Highlight colours always come with a text label too.
INK, MUTED = (30, 30, 30), (110, 110, 105)
RED, ORANGE, BLUE, PURPLE, GREEN = (190, 30, 30), (200, 100, 0), (30, 90, 190), (120, 50, 170), (20, 120, 60)
HIGHLIGHT = {"mishearing": ("MISHEARING", RED), "reasked": ("RE-ASKED", ORANGE),
             "interruption": ("INTERRUPTED", PURPLE)}


class ReportPDF(FPDF):
    def __init__(self, report: Report):
        super().__init__(format="A4")
        self.report = report
        self.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
        self.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
        for script in SCRIPT_FONTS:
            self.add_font(f"Noto{script}", "", str(FONTS / f"NotoSans{script}-Regular.ttf"))
        self.set_fallback_fonts([f"Noto{s}" for s in SCRIPT_FONTS], exact_match=False)
        self.set_text_shaping(True)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(14, 14, 14)
        self.set_title(f"Post-call report {report.call.call_id}")
        self.set_author("Zolabs voice tester (AI-assisted)")

    def footer(self):
        self.set_y(-14)
        self.set_font("Noto", "", 7)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 3.5, f"{self.report.test_mode_notice}  ·  {self.report.review_notice}  ·  page {self.page_no()}",
                        align="C")

    # --- small helpers ---------------------------------------------------
    def h1(self, text):
        self.set_font("Noto", "B", 15)
        self.set_text_color(*INK)
        self.multi_cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def h2(self, text):
        if self.get_y() > 250:
            self.add_page()
        self.ln(3)
        self.set_font("Noto", "B", 12)
        self.set_text_color(*INK)
        self.multi_cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(220, 220, 215)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.5)

    def para(self, text, size=9, color=INK, bold=False):
        self.set_font("Noto", "B" if bold else "", size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.55, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def table(self, head, rows, widths=None, size=8):
        self.set_font("Noto", "", size)
        self.set_text_color(*INK)
        with super().table(col_widths=widths, text_align="LEFT", line_height=size * 0.55, padding=1,
                           headings_style=FontFace(emphasis="BOLD", fill_color=(240, 240, 235)),
                           first_row_as_headings=True) as t:
            r = t.row()
            for h in head:
                r.cell(h)
            for row in rows:
                r = t.row()
                for c in row:
                    r.cell("" if c is None else str(c))
        self.ln(2)


def to_pdf(report: Report) -> bytes:
    r = report
    pdf = ReportPDF(r)
    pdf.add_page()

    # Banner + title
    pdf.set_fill_color(251, 191, 36)
    pdf.set_font("Noto", "B", 10)
    pdf.cell(0, 7, r.test_mode_notice, align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_fill_color(255, 255, 255)  # tables must not inherit the banner colour
    pdf.ln(2)
    pdf.h1(f"Post-call report: {r.call.provider} · {r.call.model}")
    pdf.para(f"Call {r.call.call_id} · {r.call.started_at:%Y-%m-%d %H:%M} UTC · generated {r.generated_at:%Y-%m-%d %H:%M} UTC",
             8, MUTED)
    for w in r.pii.warnings:
        pdf.para(f"Warning: {w}", 9, RED, bold=True)

    # 1. Summary
    pdf.h2("1. Call summary")
    pdf.para(f"Overall score: {round(r.summary.overall_score)} / 100 - {r.summary.verdict}", 13, INK, bold=True)
    pdf.table(["Provider", "Model", "Voice", "Language", "Audio", "Duration", "Mode"],
              [[r.call.provider, r.call.model, r.call.voice or "-", r.call.language_selected,
                "Phone 8 kHz" if r.call.audio_mode == "phone_8khz" else "Normal", f"{round(r.call.duration_s)} s", r.call.mode]])
    scores_chart = section_scores_chart(r)
    if scores_chart:
        pdf.image(io.BytesIO(scores_chart), w=150)
    if r.summary.missing_sections:
        pdf.para("Not in the score (no data): " + ", ".join(LABELS[k] for k in r.summary.missing_sections), 8, MUTED)
    pdf.para("Key strengths", 9, GREEN, bold=True)
    for s in r.summary.strengths or ["None found."]:
        pdf.para(f"•  {s}", 9)
    pdf.para("Key problems", 9, RED, bold=True)
    for s in r.summary.problems or ["None found."]:
        pdf.para(f"•  {s}", 9)

    # 2. Transcript
    pdf.h2("2. Transcript")
    pdf.para("Labels: MISHEARING (red) · RE-ASKED (orange) · TOOL (blue) · INTERRUPTED (purple)", 7.5, MUTED)
    for t in r.transcript:
        if t.role == "tool":
            status = "ok" if t.tool and t.tool["success"] else "FAILED"
            extra = f" - {t.tool['error']}" if t.tool and t.tool.get("error") else ""
            pdf.para(f"{t.time}   TOOL {status}: {t.text}{extra}", 7.5, BLUE)
            continue
        who = "Agent" if t.role == "agent" else "Caller"
        lang = f" ({t.language})" if t.language else ""
        labels = [HIGHLIGHT[h] for h in t.highlights if h in HIGHLIGHT]
        color = labels[0][1] if labels else INK
        tags = "  [" + ", ".join(lbl for lbl, _ in labels) + "]" if labels else ""
        pdf.para(f"{t.time}   {who}{lang}: {t.text}{tags}", 8.5, color)

    # 3. Mishearings
    m = r.mishearings
    pdf.h2("3. Mishearings")
    rates = (f"WER {pct(m.wer, 1)}, CER {pct(m.cer, 1)} ({m.aligned_turns} turns vs expected script)."
             if m.script_available else "No expected script, so no WER/CER.")
    pdf.para(f"{m.total} found, {m.fixed} fixed during the call. {rates}", 9)
    if m.items:
        pdf.table(["Time", "Type", "Caller said", "AI heard / saved", "Field", "Fixed?"],
                  [[i.time or "-", KINDS[i.kind], i.said, i.heard + (f" ({i.detail})" if i.detail else ""), i.field_id or "-",
                    "unknown" if i.fixed is None else ("yes" if i.fixed else "no")] for i in m.items],
                  widths=(10, 22, 40, 48, 24, 12), size=7.5)

    # 4. Voice quality
    vq = r.voice_quality
    pdf.h2("4. Voice quality")
    avg = f"{vq.rating_average:.1f} / 5" if vq.rating_average is not None else "not rated"
    mos = (f"overall {vq.mos.ovrl}, signal {vq.mos.sig}, noise {vq.mos.bak} ({vq.mos.model})" if vq.mos else vq.mos_status)
    pdf.para(f"Tester rating average: {avg}.  Automatic MOS: {mos}.", 9)
    given = [(label, getattr(vq.ratings, key)) for key, label in RATING_LABELS if getattr(vq.ratings, key) is not None]
    if given:
        pdf.table([g[0] for g in given], [[f"{g[1]} / 5" for g in given]])
    if vq.ratings.notes:
        pdf.para(f"Tester notes: {vq.ratings.notes}", 8.5)
    pdf.para("Audio issues:", 9, bold=True)
    for i in vq.issues or []:
        pdf.para(f"{i.time or '-'}   {ISSUE_KINDS[i.kind]}: {i.detail}", 8.5)
    if not vq.issues:
        pdf.para("None found.", 8.5)

    # 5. Latency
    lat = r.latency
    pdf.h2("5. Latency")
    pdf.para(f"Average {ms(lat.average_ms)} · median {ms(lat.median_ms)} · p90 {ms(lat.p90_ms)} · max {ms(lat.max_ms)} · "
             f"rating {lat.rating or '-'} (Good < 1 s, OK 1-1.5 s, Poor > 1.5 s)", 9)
    chart = latency_chart(r)
    if chart:
        pdf.image(io.BytesIO(chart), w=180)
    pdf.para("Slowest turns:", 9, bold=True)
    for s in lat.slowest:
        pdf.para(f"Turn {s.turn_index}: {ms(s.total_ms)} - {s.reason}", 8.5)

    # 6. Language
    lg = r.language
    pdf.h2("6. Language support")
    detected = ", ".join(f"{d.language} ({d.caller_turns})" for d in lg.detected) or "-"
    correct = f"{lg.agent_correct_language_pct:.0f}%" if lg.agent_correct_language_pct is not None else "-"
    pdf.para(f"Selected: {lg.selected}. Detected in caller turns: {detected}.", 9)
    pdf.para(f"Agent replied in the correct language: {correct} of {lg.agent_turns_checked} turns. "
             f"Code-mixing rating: {str(lg.code_mixing_rating) + ' / 5' if lg.code_mixing_rating else 'not rated'}. "
             f"Mishearings by language: {', '.join(f'{k}: {v}' for k, v in lg.mishearings_by_language.items()) or 'none'}.", 9)
    for w in lg.wrong_language_turns:
        pdf.para(f"{w['time']}   expected {w['expected']}, got {w['got']}: {w['text']}", 8.5, ORANGE)
    pdf.para(lg.method_note, 7.5, MUTED)

    # 7. Accuracy
    a = r.accuracy
    pdf.h2("7. Accuracy (form data)")
    pdf.para(f"Field accuracy {pct(a.field_accuracy)} ({a.correct} of {a.reviewed} checked) · completion {pct(a.completion)} "
             f"({a.required_filled} of {a.required_total} required) · follow-ups {a.followups_correct}/{a.followups_total} correct · "
             f"invalid answers fixed {a.invalid_answers_fixed}/{a.invalid_answers} · tool calls {a.tool_calls_total} "
             f"(success {pct(a.tool_success_rate)}, {a.invalid_tool_calls} invalid JSON, {a.validation_errors} validation errors)", 9)
    for f in a.followup_issues:
        pdf.para(f"Follow-up problem: {f}", 8.5, RED)
    pdf.table(["Field", "Expected", "Saved", "Correct?", "Notes"],
              [[row.label, row.expected or "-", row.saved or "-",
                "not checked" if row.correct is None else ("yes" if row.correct else "NO"), row.notes] for row in a.table],
              widths=(36, 30, 36, 18, 62), size=7.5)

    # 8. Cost
    c = r.cost
    pdf.h2("8. Cost")
    per_form = f"₹{c.per_completed_form_inr:.2f}" if c.per_completed_form_inr is not None else "- (form not completed)"
    pdf.para(f"This call ₹{c.total_inr:.2f} (${c.total_usd:.4f}) · per minute ₹{c.per_minute_inr or 0:.2f} · "
             f"per completed form {per_form} · 1,000 similar calls ₹{c.projection_1000_inr:,.0f} (${c.projection_1000_usd:,.2f})", 9)
    pdf.table(["Item", "Quantity", "Rate", "USD", "INR"],
              [[i.label, f"{i.quantity:g} {i.unit}", f"{'₹' if i.rate_currency == 'INR' else '$'}{i.rate}",
                f"{i.cost_usd:.4f}", f"{i.cost_inr:.2f}"] for i in c.items], widths=(60, 34, 30, 28, 30))
    pdf.para(f"Rates last updated {c.rates_last_updated} · 1 USD = ₹{c.usd_to_inr}. {c.note}", 7.5, MUTED)

    # 9. Issues
    pdf.h2("9. Issues and recommendations")
    colors = {"High": RED, "Medium": ORANGE, "Low": BLUE}
    for i in r.issues:
        pdf.para(f"[{i.severity}] {i.title}", 9, colors[i.severity], bold=True)
        pdf.para(i.detail, 8.5)
        pdf.para(f"→ {i.suggestion}", 8.5, GREEN)
    if not r.issues:
        pdf.para("No issues found.", 9)

    # 10. AI summary
    pdf.h2("10. AI-written summary")
    s = r.ai_summary
    if s.status in ("ok", "flagged"):
        pdf.para(s.label, 8.5, ORANGE, bold=True)
        if s.status == "flagged":
            pdf.para(f"Warning: numbers not found in the report data: {', '.join(s.unverified_numbers)}. Check before use.", 8.5, RED)
        pdf.para(s.text or "", 9)
    elif s.status == "error":
        pdf.para(f"Could not write the summary: {s.text}", 9, RED)
    else:
        pdf.para("Off.", 9, MUTED)

    return bytes(pdf.output())
