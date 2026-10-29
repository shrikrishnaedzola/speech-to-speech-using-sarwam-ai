"""Cost of one call, per provider, in USD and INR.

Each provider bills differently, so each has its own small function that turns
Usage into line items. Rates come from settings (editable, with a
"rates_last_updated" date shown on the report).
"""

from report_module.schema import CallData, CostItem, CostSection


def _item(label: str, quantity: float, unit: str, rate: float, per: float, currency: str, usd_to_inr: float) -> CostItem:
    """One line: quantity / per * rate, converted to both currencies."""
    amount = quantity / per * rate
    usd = amount if currency == "USD" else amount / usd_to_inr
    return CostItem(label=label, quantity=round(quantity, 4), unit=unit, rate=rate, rate_currency=currency,
                    cost_usd=round(usd, 6), cost_inr=round(usd * usd_to_inr, 4))


def _openai(data: CallData, r: dict, fx: float) -> list[CostItem]:
    u, cur = data.usage, r["currency"]
    uncached = max(0, u.audio_input_tokens - u.llm_cached_input_tokens)
    return [
        _item("Audio in (uncached)", uncached, "tokens", r["audio_input_per_1m_tokens"], 1e6, cur, fx),
        _item("Audio in (cached)", u.llm_cached_input_tokens, "tokens", r["audio_cached_input_per_1m_tokens"], 1e6, cur, fx),
        _item("Audio out", u.audio_output_tokens, "tokens", r["audio_output_per_1m_tokens"], 1e6, cur, fx),
        _item("Text in", u.llm_input_tokens, "tokens", r["text_input_per_1m_tokens"], 1e6, cur, fx),
        _item("Text out", u.llm_output_tokens, "tokens", r["text_output_per_1m_tokens"], 1e6, cur, fx),
    ]


def _gemini(data: CallData, r: dict, fx: float) -> list[CostItem]:
    u, cur = data.usage, r["currency"]
    return [
        _item("Audio in", u.audio_input_tokens, "tokens", r["audio_input_per_1m_tokens"], 1e6, cur, fx),
        _item("Audio out", u.audio_output_tokens, "tokens", r["audio_output_per_1m_tokens"], 1e6, cur, fx),
        _item("Text in", u.llm_input_tokens, "tokens", r["text_input_per_1m_tokens"], 1e6, cur, fx),
        _item("Text out", u.llm_output_tokens, "tokens", r["text_output_per_1m_tokens"], 1e6, cur, fx),
    ]


def _elevenlabs(data: CallData, r: dict, fx: float) -> list[CostItem]:
    minutes, cur = data.usage.call_minutes, r["currency"]
    return [
        _item("Voice agent per-minute fee", minutes, "min", r["voice_per_minute"], 1, cur, fx),
        _item("LLM (estimate per minute)", minutes, "min", r["llm_per_minute_estimate"], 1, cur, fx),
    ]


def _sarvam(data: CallData, r: dict, fx: float) -> list[CostItem]:
    u, cur = data.usage, r["currency"]
    v4 = (u.tts_model or "").startswith("bulbul:v4")
    tts_rate = r["tts_bulbul_v4_flash_per_10k_chars"] if v4 else r["tts_bulbul_v3_per_10k_chars"]
    return [
        _item("Speech-to-text (Saaras)", u.stt_minutes or u.call_minutes, "min", r["stt_per_minute"], 1, cur, fx),
        _item("LLM input tokens", u.llm_input_tokens, "tokens", r["llm_input_per_1m_tokens"], 1e6, cur, fx),
        _item("LLM output tokens", u.llm_output_tokens, "tokens", r["llm_output_per_1m_tokens"], 1e6, cur, fx),
        _item(f"Text-to-speech ({'Bulbul v4 Flash' if v4 else 'Bulbul v3'})", u.tts_characters, "chars", tts_rate, 1e4, cur, fx),
    ]


PROVIDERS = {"openai": _openai, "gemini": _gemini, "elevenlabs": _elevenlabs, "sarvam": _sarvam}


def analyse_cost(data: CallData, settings: dict) -> CostSection:
    fx = float(settings["usd_to_inr"])
    items = PROVIDERS[data.call.provider](data, settings["rates"][data.call.provider], fx)
    total_usd = sum(i.cost_usd for i in items)
    minutes = data.call.duration_s / 60 if data.call.duration_s else data.usage.call_minutes
    has_usage = total_usd > 0
    return CostSection(
        items=items,
        total_usd=round(total_usd, 4),
        total_inr=round(total_usd * fx, 2),
        per_minute_usd=round(total_usd / minutes, 4) if minutes else None,
        per_minute_inr=round(total_usd * fx / minutes, 2) if minutes else None,
        per_completed_form_usd=round(total_usd, 4) if data.form_completed else None,
        per_completed_form_inr=round(total_usd * fx, 2) if data.form_completed else None,
        projection_1000_usd=round(total_usd * 1000, 2),
        projection_1000_inr=round(total_usd * fx * 1000, 2),
        usd_to_inr=fx,
        rates_last_updated=settings["rates_last_updated"],
        note=("Estimate from logged usage and the rates in settings. "
              + ("" if has_usage else "No usage was logged for this call. ")
              + "Cost per completed form is only shown when complete_form succeeded."),
    )


def cost_score(cost: CostSection, settings: dict) -> float | None:
    """0-100: 100 at or below the target INR per minute, 0 at 3x the target."""
    if cost.per_minute_inr is None or cost.total_usd == 0:
        return None
    target = float(settings["cost_target_inr_per_min"])
    if cost.per_minute_inr <= target:
        return 100.0
    return round(max(0.0, 100 * (1 - (cost.per_minute_inr - target) / (2 * target))), 1)
