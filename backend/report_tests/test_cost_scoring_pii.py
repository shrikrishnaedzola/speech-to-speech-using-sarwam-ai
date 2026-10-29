import pytest

from report_module.cost import analyse_cost, cost_score
from report_module.pii import AADHAAR_MASK, PHONE_MASK, mask_call_data, mask_text
from report_module.scoring import overall
from report_module.settings import DEFAULTS, _merge
from tests.helpers import call_data, caller

FX = DEFAULTS["usd_to_inr"]


# ------------------------------------------------------------------ cost per provider


def test_openai_cost():
    data = call_data("openai", usage={"audio_input_tokens": 1_000_000, "llm_cached_input_tokens": 0,
                                      "audio_output_tokens": 1_000_000, "llm_input_tokens": 0, "llm_output_tokens": 0})
    cost = analyse_cost(data, DEFAULTS)
    assert cost.total_usd == pytest.approx(32 + 64)
    assert cost.total_inr == pytest.approx(96 * FX)


def test_openai_cached_tokens_are_cheaper():
    data = call_data("openai", usage={"audio_input_tokens": 1_000_000, "llm_cached_input_tokens": 1_000_000})
    assert analyse_cost(data, DEFAULTS).total_usd == pytest.approx(0.40)


def test_gemini_cost():
    data = call_data("gemini", usage={"audio_input_tokens": 1_000_000, "audio_output_tokens": 500_000})
    assert analyse_cost(data, DEFAULTS).total_usd == pytest.approx(3 + 6)


def test_elevenlabs_cost_per_minute():
    data = call_data("elevenlabs", usage={"call_minutes": 10})
    cost = analyse_cost(data, DEFAULTS)
    assert cost.total_usd == pytest.approx(10 * (0.08 + 0.01))
    assert cost.per_minute_usd == pytest.approx(0.45)  # duration_s=120 -> 2 minutes


def test_sarvam_cost_in_inr():
    data = call_data("sarvam", usage={"stt_minutes": 2, "llm_input_tokens": 1_000_000, "llm_output_tokens": 0,
                                      "tts_characters": 10_000, "tts_model": "bulbul:v3"})
    cost = analyse_cost(data, DEFAULTS)
    assert cost.total_inr == pytest.approx(0.98 + 15 + 30, abs=0.01)
    v4 = call_data("sarvam", usage={"tts_characters": 10_000, "tts_model": "bulbul:v4-flash"})
    assert analyse_cost(v4, DEFAULTS).total_inr == pytest.approx(10, abs=0.01)


def test_projection_and_per_form():
    data = call_data("elevenlabs", usage={"call_minutes": 2}, form_completed=True)
    cost = analyse_cost(data, DEFAULTS)
    assert cost.projection_1000_usd == pytest.approx(cost.total_usd * 1000, abs=0.01)
    assert cost.per_completed_form_usd == pytest.approx(cost.total_usd)
    assert analyse_cost(call_data("elevenlabs", usage={"call_minutes": 2}), DEFAULTS).per_completed_form_usd is None


def test_cost_score():
    cheap = analyse_cost(call_data("sarvam", usage={"stt_minutes": 2}), DEFAULTS)
    assert cost_score(cheap, DEFAULTS) == 100
    assert cost_score(analyse_cost(call_data("sarvam"), DEFAULTS), DEFAULTS) is None  # no usage logged


# ------------------------------------------------------------------ overall score


def test_overall_weights_and_verdict():
    scores = {"accuracy": 100, "mishearings": 100, "latency": 100, "voice_quality": 100, "language": 100, "cost": 100}
    assert overall(scores, DEFAULTS)[:2] == (100, "Good")
    scores = {"accuracy": 50, "mishearings": 50, "latency": 50, "voice_quality": 50, "language": 50, "cost": 50}
    assert overall(scores, DEFAULTS)[:2] == (50, "Needs improvement")
    scores["accuracy"] = 0
    score, verdict, _, _ = overall(scores, DEFAULTS)
    assert score == pytest.approx(32.5) and verdict == "Poor"


def test_missing_section_weight_is_shared():
    scores = {"accuracy": 80, "mishearings": 100, "latency": 100, "voice_quality": None, "language": 100, "cost": 100}
    score, _, used, missing = overall(scores, DEFAULTS)
    assert missing == ["voice_quality"]
    assert sum(used.values()) == pytest.approx(100, abs=0.2)
    assert score == pytest.approx((80 * 35 + 100 * 50) / 85, abs=0.1)


def test_custom_weights():
    settings = _merge(DEFAULTS, {"weights": {"accuracy": 100, "mishearings": 0, "latency": 0, "voice_quality": 0,
                                             "language": 0, "cost": 0}})
    scores = {"accuracy": 40, "mishearings": 100, "latency": 100, "voice_quality": 100, "language": 100, "cost": 100}
    assert overall(scores, settings)[0] == 40


# ------------------------------------------------------------------ PII masking


@pytest.mark.parametrize("text", ["9876543210", "+91 98765 43210", "98765-43210", "call 091 9876543210 now",
                                  "०९८७६५४३२१०".replace("०", "", 1)])
def test_phone_masked(text):
    masked, kinds = mask_text(text)
    assert PHONE_MASK in masked and kinds == ["phone"]
    assert not any(ch.isdigit() for ch in masked.replace(PHONE_MASK, ""))


@pytest.mark.parametrize("text", ["2345 6789 0123", "my number is 234567890123", "२३४५ ६७८९ ०१२३"])
def test_aadhaar_masked(text):
    masked, kinds = mask_text(text)
    assert AADHAAR_MASK in masked and kinds == ["aadhaar"]


@pytest.mark.parametrize("text", ["I am 35", "pin 400001", "1234567890", "rating 4 out of 5", "123456789012345678"])
def test_not_masked(text):
    assert mask_text(text) == (text, [])


def test_mask_call_data_everywhere():
    data = call_data(
        transcript=[caller("Mera number 98765 43210 hai", 1)],
        tool_calls=[{"name": "save_answer", "arguments": {"field_id": "age", "value": "9876543210"}, "success": False}],
        answers=[{"field_id": "age", "value": 9876543210, "status": "filled"}],
    )
    masked, found = mask_call_data(data)
    assert found.count("phone") == 3
    assert PHONE_MASK in masked.transcript[0].text
    assert masked.tool_calls[0].arguments["value"] == PHONE_MASK
    assert masked.answers[0].value == PHONE_MASK
    assert "98765" not in masked.model_dump_json()
