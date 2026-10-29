# report_module - shared post-call report for the Zolabs voice testers

One Python package used by all four tester apps (OpenAI, Sarvam, Gemini, ElevenLabs). Every report has
the same 10 sections, uses the same scoring formula, and exports the same JSON shape, so results can be
compared directly.

> **TEST MODE - dummy data only.** Phone- and Aadhaar-like numbers are masked before anything is computed,
> exported or sent to an LLM. Reports are AI-assisted and must be reviewed by a team member before they
> are shared outside EdZola.

```
tester DB ──adapter──► CallData ──► metrics ──► Report ──► React page / PDF / Markdown / JSON
(different per app)    (fixed)                  (fixed, schema_version 1.0)
```

## What's in the report

1. **Call summary:**
   - overall score (0-100) and verdict (Good ≥ 75, Needs improvement 50-74, Poor < 50);
   - a score for each section;
   - 3 strengths and 3 problems.
2. **Transcript:** the conversation as chat bubbles. Mishearings are red, re-asked questions orange, tool calls blue, interruptions purple.
3. **Mishearings:**
   - WER and CER against the expected caller script, if one exists. CER counts *visible letters* (graphemes), which is fair for Indian scripts.
   - caller corrections ("No, I said…", "nahi, maine kaha…", Tamil, Telugu, Devanagari);
   - answers that changed;
   - numbers misheard (e.g. caller said 45, 54 saved);
   - wrong final values.

   Each item shows when it happened, what was said, what was heard, the field, and whether it was fixed later.
4. **Voice quality:**
   - tester ratings 1-5, entered on the report page;
   - optional DNSMOS score;
   - audio issues found in the logs: long silences (> 2 s), talking over each other, cut-off replies, repeated phrases.
5. **Latency:**
   - average, median, p90 and max reply time;
   - a Good / OK / Poor rating;
   - a chart per turn, stacked STT / LLM / TTS for cascaded pipelines like Sarvam;
   - the 3 slowest turns, with what was happening.
6. **Language support:**
   - language selected vs detected;
   - % of agent replies in the correct language (guessed from the script; Hinglish counts as Hindi);
   - code-mixing rating;
   - mishearings per language.
7. **Accuracy:**
   - field accuracy and completion;
   - follow-up questions asked only when needed;
   - error recovery;
   - tool-call stats;
   - a field table (expected / saved / correct / notes).
8. **Cost:**
   - USD and INR, with a line-item breakdown per provider;
   - per minute and per completed form;
   - projection for 1,000 similar calls;
   - the "rates last updated" date.
9. **Issues and recommendations:** rule-based, sorted High / Medium / Low, each with a simple suggestion.
10. **AI-written summary (optional):** written by Claude from the computed numbers only. Every number in it is checked against the input; if any number isn't found there, the summary is flagged.

### Overall score

The overall score is a weighted average of the six section scores. Weights are editable on the report page:

| Section | Default weight |
|---|---|
| Accuracy | 35% |
| Mishearings | 15% |
| Latency | 20% |
| Voice quality | 15% |
| Language support | 10% |
| Cost | 5% |

If a section has no data yet (for example no tester ratings), it is left out and the other weights are
scaled up. The report says when this happens.

How each section is scored (all in `scoring.py` and the section modules):

| Section | Score |
|---|---|
| Accuracy | 60% field accuracy + 25% completion + 15% follow-up correctness |
| Mishearings | 100 − 15 per unfixed − 5 per fixed, and never above 100 × (1 − CER) |
| Latency | 100 up to 1 s, 50 at 1.5 s, 0 at 3 s (average reply time) |
| Voice quality | 70% tester ratings + 30% MOS, minus 5 per audio issue (at most −20) |
| Language | 80% correct-language replies + 20% code-mixing rating |
| Cost | 100 at or below the target ₹ per minute (default ₹3), 0 at 3× the target |

## Install (in each tester's backend virtual environment)

```bash
pip install -e ../report_module                 # core
pip install -e "../report_module[mos]"          # + optional DNSMOS speech-quality score
pip install -e "../report_module[summary]"      # + optional AI summary (Claude)
python -m report_module.voice_quality --download   # DNSMOS model (1.1 MB, checksum-verified)
```

## Plug it into a tester app (4 steps)

**1. Write an adapter: call_id → `CallData`.**
- **Sarvam:** already done, in `adapters/sarvam.py`.
- **Other testers:** copy `adapters/template.py` and fill each field from your tables (the checklist is in the file).
- **Testers that can export JSON:** `json_file_adapter(folder)` reads `<folder>/<call_id>.json` in the `CallData` shape.

**2. Create the service and mount the API.**

```python
from report_module.adapters.base import SAMPLE_DATA_DIR, first_of, json_file_adapter
from report_module.router import make_report_router
from report_module.service import ReportService

report_service = ReportService(
    adapter=first_of(my_tester_adapter(engine), json_file_adapter(SAMPLE_DATA_DIR)),  # 2nd = demo samples
    engine=engine,                                 # the tester's SQLAlchemy engine (SQLite)
    settings_path="data/report_settings.json",
)
app.include_router(make_report_router(report_service))
```

