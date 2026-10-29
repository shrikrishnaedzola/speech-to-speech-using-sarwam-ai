# Zolabs Voice Form Tester – Sarvam Pipeline

An **internal test tool**, not for production use. It checks how well a Sarvam AI voice pipeline handles a
phone-style survey call: it asks the form's questions one by one, asks follow-ups, saves the answers as
structured data, and times every step of every turn.

```
Caller voice ─► Saaras STT ─► Sarvam-105B LLM (+ tools) ─► Bulbul TTS ─► agent voice
   (browser WebRTC)        all inside the FastAPI backend (Pipecat)        (browser)
```

> **TEST MODE – use dummy data only.** Never use real names, phone numbers, Aadhaar numbers or any real
> beneficiary data.

---

## 1. Setup (Windows, macOS or Linux)

You need **Python 3.11 or 3.12** and **Node 18 or newer**.
(Use Python 3.12, not 3.13: Pipecat still uses `audioop`, which Python 3.13 removed.)

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
# open backend/.env and set SARVAM_API_KEY=<your key>

# Frontend
cd ../frontend
npm install
```

The API key is read **only** by the backend, from `backend/.env`. That file is git-ignored. The browser
never sees the key: every Sarvam call goes through the backend.

## 2. Run

Use two terminals:

```bash
# Terminal 1 – backend on http://localhost:8010
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8010

