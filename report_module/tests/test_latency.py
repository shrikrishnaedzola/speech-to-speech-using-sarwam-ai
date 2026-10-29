import pytest

from report_module.latency import analyse_latency, latency_score, percentile, rate
from report_module.settings import DEFAULTS
from tests.helpers import call_data, caller


def test_percentile_matches_numpy_linear():
    values = [100, 200, 300, 400, 500]
    assert percentile(values, 50) == 300
    assert percentile(values, 90) == pytest.approx(460)
    assert percentile([], 50) is None


@pytest.mark.parametrize("ms, expected", [(999, "Good"), (1000, "OK"), (1500, "OK"), (1501, "Poor"), (None, None)])
def test_rating_bands(ms, expected):
    assert rate(ms, DEFAULTS) == expected


def test_latency_score():
    assert latency_score(800, DEFAULTS) == 100
    assert latency_score(1250, DEFAULTS) == 75
    assert latency_score(1500, DEFAULTS) == 50
    assert latency_score(3000, DEFAULTS) == 0
    assert latency_score(5000, DEFAULTS) == 0
    assert latency_score(None, DEFAULTS) is None


def test_stats_skip_greeting_and_find_slowest():
    turns = [{"turn_index": 0, "total_ms": 3000},  # greeting: not a reply to the caller
             {"turn_index": 1, "total_ms": 800}, {"turn_index": 2, "total_ms": 1200},
             {"turn_index": 3, "total_ms": 2000, "llm_ttft_ms": 1500, "stt_ms": 200},
             {"turn_index": 4, "total_ms": 1000}]
    data = call_data(turns=turns, transcript=[caller(f"t{i}", i * 5) for i in range(1, 5)],
                     tool_calls=[{"name": "save_answer", "arguments": {"field_id": "age"}, "success": True, "offset_s": 16}])
    lat = analyse_latency(data, DEFAULTS)
    assert lat.average_ms == 1250
    assert lat.median_ms == 1100
    assert lat.max_ms == 2000
    assert lat.rating == "OK"
    assert lat.has_step_split
    assert [s.turn_index for s in lat.slowest] == [3, 2, 4]
    assert "LLM first token" in lat.slowest[0].reason and "save_answer" in lat.slowest[0].reason
    turn3 = next(t for t in lat.per_turn if t.turn_index == 3)
    assert turn3.other_ms == 300  # 2000 - 200 - 1500


def test_no_turns():
    lat = analyse_latency(call_data(), DEFAULTS)
    assert lat.average_ms is None and lat.rating is None and lat.slowest == []