The module adds two tables to the tester's database: `report_ratings` and `reports`. The tester's own
tables are never changed.

**3. Generate the report automatically when a call ends, and when `complete_form` succeeds.**
Run `report_service.generate(call_id)` in a background thread, then tell the UI. For a working example,
see `backend/app/services/report_hook.py` in the Sarvam tester, which sends a `report_ready` event.

**4. Frontend.**
1. Copy `frontend/src/components/report/` into the tester (it only needs React, Recharts and Tailwind).
2. Run `npm install recharts@2`.
3. Route `/report/<call_id>` to `ReportPage` (see `frontend/src/main.jsx`).
4. Show a "Report ready" link when the `report_ready` event arrives.

## API (added by the router)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/calls/{call_id}/report` | Generate or regenerate the report |
| GET | `/api/calls/{call_id}/report` | Get the report JSON (404 if not generated yet) |
| GET / POST | `/api/calls/{call_id}/ratings` | Read or save tester ratings (1-5) |
| GET | `/api/calls/{call_id}/report/export?format=pdf\|md\|json` | Download the report |
| GET / PUT | `/api/report/settings` | Weights, exchange rate, cost target, optional features |
| GET | `/api/report/schema` | JSON schema for the comparison tool |

Download file names follow `report_{provider}_{model}_{language}_{date}_{call_id}.{ext}`, with unsafe characters replaced.

## JSON for the comparison tool

Every report validates against `report_module/report.schema.json` (`schema_version: "1.0"`), whatever
the provider. Regenerate the schema after changing `schema.py`:

```bash
python -m report_module.exporters.json_schema
```

## Sample data (no real call needed)

`report_module/sample_data/` contains 4 fake calls, one per provider. Each shows different problems:

| Sample | Shows |
|---|---|
| `sample-sarvam-01` | Hinglish; STT misheard a number; the caller corrected it |
| `sample-openai-01` | English; fast replies; a misheard number fixed by the caller; one invalid tool call |
| `sample-gemini-01` | Tamil, phone 8 kHz; numbers misheard; English replies on a Tamil call |
| `sample-elevenlabs-01` | Hindi; slow replies; a follow-up asked wrongly; form not completed |

To regenerate them: `python -m report_module.sample_data.make_samples`. In the Sarvam tester, open
`http://localhost:5180/report/sample-gemini-01` (and so on).

## Optional features

**Speech quality score (DNSMOS).** Microsoft's DNSMOS P.835 runs locally on CPU (onnxruntime); nothing is
uploaded.
- **Licence:** code MIT, model CC-BY-4.0. Attribution: "DNSMOS P.835, Microsoft".
- **What it measures:** how clean the audio is (signal, background noise, overall), **not** how natural the voice sounds.
- **What it needs:** a 16-bit WAV of the agent's audio. The Sarvam tester records only the agent's speech turns into `backend/data/recordings/` (git-ignored, dummy calls only).
- **Turn on:** "Report settings" on the report page.

**AI summary (Claude).**
- **Model:** `claude-opus-5-5` by default (`ai_summary_model` in settings), effort `low`.
- **Fallback:** the API's server-side refusal fallback is on, so a declined request is retried on a fallback model.
- **Key:** `ANTHROPIC_API_KEY` in the tester's `.env`. It is never logged or written to a report.
- **What it sees:** only the facts sheet and the masked transcript.
- **Turn on:** "Report settings" on the report page.

## Cost rates

Default rates are in `settings.py` (taken from public pricing pages on 2026-10-28; USD → INR 95.5).
Prices change, so check them and edit `data/report_settings.json`, including `rates_last_updated`.

| Provider | Default rates |
|---|---|
| OpenAI | gpt-realtime audio: $32 in / $64 out per 1M tokens ($0.40 cached); text: $4 / $16 |
| Gemini Live | audio: $3 / $12 per 1M tokens; text: $0.75 / $4.50 |
| ElevenLabs Agents | $0.08 per minute, plus an LLM estimate of $0.01 per minute |
| Sarvam | STT ₹0.49/min; Bulbul v3 ₹30 or v4 Flash ₹10 per 10K characters; LLM ₹15 / ₹60 per 1M tokens |

## Known limits

- **Expected script:** compared turn by turn, in order. If the caller skips or adds a turn, later turns no longer line up.
- **Reply language:** guessed from the script, with a word list for romanized Hindi. Marathi and Hindi share Devanagari, and Bengali and Assamese share a script, so each pair counts as one group.
- **Spoken numbers:** understood from 0-100 in Hindi, Tamil, Telugu and English, plus native digits.
- **PII masking:** only digit-based phone and Aadhaar numbers are masked. Numbers spoken as words are not detected.
- **Silences:** come from turn timings, not from the recording.

## Tests

```bash
cd report_module
python -m pytest -q
```

Run with the backend's Python environment. The 79 tests cover:
- WER/CER (English, Hindi, Tamil);
- correction detection and number checks;
- latency stats, accuracy, cost per provider, overall score and weights;
- PII masking;
- exports (JSON, Markdown, PDF) and the AI-summary number check.

They make no network calls.

_Built with AI assistance (Claude Code). Needs human review before merge, per the EdZola policy._
