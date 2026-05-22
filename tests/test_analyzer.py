import json
import pytest
from unittest.mock import patch

from src.agent.analyzer import pick_top3, _build_signal, _generate_reasoning_th, _parse_json_response
from src.agent.models import CandidateTicker, TradeSignal


def _make_candidate(
    symbol: str = "SOFI",
    price: float = 10.0,
    score: int = 3,
    fired: list[str] | None = None,
    bb_lower: float = 9.2,
) -> CandidateTicker:
    if fired is None:
        fired = ["RSI=35 (oversold <40)", "MACD bullish zero-cross"]
    return CandidateTicker(
        symbol=symbol,
        market="us_stock",
        current_price=price,
        indicators={
            "score": score,
            "fired": fired,
            "RSI_14": 35.0,
            "MACDh_12_26_9": 0.12,
            "EMA_9": 9.8,
            "EMA_21": 9.5,
            "BBL_20_2.0": bb_lower,
            "BBU_20_2.0": 11.0,
        },
        news=[{"title": "SOFI beats earnings", "publisher": "Reuters", "link": "", "published_utc": ""}],
        ohlcv_recent=[],
    )


_SAMPLE_CLI_RESPONSE = json.dumps({
    "signals": [
        {
            "symbol": "SOFI",
            "entry": 10.0,
            "tp": 12.5,
            "sl": 9.0,
            "confidence": "high",
            "timeframe_days": 3,
            "reasoning_th": "SOFI RSI oversold MACD cross ขึ้น ราคาใกล้แนวรับ",
        },
        {
            "symbol": "PLTR",
            "entry": 20.0,
            "tp": 24.0,
            "sl": 18.5,
            "confidence": "medium",
            "timeframe_days": 5,
            "reasoning_th": "PLTR BB lower band touch มีข่าวสัญญาใหม่",
        },
        {
            "symbol": "AAL",
            "entry": 15.0,
            "tp": 18.0,
            "sl": 13.8,
            "confidence": "medium",
            "timeframe_days": 4,
            "reasoning_th": "AAL EMA cross ขึ้น sector airline recover",
        },
    ]
})


# ── pick_top3 — AI path ───────────────────────────────────────────────────────

@patch("src.agent.analyzer.run_claude")
def test_pick_top3_returns_ai_signals(mock_run_claude):
    mock_run_claude.return_value = _SAMPLE_CLI_RESPONSE
    candidates = [_make_candidate(s, p) for s, p in [("SOFI", 10), ("PLTR", 20), ("AAL", 15), ("F", 12)]]

    signals = pick_top3(candidates, "us_stock")

    assert len(signals) == 3
    assert all(isinstance(s, TradeSignal) for s in signals)
    assert all(s.market == "us_stock" for s in signals)


@patch("src.agent.analyzer.run_claude")
def test_pick_top3_ai_signals_have_thai_reasoning(mock_run_claude):
    mock_run_claude.return_value = _SAMPLE_CLI_RESPONSE
    signals = pick_top3([_make_candidate()], "us_stock")
    assert any(ord(c) > 127 for c in signals[0].reasoning_th)


@patch("src.agent.analyzer.run_claude")
def test_pick_top3_falls_back_to_score_based_on_cli_error(mock_run_claude):
    mock_run_claude.side_effect = RuntimeError("Claude CLI not found")
    candidates = [
        _make_candidate("HIGH", score=4),
        _make_candidate("MID",  score=3),
        _make_candidate("LOW",  score=1),
    ]
    signals = pick_top3(candidates, "us_stock")
    assert len(signals) == 3
    assert signals[0].symbol == "HIGH"


@patch("src.agent.analyzer.run_claude")
def test_pick_top3_falls_back_when_response_has_no_json(mock_run_claude):
    mock_run_claude.return_value = "ขอโทษ ไม่สามารถวิเคราะห์ได้"
    candidates = [_make_candidate("SOFI", score=3)]
    signals = pick_top3(candidates, "us_stock")
    # Should fall back to score-based — still returns a signal
    assert len(signals) == 1
    assert signals[0].symbol == "SOFI"


def test_pick_top3_returns_empty_for_no_candidates():
    signals = pick_top3([], "us_stock")
    assert signals == []


# ── _parse_json_response ──────────────────────────────────────────────────────

def test_parse_json_response_extracts_signals():
    signals = _parse_json_response(_SAMPLE_CLI_RESPONSE, "us_stock")
    assert len(signals) == 3
    assert signals[0].symbol == "SOFI"
    assert signals[0].tp == pytest.approx(12.5)
    assert signals[0].sl == pytest.approx(9.0)


def test_parse_json_response_computes_tp_sl_pct():
    signals = _parse_json_response(_SAMPLE_CLI_RESPONSE, "us_stock")
    s = signals[0]
    assert s.tp_pct == pytest.approx(25.0, rel=0.01)
    assert s.sl_pct == pytest.approx(-10.0, rel=0.01)


def test_parse_json_response_returns_empty_on_no_json():
    signals = _parse_json_response("No JSON here at all.", "us_stock")
    assert signals == []


def test_parse_json_response_skips_malformed_signal():
    response = json.dumps({
        "signals": [
            {"symbol": "GOOD", "entry": 10.0, "tp": 12.0, "sl": 9.0,
             "confidence": "high", "timeframe_days": 3, "reasoning_th": "ok"},
            {"symbol": "BAD"},  # missing required fields
        ]
    })
    signals = _parse_json_response(response, "us_stock")
    assert len(signals) == 1
    assert signals[0].symbol == "GOOD"