# Terminal 2 – frontend on http://localhost:5180 (forwards /api to the backend)
cd frontend
npm run dev
```

Open **http://localhost:5180**. Ports 8010 and 5180 were picked to avoid the common 8000 and 5173,
which other apps were already using on the dev machine. To change them, edit
`frontend/vite.config.js` (both the port and the proxy target) and `CORS_ORIGINS` in `.env`.

## 3. Run a test call

1. **Try Simulate first. It is free.** Click **Simulate**. A saved dummy Hinglish call
   (`backend/app/simulate/sample_call.json`) plays back through the **real** tool and validation code
   without using the mic or Sarvam. The timings shown in this mode are made up. The dummy call includes:
   - a rejected answer (age 150),
   - a malformed tool call,
   - a barge-in (the caller interrupting the agent),
   - a correction (2 children → 3).

   Use **Settings → Simulate speed** to run it faster.
2. **Live call.** Choose the form, models, voice, language and audio quality, then click **Start Call** and
   allow the microphone. Use a headset to avoid echo. The agent speaks first.
3. **While the call runs:**
   - Column 1 shows the transcript, with the detected language on each caller message.
   - Column 2 fills in the form cards. Follow-up questions appear only when their condition is met.
   - Column 3 shows a timing bar for each turn.
4. **After the call:** in Column 2, mark each filled answer **Correct** or **Wrong**. Typing an expected
   value marks the answer Wrong automatically. Then **Export JSON / CSV**.
   - **Accuracy** = correct ÷ reviewed filled fields.
   - **Completion** = filled required fields ÷ visible required fields.

**Phone 8 kHz** mode runs both STT input and TTS output at 8 kHz, so the call sounds like a phone line.

## 4. What was changed from the original brief (and why)

Everything below follows the Sarvam docs as of October 2026.

| Brief said | Docs say | What the tool does |
|---|---|---|
| LLM default `sarvam-30b` | Sarvam-30B is **deprecated**. The chat API now accepts only `sarvam-105b` and `sarvam-105b-conversations` ([API ref](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1), [models](https://docs.sarvam.ai/api/getting-started/models)) | The default is `sarvam-105b-conversations`, which is built for voice agents. `sarvam-105b` is the alternative. |
| "Lowest reasoning setting" | `-conversations` has no reasoning setting. For `sarvam-105b`, `reasoning_effort` accepts `low`/`high`/`max`, and `null` turns reasoning off. | The default is **off**: the tool sends `null` explicitly, because leaving it out uses the server's default level. The other option is `low`. |
| STT `language="unknown"` | The realtime STT endpoint uses `language_code=auto` ([realtime STT](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming)) | Uses `auto`. Each final transcript carries the detected language. In auto mode the TTS language follows the caller's language. |
| Endpointing about 70 ms | The 70 ms is LiveKit's `min_endpointing_delay`. Sarvam's Pipecat guide uses a 200 ms turn-stop timeout. | The **turn-stop timeout** defaults to 70 ms and can be changed. The Sarvam VAD silence window (default 500 ms) can also be changed. |
| TTS `bulbul:v3` | v3 is still supported on the TTS API (its end of life on 10 Nov 2026 applies to the Voice Agents product only). `bulbul:v4-flash` is recommended and about 3× cheaper, but it has **no Malayalam or Odia**. | v3 stays the default. v4-flash is available as an option, and calls in Malayalam or Odia fall back to v3. |

### Tool calling: native
Sarvam's chat API supports OpenAI-style function calling, so the four tools are sent as native `tools`
with a strict JSON schema, and `field_id` is limited to the form's own field IDs. The model sends tool
arguments as a JSON string, and that JSON can still be malformed. Every call is therefore parsed and checked
in `services/tool_schema.py`. A failure counts as a **JSON parse failure** in the metrics, and the error goes
back to the LLM so it retries.

Pipecat normally drops a tool call silently when its JSON is malformed. A small, commented patch in
`pipeline/runner.py` keeps these calls so they can be counted and retried. `save_answer.value` is a string
on purpose, because that is the most reliable type for the model to fill. The backend converts it (`"35"` →
35, `"5, 8"` → [5, 8]).

### Framework: Pipecat with the built-in browser WebRTC transport
- **No extra server.** Pipecat's built-in WebRTC transport runs inside the FastAPI process. LiveKit would
  need a LiveKit server plus a separate worker process.
- **Docs.** Sarvam publishes a Pipecat production guide.
- **Built-in Sarvam STT support.** Pipecat's realtime STT service supports `stream_type`, 8 kHz audio,
  `saaras:v4` and Sarvam's server VAD.
- **Per-step timing.** Pipecat passes timestamped events (frames) through the pipeline, so one observer
  can time each step.

Following the [Pipecat production guide](https://docs.sarvam.ai/api/integration/pipecat-production-guide):
- **No local VAD.** Sarvam's server VAD decides when the caller has finished.
- **Barge-in.** The caller starting to speak interrupts the agent.
- **TTS warm-up.** The TTS WebSocket is opened when the call starts and kept alive with pings.
- **Faster first audio.** `min_buffer_size` is set to 30 characters.

## 5. How response time is measured

`backend/app/pipeline/metrics.py` timestamps the pipeline events for each turn:

| Metric | From → to |
|---|---|
| **STT** | Sarvam `vad.speech_end` → final transcript |
| Turn wait | final transcript → LLM request (the turn-stop timeout) |
| **LLM TTFT** | LLM request → first token. Includes tool calls in that turn; `tool_ms` shows how much. |
| **TTS first audio** | first LLM token → first audio chunk. Includes waiting for `min_buffer_size` characters. |
| **Total** | Sarvam `vad.speech_end` → agent audio starts playing |

Sarvam sends `speech_end` only after its silence window, so the caller actually went quiet
`vad_silence_ms` (default 500 ms) earlier. That window is a setting and is **not** included in the total.

## 6. Export format

- **CSV** (`?format=csv`): one row per form field. The columns shared with the OpenAI tester come first, and
  the Sarvam-only `avg_stt_ms, avg_llm_ttft_ms, avg_tts_ttfb_ms` columns come last. Fields hidden by a
  follow-up rule are exported as `not_applicable`.
- **Turns CSV** (`?format=csv&section=turns`): one row per turn, with every timing.
- **JSON** (`?format=json`): the full report (settings, form, transcript, turns, tool calls, metrics,
  cost) plus the same rows as the CSV.

> ⚠️ The OpenAI tester's export file was not available when this tool was built. If its column names
> differ, edit `COMMON_COLUMNS` in `backend/app/services/export.py`, which is the only place they are
> defined.

## 7. Adding a form

Put a JSON file in `backend/app/seed_forms/` with the same shape as `program_feedback_survey.json`, then
restart the backend.
- **Field types:** `text`, `number` (`min`/`max`), `choice` (`choices`), `yes_no`, `number_list`
  (`item_min`/`item_max`/`length_equals_field`).
- **Follow-ups:** `"show_if": {"field": "...", "op": "eq|ne|gt|gte|lt|lte|in", "value": ...}`.
- **Required follow-ups:** a follow-up marked `required` is only required while its condition is true.

The system prompt is built from the form each time, so nothing about the form is hard-coded.

## 8. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/forms`, `/api/forms/{id}` | List forms, or get one form's definition |
| GET | `/api/options` | Dropdown options and default settings |
| POST | `/api/session` | Create a live call and return the WebRTC offer URL and events URL |
| POST | `/api/webrtc/offer?call_id=` | Exchange WebRTC offer/answer (starts the pipeline) |
| POST | `/api/session/{id}/end` | End a call |
| POST | `/api/simulate` | Start a Simulate-mode call |
| POST | `/api/tools/{tool_name}` | Run a tool (`{"call_id", "arguments"}`) |
| GET | `/api/calls/{id}` | Answers, metrics, transcript |
| POST | `/api/calls/{id}/review` | Save Correct/Wrong marks |
| GET | `/api/calls/{id}/export?format=json\|csv[&section=turns]` | Download a report |
| WS | `/api/calls/{id}/events` | Live events for the UI |

SQLite tables: `forms`, `calls`, `answers`, `tool_calls`, `turn_metrics`, `reviews`. The database file is
`backend/data/tester.db`, which is git-ignored.

## 8b. Post-call report

