"""Report settings: score weights, thresholds, cost rates, exchange rate, options.

Stored as a JSON file (path chosen by each tester app). Missing keys fall back
to DEFAULTS, so old settings files keep working after new keys are added.

Rates were taken from the providers' public pricing pages on 2026-10-28.
They change often: check them and update "rates_last_updated".
- OpenAI:     https://developers.openai.com/api/docs/pricing  (gpt-realtime-2.1)
- Gemini:     https://ai.google.dev/gemini-api/docs/pricing   (Live native audio)
- ElevenLabs: Agents platform per-minute fee (LLM billed on top)
- Sarvam:     https://docs.sarvam.ai/api/getting-started/pricing (INR)
"""

import copy
import json
from pathlib import Path

DEFAULTS: dict = {
    # Overall score weights (percent). Re-normalised if a section has no data.
    "weights": {
        "accuracy": 35,
        "mishearings": 15,
        "latency": 20,
        "voice_quality": 15,
        "language": 10,
        "cost": 5,
    },
    "verdict": {"good_min": 75, "needs_improvement_min": 50},
    "latency": {"good_below_ms": 1000, "ok_below_ms": 1500, "zero_score_at_ms": 3000},
    "audio_issues": {"long_silence_ms": 2000},
    # Cost score: 100 at or below the target cost per minute, 0 at 3x the target.
    "cost_target_inr_per_min": 3.0,
    "usd_to_inr": 95.5,
    "rates_last_updated": "2026-10-28",
    "rates": {
        "openai": {
            "currency": "USD",
            "audio_input_per_1m_tokens": 32.0,
            "audio_cached_input_per_1m_tokens": 0.40,
            "audio_output_per_1m_tokens": 64.0,
            "text_input_per_1m_tokens": 4.0,
            "text_output_per_1m_tokens": 16.0,
        },
        "gemini": {
            "currency": "USD",
            "audio_input_per_1m_tokens": 3.0,
            "audio_output_per_1m_tokens": 12.0,
            "text_input_per_1m_tokens": 0.75,
            "text_output_per_1m_tokens": 4.50,
        },
        "elevenlabs": {
            "currency": "USD",
            "voice_per_minute": 0.08,
            # LLM is billed on top and depends on the model chosen in ElevenLabs.
            "llm_per_minute_estimate": 0.01,
        },
        "sarvam": {
            "currency": "INR",
            "stt_per_minute": 0.49,
            "tts_bulbul_v3_per_10k_chars": 30.0,
            "tts_bulbul_v4_flash_per_10k_chars": 10.0,
            "llm_input_per_1m_tokens": 15.0,
            "llm_output_per_1m_tokens": 60.0,
        },
    },
    # Optional features (off by default)
    "mos_enabled": False,  # DNSMOS speech-quality score (needs: pip install report-module[mos])
    "ai_summary_enabled": False,  # needs ANTHROPIC_API_KEY in the tester's .env
    "ai_summary_model": "claude-opus-5-5",
}


def _merge(base: dict, override: dict) -> dict:
    """Deep-merge override into a copy of base."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(path: str | Path | None) -> dict:
    if path is None or not Path(path).exists():
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, json.loads(Path(path).read_text(encoding="utf-8")))


def save_settings(path: str | Path, settings: dict) -> dict:
    merged = _merge(DEFAULTS, settings)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