def test_parse_json_response_repairs_trailing_comma():
    response = (
        '{"signals": [{"symbol": "SOFI", "entry": 10.0, "tp": 12.0, "sl": 9.0,'
        '"confidence": "high", "timeframe_days": 3, "reasoning_th": "ok",}]}'
    )
    signals = _parse_json_response(response, "us_stock")
    assert len(signals) == 1
    assert signals[0].symbol == "SOFI"


def test_parse_json_response_repairs_unescaped_inner_quote():
    response = (
        '{"signals": [{"symbol": "SOFI", "entry": 10.0, "tp": 12.0, "sl": 9.0,'
        '"confidence": "high", "timeframe_days": 3,'
        '"reasoning_th": "SOFI ใกล้แนวรับ "strong" — RSI oversold"}]}'
    )
    signals = _parse_json_response(response, "us_stock")
    assert len(signals) == 1
    assert signals[0].symbol == "SOFI"


def test_parse_json_response_repairs_missing_comma_between_signals():
    response = (
        '{"signals": ['
        '{"symbol": "A", "entry": 1.0, "tp": 1.2, "sl": 0.9, '
        '"confidence": "high", "timeframe_days": 3, "reasoning_th": "ok"}'
        '{"symbol": "B", "entry": 2.0, "tp": 2.4, "sl": 1.8, '
        '"confidence": "high", "timeframe_days": 3, "reasoning_th": "ok"}'
        ']}'
    )
    signals = _parse_json_response(response, "us_stock")
    assert len(signals) >= 1


def test_parse_json_response_returns_empty_on_unrepairable_garbage():
    signals = _parse_json_response("{ this is { not json at all }", "us_stock")
    assert signals == []


# ── Score-based fallback (_build_signal / _generate_reasoning_th) ─────────────

def test_build_signal_tp_above_entry():
    c = _make_candidate("SOFI", price=10.0, score=3)
    signal = _build_signal(c, "us_stock")
    assert signal.tp > signal.entry


def test_build_signal_sl_below_entry():
    c = _make_candidate("SOFI", price=10.0, score=3)
    signal = _build_signal(c, "us_stock")
    assert signal.sl < signal.entry


def test_build_signal_confidence_high_for_score4():
    c = _make_candidate("SOFI", price=10.0, score=4)
    signal = _build_signal(c, "us_stock")
    assert signal.confidence == "high"


def test_build_signal_confidence_medium_for_score3():
    c = _make_candidate("SOFI", price=10.0, score=3)
    signal = _build_signal(c, "us_stock")
    assert signal.confidence == "medium"


def test_build_signal_confidence_low_for_score_lt3():
    c = _make_candidate("SOFI", price=10.0, score=2)
    signal = _build_signal(c, "us_stock")
    assert signal.confidence == "low"


def test_build_signal_crypto_tp_pct_higher_than_us():
    c_us = _make_candidate("SOFI",     price=10.0, score=4)
    c_cr = _make_candidate("BTC/USDT", price=10.0, score=4)
    sig_us = _build_signal(c_us, "us_stock")
    sig_cr = _build_signal(c_cr, "crypto")
    assert (sig_cr.tp - c_cr.current_price) > (sig_us.tp - c_us.current_price)


def test_build_signal_uses_hard_stop_when_bb_lower_too_low():
    c = _make_candidate("SOFI", price=10.0, score=3, bb_lower=8.0)
    signal = _build_signal(c, "us_stock")
    assert signal.sl == pytest.approx(9.5, rel=0.01)


def test_generate_reasoning_th_mentions_rsi_when_fired():
    c = _make_candidate("SOFI", fired=["RSI=35 (oversold <40)"])
    reasoning = _generate_reasoning_th(c)
    assert "RSI" in reasoning


def test_generate_reasoning_th_mentions_macd_when_fired():
    c = _make_candidate("SOFI", fired=["MACD bullish zero-cross"])
    reasoning = _generate_reasoning_th(c)
    assert "MACD" in reasoning


def test_generate_reasoning_th_fallback_when_no_fired():
    c = _make_candidate("SOFI", fired=[], score=2)
    reasoning = _generate_reasoning_th(c)
    assert "2/4" in reasoning


# ── Model and news display ─────────────────────────────────────────────────────

@patch("src.agent.analyzer.run_claude")
def test_pick_top3_uses_opus_model(mock_run_claude):
    mock_run_claude.return_value = _SAMPLE_CLI_RESPONSE
    pick_top3([_make_candidate()], "us_stock")
    assert mock_run_claude.call_args[1].get("model") == "opus"


@patch("src.agent.analyzer.run_claude")
def test_pick_top3_prompt_includes_catalyst_label(mock_run_claude):
    mock_run_claude.return_value = _SAMPLE_CLI_RESPONSE
    candidate = _make_candidate()
    candidate.news = [{"title": "SOFI beats earnings", "catalyst": "Earnings beat"}]
    pick_top3([candidate], "us_stock")
    prompt_used = mock_run_claude.call_args[0][0]
    assert "Earnings beat" in prompt_used


@patch("src.agent.analyzer.run_claude")
def test_pick_top3_prompt_shows_no_news_label_when_empty(mock_run_claude):
    mock_run_claude.return_value = _SAMPLE_CLI_RESPONSE
    candidate = _make_candidate()
    candidate.news = []
    pick_top3([candidate], "us_stock")
    prompt_used = mock_run_claude.call_args[0][0]
    assert "ไม่มีข่าว" in prompt_used