When a call ends, or `complete_form` succeeds, a full report is generated automatically. A
**"Report ready"** button then appears in Column 1 and opens `/report/<call_id>` in a new tab.

The report has 10 sections:
1. Summary and score
2. Transcript with highlights
3. Mishearings
4. Voice quality, with ratings you fill in
5. Latency, with the STT / LLM / TTS split
6. Language
7. Accuracy
8. Cost
9. Issues
10. Optional AI summary

You can download it as **PDF, Markdown or JSON**.

The report comes from the shared module in [`report_module/`](report_module/README.md), which the other
testers can use too. Its settings are stored in `backend/data/report_settings.json`, and agent-audio
recordings in `backend/data/recordings/` (dummy calls only, git-ignored).

To try it without a call, open `/report/sample-openai-01`, `sample-gemini-01`, `sample-elevenlabs-01` or
`sample-sarvam-01`.

## 9. Tests

```bash
cd backend
.venv\Scripts\python -m pytest -q                        # tester (100 tests)
cd ..\report_module
..\backend\.venv\Scripts\python -m pytest -q             # report module (79 tests)
```

The tests cover:
- field validation;
- follow-up conditions;
- spoken numbers in Hindi, Tamil and Telugu (Latin spelling and native script);
- JSON tool-call parsing;
- `complete_form`'s missing-field check;
- reviews;
- export.

The tests make no Sarvam calls and need no API key.

## 10. Project layout

```
backend/app/
  main.py, config.py, db.py, models.py, schemas.py
  routers/   forms.py  session.py  tools.py  calls.py
  pipeline/  stt.py  llm.py  tts.py  runner.py  metrics.py  prompt.py
  services/  tools.py  validation.py  conditions.py  spoken_numbers.py  tool_schema.py
             report.py  export.py  events.py  forms_loader.py  simulate.py
  seed_forms/program_feedback_survey.json
  simulate/sample_call.json
backend/tests/
frontend/src/
  App.jsx  api.js  hooks/useCallEvents.js  hooks/useVoiceCall.js
  components/ CallPanel  FormPanel  MetricsPanel  TurnBar  SettingsDrawer  TestModeBanner  ui
```

## 11. Known limits

- **Spoken numbers.** The helper covers 0–100 in Hindi, Tamil, Telugu and English, plus native digits in
  all major Indian scripts. Other languages rely on the LLM sending digits, which the prompt asks for.
- **STT cost** is estimated from the call length, because the browser streams audio for the whole call.
- **Remote testers.** Testing from another network needs a TURN server, set with `ICE_SERVERS` in `.env`.
- **AI-assisted code.** This code was written with AI help (Claude Code). Under the EdZola policy it needs a
  human code review before merge or wider use.

## 12. Vercel Deployment (Unified Root Directory + MySQL)

The project is structured to deploy directly from the **root directory** to Vercel without deploying backend and frontend separately.

### Files configured for Root Deployment:
1. `vercel.json` – Configures static frontend build output (`frontend/dist`), serverless Python API function (`api/index.py`), and `/api/(.*)` rewrites.
2. `package.json` (root) – Defines `"build": "npm --prefix frontend install && npm --prefix frontend run build"`.
3. `requirements.txt` (root) – Python dependencies for Vercel's serverless runtime (including `pymysql` and `cryptography`).
4. `api/index.py` – Vercel serverless entry point routing `/api` requests to the FastAPI backend.

### Setting up MySQL:
1. Obtain your MySQL connection URL from any cloud MySQL provider (Aiven, PlanetScale, AWS RDS, DigitalOcean, Clever Cloud, etc.):
   ```text
   DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<dbname>?charset=utf8mb4
   ```
2. Configure Environment Variables in Vercel:
   - Go to your Project in **Vercel Dashboard > Settings > Environment Variables**.
   - Add `DATABASE_URL` (or `MYSQL_URL`) with your MySQL connection string.
   - Add `SARVAM_API_KEY` with your Sarvam API key.
   - Add `CORS_ORIGINS` (e.g. `https://your-project.vercel.app,http://localhost:5180`).
3. Deploy to Vercel:
   - Via GitHub: push your repo to GitHub and import the repository into Vercel. Keep **Root Directory** as `./` (default).
   - Via Vercel CLI:
     ```bash
     vercel
     ```

## Sarvam docs used
- [Realtime STT streaming](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming)
- [TTS WebSocket](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/web-socket)
- [Bulbul models](https://docs.sarvam.ai/api/getting-started/models/bulbul)
- [Chat completions](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1)
- [Pipecat integration](https://docs.sarvam.ai/api/integration/build-voice-agent-with-pipecat)
- [Pipecat production guide](https://docs.sarvam.ai/api/integration/pipecat-production-guide)
- [LiveKit production best practices](https://docs.sarvam.ai/api/integration/livekit-production-best-practices)
- [IVR & contact center](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/use-cases/ivr-contact-center)
- [Pricing](https://docs.sarvam.ai/api/getting-started/pricing)
