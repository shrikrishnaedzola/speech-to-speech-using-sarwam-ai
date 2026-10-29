"""Generate the 4 sample calls (one per provider) used for demos and tests.

ALL DATA IS MADE UP. Run:  python -m report_module.sample_data.make_samples

Each call is written as a short script of steps:
    ("agent",  text)                         agent speaks
    ("caller", text, language)               caller speaks (STT result)
    ("save",   field_id, value, normalized)  successful save_answer
    ("reject", field_id, value, error)       save_answer rejected by validation
    ("badjson", raw_arguments)               tool call with invalid JSON
    ("skip",   field_id)                     skip_field
    ("complete", ok, missing)                complete_form
Timings, offsets, answers and usage are derived from the steps.
Each sample shows different strengths and problems on purpose.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent

FORM_FIELDS = [
    {"id": "caller_name", "label": "Caller name", "type": "text", "required": True},
    {"id": "age", "label": "Age", "type": "number", "required": True},
    {"id": "district", "label": "District", "type": "text", "required": True},
    {"id": "preferred_language", "label": "Preferred language", "type": "choice", "required": False},
    {"id": "attended_sessions", "label": "Attended sessions", "type": "yes_no", "required": True},
    {"id": "reason_not_attended", "label": "Reason for not attending", "type": "text", "required": True,
     "show_if": {"field": "attended_sessions", "op": "eq", "value": "no"}},
    {"id": "sessions_attended_count", "label": "Sessions attended", "type": "number", "required": True,
     "show_if": {"field": "attended_sessions", "op": "eq", "value": "yes"}},
    {"id": "number_of_children", "label": "Number of children", "type": "number", "required": True},
    {"id": "children_ages", "label": "Children's ages", "type": "number_list", "required": True,
     "show_if": {"field": "number_of_children", "op": "gt", "value": 0}},
    {"id": "satisfaction_rating", "label": "Satisfaction rating (1-5)", "type": "number", "required": True},
    {"id": "improvement_suggestion", "label": "Improvement suggestion", "type": "text", "required": False},
    {"id": "consent_to_followup", "label": "Consent to follow-up", "type": "yes_no", "required": True},
]


def build(call: dict, steps: list, totals_ms: list[float], split: bool, interrupted_agent: set[int] = frozenset(),
          reviews: list | None = None, expected: dict | None = None, usage: dict | None = None) -> dict:
    t = 1.0
    transcript, tools, turns = [], [], []
    answers: dict[str, dict] = {}
    completed = False
    caller_i = 0
    agent_i = 0
    last_caller_end = None
    for step in steps:
        kind = step[0]
        if kind == "agent":
            if last_caller_end is not None:
                t = last_caller_end + totals_ms[caller_i] / 1000
            transcript.append({"role": "agent", "text": step[1], "offset_s": round(t, 2),
                               "interrupted": agent_i in interrupted_agent})
            agent_i += 1
            t += len(step[1]) * 0.06
            last_caller_end = None
        elif kind == "caller":
            caller_i += 1
            t += 1.0
            t += len(step[1]) * 0.07
            transcript.append({"role": "caller", "text": step[1], "offset_s": round(t, 2), "language": step[2]})
            last_caller_end = t
        else:
            offset = round((last_caller_end or t) + 0.3 + 0.05 * len(tools), 2)
            if kind == "save":
                _, fid, value, normalized = step
                tools.append({"name": "save_answer", "arguments": {"field_id": fid, "value": value, "confidence": "high"},
                              "success": True, "result": {"ok": True, "saved": {fid: normalized}}, "duration_ms": 9, "offset_s": offset})
                a = answers.setdefault(fid, {"field_id": fid, "attempts": 0})
                a.update(value=normalized, status="filled", confidence="high")
                a["attempts"] += 1
            elif kind == "reject":
                _, fid, value, error = step
                tools.append({"name": "save_answer", "arguments": {"field_id": fid, "value": value, "confidence": "high"},
                              "success": False, "result": {"ok": False, "error": error}, "duration_ms": 8, "offset_s": offset})
                a = answers.setdefault(fid, {"field_id": fid, "attempts": 0, "status": "pending"})
                a["attempts"] += 1
            elif kind == "badjson":
                tools.append({"name": "save_answer", "arguments": step[1], "success": False, "parse_error": True,
                              "result": {"ok": False, "error": "Invalid arguments: not valid JSON."}, "duration_ms": 2, "offset_s": offset})
            elif kind == "skip":
                tools.append({"name": "skip_field", "arguments": {"field_id": step[1], "reason": "Caller had none"},
                              "success": True, "result": {"ok": True}, "duration_ms": 6, "offset_s": offset})
                answers[step[1]] = {"field_id": step[1], "status": "skipped", "attempts": 0}
            elif kind == "complete":
                ok, missing = step[1], step[2]
                result = {"ok": True} if ok else {"ok": False, "missing_fields": [{"field_id": m} for m in missing]}
                tools.append({"name": "complete_form", "arguments": {}, "success": ok, "result": result,
                              "duration_ms": 7, "offset_s": offset})
                completed = completed or ok

    # One TurnTiming per caller turn (+ the greeting as turn 0).
    callers = [u for u in transcript if u["role"] == "caller"]
    agents = [u for u in transcript if u["role"] == "agent"]
    turns.append({"turn_index": 0, "total_ms": totals_ms[0], "agent_text": agents[0]["text"]})
    for i, c in enumerate(callers, start=1):
        total = totals_ms[i] if i < len(totals_ms) else None
        reply = next((a for a in agents if a["offset_s"] > c["offset_s"]), None)
        turn = {"turn_index": i, "total_ms": total, "user_text": c["text"],
                "agent_text": reply["text"] if reply else None,
                "interrupted": bool(reply and reply["interrupted"])}
        if split and total:
            turn.update(stt_ms=round(total * 0.15), turn_wait_ms=70, llm_ttft_ms=round(total * 0.55),
                        tts_ttfb_ms=round(total * 0.22))
        turns.append(turn)

    duration = round(transcript[-1]["offset_s"] + 4, 1)
    started = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
    call.update(started_at=started.isoformat(), ended_at=(started + timedelta(seconds=duration)).isoformat(),
                duration_s=duration, form_id="program_feedback_survey_test", form_name="Program Feedback Survey (Test)")
    agent_chars = sum(len(a["text"]) for a in agents)
    u = {"call_minutes": round(duration / 60, 3), **(usage or {})}
    if call["provider"] == "sarvam":
        u.setdefault("stt_minutes", round(duration / 60, 3))
        u.setdefault("tts_characters", agent_chars)
    return {
        "schema_version": "1.0",
        "call": call,
        "form_fields": FORM_FIELDS,
        "transcript": transcript,
        "answers": list(answers.values()),
        "reviews": reviews or [],
        "turns": turns,
        "tool_calls": tools,
        "usage": u,
        "interruptions": len(interrupted_agent),
        "form_completed": completed,
        "recording_path": None,
        "expected_script": expected,
        "errors": [],
    }


def correct(*fields):
    return [{"field_id": f, "verdict": "correct"} for f in fields]


# --------------------------------------------------------------------------- Sarvam: Hinglish, STT mishears a number
SARVAM = build(
    {"call_id": "sample-sarvam-01", "provider": "sarvam", "model": "sarvam-105b-conversations",
     "models": {"stt": "saaras:v3-realtime", "llm": "sarvam-105b-conversations", "tts": "bulbul:v3"},
     "voice": "shubh", "language_selected": "auto", "audio_mode": "normal", "mode": "simulate"},
    [
        ("agent", "Namaste! Main ek NGO program ki taraf se bol rahi hoon. Yeh call lagbhag teen minute ki hogi. Kya abhi baat kar sakte hain?"),
        ("caller", "Haan ji, boliye.", "hi-IN"),
        ("agent", "Dhanyavaad. Aapka naam kya hai?"),
        ("caller", "Mera naam Test User hai.", "hi-IN"),
        ("save", "caller_name", "Test User", "Test User"),
        ("agent", "Shukriya. Aapki umar kya hai?"),
        ("caller", "Pachaas saal.", "hi-IN"),
        ("save", "age", "50", 50),
        ("agent", "Theek hai. Aap kis district mein rehte hain?"),
        ("caller", "Nahi, maine pachees kaha tha. Pachees saal.", "hi-IN"),
        ("save", "age", "25", 25),
        ("agent", "Maaf kijiye, umar pachees saal. Aap kis district mein rehte hain?"),
        ("caller", "Sample district.", "en-IN"),
        ("save", "district", "Sample district", "Sample district"),
        ("agent", "Program sessions ke liye aap kaunsi bhasha pasand karte hain?"),
        ("caller", "Hindi.", "hi-IN"),
        ("save", "preferred_language", "Hindi", "Hindi"),
        ("agent", "Kya aapne program ka koi session attend kiya?"),
        ("caller", "Haan, kiya tha.", "hi-IN"),
        ("save", "attended_sessions", "yes", "yes"),
        ("agent", "Aapne kitne sessions attend kiye?"),
        ("caller", "Teen sessions.", "hi-IN"),
        ("save", "sessions_attended_count", "3", 3),
        ("agent", "Aapke kitne bachche hain?"),
        ("caller", "Do bachche.", "hi-IN"),
        ("save", "number_of_children", "2", 2),
        ("agent", "Unki umar kya hai?"),
        ("caller", "Chhe aur nau saal.", "hi-IN"),
        ("save", "children_ages", "6, 9", [6, 9]),
        ("agent", "Ek se paanch ke scale par aap program se kitne santusht hain?"),
        ("caller", "Char.", "hi-IN"),
        ("save", "satisfaction_rating", "4", 4),
        ("agent", "Program ko behtar banane ke liye koi sujhav?"),
        ("caller", "Sessions shaam ko ho toh achha rahega.", "hi-IN"),
        ("save", "improvement_suggestion", "Sessions in the evening", "Sessions in the evening"),
        ("agent", "Kya hum baad mein aapse ek chhote follow-up ke liye sampark kar sakte hain?"),
        ("caller", "Haan, zaroor.", "hi-IN"),
        ("save", "consent_to_followup", "yes", "yes"),
        ("agent", "Main confirm kar leti hoon: naam Test User, umar pachees, teen sessions, do bachche, rating char. Kya yeh sahi hai?"),
        ("caller", "Haan, sab sahi hai.", "hi-IN"),
        ("complete", True, []),
        ("agent", "Aapke samay ke liye bahut dhanyavaad. Aapka din shubh ho!"),
    ],
    totals_ms=[650, 900, 1050, 980, 1750, 1100, 940, 1010, 990, 950, 1020, 1060, 990, 1030, 1000, 1480],
    split=True,
    reviews=correct("caller_name", "age", "district", "preferred_language", "attended_sessions",
                    "sessions_attended_count", "number_of_children", "children_ages", "satisfaction_rating",
                    "consent_to_followup"),
    expected={"scenario_id": "hinglish-basic-01",
              "caller_turns": ["Haan ji, boliye.", "Mera naam Test User hai.", "Pachees saal.",
                               "Nahi, maine pachees kaha tha. Pachees saal.", "Sample district.", "Hindi.",
                               "Haan, kiya tha.", "Teen sessions.", "Do bachche.", "Chhe aur nau saal.", "Char.",
                               "Sessions shaam ko ho toh achha rahega.", "Haan, zaroor.", "Haan, sab sahi hai."],
              "expected_answers": {"caller_name": "Test User", "age": 25, "district": "Sample district",
                                   "attended_sessions": "yes", "sessions_attended_count": 3, "number_of_children": 2,
                                   "children_ages": [6, 9], "satisfaction_rating": 4, "consent_to_followup": "yes"}},
    usage={"llm_input_tokens": 41000, "llm_output_tokens": 1600, "tts_model": "bulbul:v3"},
)

# --------------------------------------------------------------------------- OpenAI: English, fast, LLM mishears 45 -> 54
OPENAI = build(
    {"call_id": "sample-openai-01", "provider": "openai", "model": "gpt-realtime-2.1", "voice": "marin",
     "language_selected": "en-IN", "audio_mode": "normal", "mode": "simulate"},
    [
        ("agent", "Hello! I am calling on behalf of an NGO program. This call takes about three minutes. Is this a good time to talk?"),
        ("caller", "Yes, go ahead.", "en-IN"),
        ("agent", "Thank you. May I know your name?"),
        ("caller", "My name is Test Caller.", "en-IN"),
        ("save", "caller_name", "Test Caller", "Test Caller"),
        ("agent", "Thanks. What is your age?"),
        ("caller", "Forty five.", "en-IN"),
        ("save", "age", "54", 54),
        ("agent", "Got it, fifty four. Which district do you live in?"),
        ("caller", "No, I said forty five. And the district is Sample Nagar.", "en-IN"),
        ("save", "age", "45", 45),
        ("badjson", "{\"field_id\": \"district\", \"value\": \"Sample Nagar\" \"confidence\": \"high\"}"),
        ("save", "district", "Sample Nagar", "Sample Nagar"),
        ("agent", "Sorry about that, forty five. Which language do you prefer for the sessions?"),
        ("caller", "English.", "en-IN"),
        ("save", "preferred_language", "English", "English"),
        ("agent", "Did you attend any of the program sessions?"),
        ("caller", "No, I could not.", "en-IN"),
        ("save", "attended_sessions", "no", "no"),
        ("agent", "Could you tell me why you could not attend?"),
        ("caller", "I was travelling for work.", "en-IN"),
        ("save", "reason_not_attended", "Travelling for work", "Travelling for work"),
        ("agent", "How many children do you have?"),
        ("caller", "None.", "en-IN"),
        ("save", "number_of_children", "0", 0),
        ("agent", "On a scale of one to five, how satisfied are you with the program?"),
        ("caller", "Five.", "en-IN"),
        ("save", "satisfaction_rating", "5", 5),
        ("agent", "Do you have any suggestion to improve the program?"),
        ("caller", "No suggestions.", "en-IN"),
        ("skip", "improvement_suggestion"),
        ("agent", "May we contact you again for a short follow-up later?"),
        ("caller", "Yes.", "en-IN"),
        ("save", "consent_to_followup", "yes", "yes"),
        ("agent", "To confirm: Test Caller, forty five, Sample Nagar, did not attend, no children, rating five. Is that right?"),
        ("caller", "Yes, that's right.", "en-IN"),
        ("complete", True, []),
        ("agent", "Thank you so much for your time. Have a great day!"),
    ],
    totals_ms=[520, 760, 800, 840, 1320, 780, 820, 790, 860, 800, 830, 770, 810, 900],
    split=False,
    reviews=correct("caller_name", "age", "district", "preferred_language", "attended_sessions",
                    "reason_not_attended", "number_of_children", "satisfaction_rating", "consent_to_followup"),
    expected={"scenario_id": "english-basic-01",
              "caller_turns": ["Yes, go ahead.", "My name is Test Caller.", "Forty five.",
                               "No, I said forty five. And the district is Sample Nagar.", "English.",
                               "No, I could not.", "I was travelling for work.", "None.", "Five.", "No suggestions.",
                               "Yes.", "Yes, that's right."],
              "expected_answers": {"caller_name": "Test Caller", "age": 45, "district": "Sample Nagar",
                                   "attended_sessions": "no", "reason_not_attended": "Travelling for work",
                                   "number_of_children": 0, "satisfaction_rating": 5, "consent_to_followup": "yes"}},
    usage={"audio_input_tokens": 1100, "llm_cached_input_tokens": 400, "audio_output_tokens": 1750,
           "llm_input_tokens": 2600, "llm_output_tokens": 420},
)

# --------------------------------------------------------------------------- Gemini: Tamil, phone 8 kHz, number errors, English replies
GEMINI = build(
    {"call_id": "sample-gemini-01", "provider": "gemini", "model": "gemini-live-native-audio", "voice": "Kore",
     "language_selected": "ta-IN", "audio_mode": "phone_8khz", "mode": "simulate"},
    [
        ("agent", "வணக்கம்! ஒரு NGO திட்டத்தின் சார்பாக அழைக்கிறேன். இது சுமார் மூன்று நிமிடங்கள் ஆகும். இப்போது பேசலாமா?"),
        ("caller", "சரி, சொல்லுங்க.", "ta-IN"),
        ("agent", "நன்றி. உங்கள் பெயர் என்ன?"),
        ("caller", "என் பெயர் டெஸ்ட் யூசர்.", "ta-IN"),
        ("save", "caller_name", "Test User", "Test User"),
        ("agent", "உங்கள் வயது என்ன?"),
        ("caller", "முப்பத்தி ரெண்டு.", "ta-IN"),
        ("save", "age", "22", 22),
        ("agent", "Thank you. Which district do you live in?"),
        ("caller", "Sample district.", "en-IN"),
        ("save", "district", "Sample district", "Sample district"),
        ("agent", "எந்த மொழியை விரும்புகிறீர்கள்?"),
        ("caller", "தமிழ்.", "ta-IN"),
        ("save", "preferred_language", "Tamil", "Tamil"),
        ("agent", "நீங்கள் ஏதாவது அமர்வுகளில் கலந்து கொண்டீர்களா?"),
        ("caller", "ஆமா.", "ta-IN"),
        ("save", "attended_sessions", "yes", "yes"),
        ("agent", "Thank you. How many sessions did you attend?"),
        ("caller", "அஞ்சு.", "ta-IN"),
        ("save", "sessions_attended_count", "5", 5),
        ("agent", "உங்களுக்கு எத்தனை குழந்தைகள்?"),
        ("caller", "ரெண்டு.", "ta-IN"),
        ("save", "number_of_children", "2", 2),
        ("agent", "அவர்களின் வயது என்ன?"),
        ("caller", "மூணு, ஏழு.", "ta-IN"),
        ("save", "children_ages", "3, 7", [3, 7]),
        ("agent", "ஒன்று முதல் ஐந்து வரை, திட்டத்தில் எவ்வளவு திருப்தி?"),
        ("caller", "நாலு.", "ta-IN"),
        ("save", "satisfaction_rating", "4", 4),
        ("agent", "ஏதாவது பரிந்துரை உள்ளதா?"),
        ("caller", "இல்லை.", "ta-IN"),
        ("skip", "improvement_suggestion"),
        ("agent", "பின்னர் உங்களைத் தொடர்பு கொள்ளலாமா?"),
        ("caller", "ஆமா.", "ta-IN"),
        ("save", "consent_to_followup", "yes", "yes"),
        ("complete", True, []),
        ("agent", "மிக்க நன்றி. நல்ல நாள்!"),
    ],
    totals_ms=[700, 1100, 1250, 1380, 1210, 1150, 1290, 1340, 1180, 1420, 1260, 1190, 1300],
    split=False,
    reviews=[{"field_id": "age", "verdict": "wrong", "expected_value": "32"},
             {"field_id": "children_ages", "verdict": "wrong", "expected_value": "3, 8"},
             *correct("caller_name", "district", "preferred_language", "attended_sessions", "sessions_attended_count",
                      "number_of_children", "satisfaction_rating", "consent_to_followup")],
    expected={"scenario_id": "tamil-basic-01",
              "caller_turns": ["சரி, சொல்லுங்க.", "என் பெயர் டெஸ்ட் யூசர்.", "முப்பத்தி ரெண்டு.", "Sample district.",
                               "தமிழ்.", "ஆமா.", "அஞ்சு.", "ரெண்டு.", "மூணு, எட்டு.", "நாலு.", "இல்லை.", "ஆமா."],
              "expected_answers": {"caller_name": "Test User", "age": 32, "children_ages": [3, 8]}},
    usage={"audio_input_tokens": 1500, "audio_output_tokens": 1650, "llm_input_tokens": 2400, "llm_output_tokens": 380},
)

# --------------------------------------------------------------------------- ElevenLabs: Hindi, slow, follow-up error, not completed
ELEVENLABS = build(
    {"call_id": "sample-elevenlabs-01", "provider": "elevenlabs", "model": "eleven_flash_v2_5 + LLM", "voice": "Test voice A",
     "language_selected": "hi-IN", "audio_mode": "normal", "mode": "simulate"},
    [
        ("agent", "नमस्ते! मैं एक NGO कार्यक्रम की ओर से बोल रही हूँ। यह कॉल लगभग तीन मिनट की होगी। क्या अभी बात कर सकते हैं?"),
        ("caller", "हाँ, बोलिए।", "hi-IN"),
        ("agent", "आपका नाम क्या है?"),
        ("caller", "मेरा नाम टेस्ट यूज़र है।", "hi-IN"),
        ("save", "caller_name", "Test User", "Test User"),
        ("agent", "आपकी उम्र क्या है? कृपया अपनी उम्र बताइए और"),
        ("caller", "चालीस।", "hi-IN"),
        ("save", "age", "40", 40),
        ("agent", "आप किस ज़िले में रहते हैं?"),
        ("caller", "सैंपल ज़िला।", "hi-IN"),
        ("save", "district", "Sample district", "Sample district"),
        ("agent", "क्या आपने कोई सत्र अटेंड किया?"),
        ("caller", "हाँ, किया।", "hi-IN"),
        ("save", "attended_sessions", "yes", "yes"),
        ("agent", "आप सत्र में क्यों नहीं आ पाए?"),
        ("caller", "मैं आया था, दो सत्र।", "hi-IN"),
        ("save", "reason_not_attended", "Attended two sessions", "Attended two sessions"),
        ("agent", "क्या आप कृपया दोबारा बता सकते हैं कितने सत्र?"),
        ("caller", "दो।", "hi-IN"),
        ("reject", "sessions_attended_count", "do", "Could not understand a single number. Ask again."),
        ("agent", "क्या आप कृपया दोबारा बता सकते हैं कितने सत्र?"),
        ("caller", "दो सत्र।", "hi-IN"),
        ("save", "sessions_attended_count", "2", 2),
        ("agent", "आपके कितने बच्चे हैं?"),
        ("caller", "कोई नहीं।", "hi-IN"),
        ("save", "number_of_children", "0", 0),
        ("agent", "एक से पाँच तक, आप कितने संतुष्ट हैं?"),
        ("caller", "तीन।", "hi-IN"),
        ("save", "satisfaction_rating", "3", 3),
        ("complete", False, ["consent_to_followup"]),
        ("agent", "क्या हम बाद में आपसे संपर्क कर सकते हैं?"),
        ("caller", "अभी मुझे जाना है, धन्यवाद।", "hi-IN"),
        ("agent", "ठीक है, धन्यवाद। नमस्ते।"),
    ],
    totals_ms=[900, 1650, 2300, 1720, 1890, 2650, 1580, 1940, 1760, 2100, 1830, 1700, 1600],
    split=False,
    interrupted_agent={2},
    reviews=[*correct("caller_name", "district", "attended_sessions"),
             {"field_id": "age", "verdict": "wrong", "expected_value": "45"}],
    expected=None,
    usage={},
)


def main():
    # File name = call id, so json_file_adapter(sample_data) can load them directly.
    for data in (SARVAM, OPENAI, GEMINI, ELEVENLABS):
        name = f"{data['call']['call_id']}.json"
        (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
