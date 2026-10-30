import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
# On Vercel only /tmp is writable (and it is wiped between cold starts).
_DEFAULT_DB_DIR = Path("/tmp") if os.getenv("VERCEL") else BACKEND_DIR / "data"
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL") or f"sqlite:///{(_DEFAULT_DB_DIR / 'tester.db').as_posix()}"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5180,http://127.0.0.1:5180,http://localhost:8000,http://127.0.0.1:8000").split(",")]

# Parse ICE / STUN / TURN servers: accepts a JSON array (JS-style unquoted keys and single quotes
# are tolerated, as copied from provider dashboards) or comma-separated URLs.
def _load_ice_json(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        pass
    fixed = raw.replace("'", '"')
    fixed = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', lambda m: f'{m.group(1)}"{m.group(2)}":', fixed)  # quote bare keys
    fixed = re.sub(r',\s*([}\]])', lambda m: m.group(1), fixed)  # trailing commas
    return json.loads(fixed)


def _parse_ice_servers():
    default = [{"urls": "stun:stun.l.google.com:19302"}]
    raw = os.getenv("ICE_SERVERS", "").strip()
    if not raw:
        return default
    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = _load_ice_json(raw)
        except ValueError:
            print("WARNING: ICE_SERVERS is not valid JSON; using the default STUN server.")
            return default
        return [data] if isinstance(data, dict) else data
    return [{"urls": s.strip()} for s in raw.split(",") if s.strip()]

ICE_SERVERS = _parse_ice_servers()

# Optional: fetch fresh TURN credentials from a provider at call time. Tried in this order, then
# falls back to ICE_SERVERS if none is set or the request fails:
#   Cloudflare: CLOUDFLARE_TURN_KEY_ID + CLOUDFLARE_TURN_API_TOKEN
#   Metered:    METERED_DOMAIN ("<app>.metered.live") + METERED_API_KEY
CLOUDFLARE_TURN_KEY_ID = os.getenv("CLOUDFLARE_TURN_KEY_ID", "").strip()
CLOUDFLARE_TURN_API_TOKEN = os.getenv("CLOUDFLARE_TURN_API_TOKEN", "").strip()
METERED_DOMAIN = os.getenv("METERED_DOMAIN", "").strip().removeprefix("https://").strip("/")
METERED_API_KEY = os.getenv("METERED_API_KEY", "").strip()
_ICE_CACHE_SECONDS = 3600
_ice_cache: dict = {"at": 0.0, "servers": None}
_ice_lock = threading.Lock()


def _fetch_cloudflare() -> list:
    url = f"https://rtc.live.cloudflare.com/v1/turn/keys/{CLOUDFLARE_TURN_KEY_ID}/credentials/generate-ice-servers"
    req = urllib.request.Request(
        url,
        data=json.dumps({"ttl": 86400}).encode(),
        headers={"Authorization": f"Bearer {CLOUDFLARE_TURN_API_TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        data = json.loads(res.read())["iceServers"]
    servers = [data] if isinstance(data, dict) else data
    for server in servers:  # browsers block port 53, so drop those URLs
        urls = server["urls"] if isinstance(server["urls"], list) else [server["urls"]]
        server["urls"] = [u for u in urls if ":53" not in u]
    return servers


def _fetch_metered() -> list:
    url = f"https://{METERED_DOMAIN}/api/v1/turn/credentials?" + urllib.parse.urlencode({"apiKey": METERED_API_KEY})
    with urllib.request.urlopen(url, timeout=5) as res:
        return json.loads(res.read())


def get_ice_servers() -> list:
    """ICE servers for new calls. Blocking (HTTP): call it from a worker thread."""
    if CLOUDFLARE_TURN_KEY_ID and CLOUDFLARE_TURN_API_TOKEN:
        fetch = _fetch_cloudflare
    elif METERED_DOMAIN and METERED_API_KEY:
        fetch = _fetch_metered
    else:
        return ICE_SERVERS
    with _ice_lock:
        if _ice_cache["servers"] and time.time() - _ice_cache["at"] < _ICE_CACHE_SECONDS:
            return _ice_cache["servers"]
        try:
            servers = fetch()
            if not isinstance(servers, list) or not servers:
                raise ValueError("unexpected response")
        except Exception as e:  # never log the URL or headers: they contain the secret
            print(f"WARNING: could not fetch TURN credentials ({type(e).__name__}); using ICE_SERVERS.")
            return _ice_cache["servers"] or ICE_SERVERS
        _ice_cache.update(at=time.time(), servers=servers)
        return servers


SEED_FORMS_DIR = BACKEND_DIR / "app" / "seed_forms"
SIMULATE_DIR = BACKEND_DIR / "app" / "simulate"


def has_api_key() -> bool:
    return bool(SARVAM_API_KEY) and not SARVAM_API_KEY.startswith("your_")


# ---------------------------------------------------------------------------
# Dropdown options (sent to the UI by GET /api/options)
# ---------------------------------------------------------------------------

STT_MODELS = [
    {"id": "saaras:v3-realtime", "label": "Saaras v3 realtime (default)"},
    {"id": "saaras:v4", "label": "Saaras v4"},
]

# sarvam-30b is deprecated and the chat API no longer accepts it, so it is not offered.
LLM_MODELS = [
    {"id": "sarvam-105b-conversations", "label": "Sarvam-105B Conversations (voice, default)", "supports_reasoning": False},
    {"id": "sarvam-105b", "label": "Sarvam-105B", "supports_reasoning": True},
]

TTS_MODELS = [
    {"id": "bulbul:v3", "label": "Bulbul v3 (default)"},
    {"id": "bulbul:v4-flash", "label": "Bulbul v4 Flash (cheaper, no Malayalam/Odia)"},
]

# Bulbul v3 speakers (lowercase, case-sensitive), from the Bulbul model page.
TTS_VOICES_V3 = [
    "shubh", "aditya", "ritu", "priya", "neha", "rahul", "pooja", "rohan", "simran",
    "kavya", "amit", "dev", "ishita", "shreya", "ratan", "manan", "sumit", "roopa",
    "kabir", "aayan", "ashutosh", "advait", "anand", "tanya", "tarun", "sunny", "mani",
    "gokul", "vijay", "shruti", "suhani", "mohit", "kavitha", "rehan", "soham", "rupali",
]

# A short list of Bulbul v4 Flash "customer / conversational" persona voices.
TTS_VOICES_V4 = [
    "simran_en_customer", "dev_en_conversational", "ritu_hi_customer", "shubh_hi_customer",
    "shalini_enhi_customer", "sunny_enhi_customer", "roopa_bn_conversational",
    "pooja_gu_customer", "chaitra_kn_conversation", "ishita_mr_conversational",
    "nilesh_mr_conversation", "anand_pa_customer", "aravind_ta_ads", "kavitha_te_conversation",
]

# "auto" = let Saaras detect the language of every utterance (handles Hinglish).
LANGUAGES = [
    {"code": "auto", "label": "Auto-detect"},
    {"code": "en-IN", "label": "English (India)"},
    {"code": "hi-IN", "label": "Hindi"},
    {"code": "bn-IN", "label": "Bengali"},
    {"code": "ta-IN", "label": "Tamil"},
    {"code": "te-IN", "label": "Telugu"},
    {"code": "kn-IN", "label": "Kannada"},
    {"code": "ml-IN", "label": "Malayalam"},
    {"code": "mr-IN", "label": "Marathi"},
    {"code": "gu-IN", "label": "Gujarati"},
    {"code": "pa-IN", "label": "Punjabi"},
    {"code": "od-IN", "label": "Odia"},
]
LANGUAGE_NAMES = {lang["code"]: lang["label"] for lang in LANGUAGES}

# Bulbul v4 Flash does not offer these yet, so the call falls back to bulbul:v3.
V4_UNSUPPORTED_LANGUAGES = {"ml-IN", "od-IN"}

# ---------------------------------------------------------------------------
# Default call settings (every value can be changed from the UI)
# ---------------------------------------------------------------------------

DEFAULT_CALL_SETTINGS = {
    "stt_model": "saaras:v3-realtime",
    "llm_model": "sarvam-105b-conversations",
    "tts_model": "bulbul:v3",
    "tts_voice": "shubh",
    "language": "auto",
    "audio_quality": "normal",  # "normal" (16 kHz) or "phone" (8 kHz)
    # --- latency tuning ---
    "stt_stream_type": "fast",  # 500 ms chunks; "balanced" uses 1000 ms
    "turn_stop_timeout_ms": 70,  # pause after Sarvam's speech_end before the LLM runs
    "vad_silence_ms": 500,  # Sarvam server VAD silence window (its default)
    "reasoning": "off",  # only used by sarvam-105b: "off" or "low"
    "llm_max_tokens": 400,
    "tts_pace": 1.0,
    "tts_min_buffer_size": 30,  # chars before TTS starts; lower = faster first audio
    "record_agent_audio": True,  # agent voice only (dummy calls), for the report MOS score
    # --- cost rates (INR, pay-as-you-go, from the pricing page) ---
    "rate_stt_per_min": 0.49,
    "rate_tts_v3_per_10k_chars": 30.0,
    "rate_tts_v4_per_10k_chars": 10.0,
    "rate_llm_input_per_1m": 15.0,
    "rate_llm_output_per_1m": 60.0,
}
