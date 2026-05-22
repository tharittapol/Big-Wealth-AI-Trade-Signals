import json
import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch

from src.agent.tp_advisor import get_tp_advice, _fetch_since_entry, _build_prompt, _parse_tp_response
from src.agent.models import TPAdvice


def _make_ohlcv(n: int = 30, base: float = 50.0) -> pd.DataFrame:
    close = base + np.linspace(0, 10, n)
    return pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": np.ones(n) * 1e6},
        index=pd.date_range("2026-04-01", periods=n, freq="D"),
    )


_SAMPLE_TP_JSON = json.dumps({
    "tp_levels": [
        {"price": 58.0, "rationale_th": "แนวต้าน BB upper band"},
        {"price": 62.0, "rationale_th": "แนวต้าน swing high เดิม"},
    ],
    "action": "hold",
    "reasoning_th": "ราคายังวิ่งขึ้นต่อได้ momentum ยังแข็งแกร่ง",
})


# ── _fetch_since_entry ────────────────────────────────────────────────────────

def test_fetch_since_entry_filters_by_date():
    df = _make_ohlcv(30)
    with patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv", return_value=df):
        result = _fetch_since_entry("AAPL", "2026-04-15", "us_stock")
    assert result is not None
    assert result.index[0] >= pd.Timestamp("2026-04-15")


def test_fetch_since_entry_returns_full_df_when_date_too_recent():
    df = _make_ohlcv(30)
    with patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv", return_value=df):
        result = _fetch_since_entry("AAPL", "2026-05-20", "us_stock")
    assert result is not None
    assert len(result) >= 5


def test_fetch_since_entry_returns_none_when_no_data():
    with patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv", return_value=None):
        result = _fetch_since_entry("AAPL", "2026-04-01", "us_stock")
    assert result is None


def test_fetch_since_entry_uses_crypto_fetcher():
    df = _make_ohlcv(30)
    with patch("src.agent.tp_advisor.crypto.fetch_ohlcv", return_value=df) as mock_crypto:
        _fetch_since_entry("BTC/USDT", "2026-04-01", "crypto")
    mock_crypto.assert_called_once()


# ── _build_prompt ──────────────────────────────────────────────────────────────

def test_build_prompt_contains_key_info():
    from src.indicators.technical import add_indicators
    df = add_indicators(_make_ohlcv(60))
    prompt = _build_prompt("AAPL", "us_stock", "2026-04-01", 50.0, 55.0, 10.0, df, news_items=[])
    assert "AAPL" in prompt
    assert "50.0" in prompt
    assert "55.0" in prompt
    assert "+10.00%" in prompt


def test_build_prompt_includes_news_section():
    from src.indicators.technical import add_indicators
    df = add_indicators(_make_ohlcv(60))
    news = [{"title": "AAPL beats earnings", "catalyst": "Earnings beat"}]
    prompt = _build_prompt("AAPL", "us_stock", "2026-04-01", 50.0, 55.0, 10.0, df, news_items=news)
    assert "AAPL beats earnings" in prompt
    assert "Earnings beat" in prompt


def test_build_prompt_shows_no_news_label_when_empty():
    from src.indicators.technical import add_indicators
    df = add_indicators(_make_ohlcv(60))
    prompt = _build_prompt("AAPL", "us_stock", "2026-04-01", 50.0, 55.0, 10.0, df, news_items=[])
    assert "ไม่มีข้อมูลข่าว" in prompt


# ── _parse_tp_response ────────────────────────────────────────────────────────

def test_parse_tp_response_builds_tp_advice():
    advice = _parse_tp_response(_SAMPLE_TP_JSON, "AAPL", "us_stock", 50.0, 55.0, 10.0)
    assert isinstance(advice, TPAdvice)
    assert advice.symbol == "AAPL"
    assert advice.action == "hold"
    assert len(advice.tp_levels) == 2
    assert advice.tp_levels[0].price == 58.0


def test_parse_tp_response_returns_none_on_bad_json():
    advice = _parse_tp_response("not json", "AAPL", "us_stock", 50.0, 55.0, 10.0)
    assert advice is None


def test_parse_tp_response_returns_none_when_no_json_block():
    advice = _parse_tp_response("ขอโทษไม่มีข้อมูล", "AAPL", "us_stock", 50.0, 55.0, 10.0)
    assert advice is None


# ── get_tp_advice ─────────────────────────────────────────────────────────────

@patch("src.agent.tp_advisor._fetch_us_news", return_value=[])
@patch("src.agent.tp_advisor.run_claude")
@patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv")
def test_get_tp_advice_returns_tp_advice(mock_fetch, mock_run_claude, mock_news):
    mock_fetch.return_value = _make_ohlcv(60, base=50.0)
    mock_run_claude.return_value = _SAMPLE_TP_JSON

    advice = get_tp_advice("AAPL", "2026-04-01", 50.0, market="us_stock")

    assert isinstance(advice, TPAdvice)
    assert advice.symbol == "AAPL"
    assert advice.action == "hold"
    assert len(advice.tp_levels) == 2
    assert advice.tp_levels[0].price == 58.0


@patch("src.agent.tp_advisor._fetch_us_news", return_value=[])
@patch("src.agent.tp_advisor.run_claude")
@patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv")
def test_get_tp_advice_calculates_pnl(mock_fetch, mock_run_claude, mock_news):
    mock_fetch.return_value = _make_ohlcv(60, base=50.0)
    mock_run_claude.return_value = _SAMPLE_TP_JSON

    advice = get_tp_advice("AAPL", "2026-04-01", 50.0, market="us_stock")
    assert advice.unrealized_pnl_pct > 0


@patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv")
def test_get_tp_advice_returns_none_when_no_data(mock_fetch):
    mock_fetch.return_value = None
    advice = get_tp_advice("AAPL", "2026-04-01", 50.0)
    assert advice is None


@patch("src.agent.tp_advisor._fetch_us_news", return_value=[])
@patch("src.agent.tp_advisor.run_claude")
@patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv")
def test_get_tp_advice_returns_none_on_cli_error(mock_fetch, mock_run_claude, mock_news):
    mock_fetch.return_value = _make_ohlcv(60)
    mock_run_claude.side_effect = RuntimeError("Claude CLI not found")

    advice = get_tp_advice("AAPL", "2026-04-01", 50.0)
    assert advice is None


@patch("src.agent.tp_advisor._fetch_us_news", return_value=[])
@patch("src.agent.tp_advisor.run_claude")
@patch("src.agent.tp_advisor.us_stocks.fetch_ohlcv")
def test_get_tp_advice_returns_none_on_bad_response(mock_fetch, mock_run_claude, mock_news):
    mock_fetch.return_value = _make_ohlcv(60)
    mock_run_claude.return_value = "ขอโทษ ไม่สามารถวิเคราะห์ได้ในขณะนี้"

    advice = get_tp_advice("AAPL", "2026-04-01", 50.0)
    assert advice is None


# ── News buffering tests ───────────────────────────────────────────────────────

@patch("src.agent.tp_advisor._fetch_us_news")
@patch("src.agent.tp_advisor._fetch_since_entry")
@patch("src.agent.tp_advisor.run_claude")
def test_get_tp_advice_buffers_us_news(mock_run_claude, mock_fetch_entry, mock_fetch_news):
    from src.indicators.technical import add_indicators
    mock_fetch_entry.return_value = add_indicators(_make_ohlcv(60))
    mock_fetch_news.return_value = [{"title": "SOFI beats earnings", "catalyst": "Earnings beat"}]
    mock_run_claude.return_value = _SAMPLE_TP_JSON

    get_tp_advice("SOFI", "2026-05-01", 10.0, "us_stock")

    prompt_used = mock_run_claude.call_args[0][0]
    assert "SOFI beats earnings" in prompt_used


@patch("src.agent.tp_advisor._fetch_crypto_news")
@patch("src.agent.tp_advisor._fetch_since_entry")
@patch("src.agent.tp_advisor.run_claude")
def test_get_tp_advice_buffers_crypto_news(mock_run_claude, mock_fetch_entry, mock_fetch_news):
    from src.indicators.technical import add_indicators
    mock_fetch_entry.return_value = add_indicators(_make_ohlcv(60))
    mock_fetch_news.return_value = [{"title": "BTC ETF inflow record", "catalyst": "ETF"}]
    mock_run_claude.return_value = _SAMPLE_TP_JSON

    get_tp_advice("BTC/USDT", "2026-05-01", 62000.0, "crypto")

    prompt_used = mock_run_claude.call_args[0][0]
    assert "ETF inflow" in prompt_used


@patch("src.agent.tp_advisor._fetch_us_news", return_value=[])
@patch("src.agent.tp_advisor._fetch_since_entry")
@patch("src.agent.tp_advisor.run_claude")
def test_get_tp_advice_uses_opus_model(mock_run_claude, mock_fetch_entry, mock_fetch_news):
    from src.indicators.technical import add_indicators
    mock_fetch_entry.return_value = add_indicators(_make_ohlcv(60))
    mock_run_claude.return_value = _SAMPLE_TP_JSON

    get_tp_advice("SOFI", "2026-05-01", 10.0, "us_stock")

    assert mock_run_claude.call_args[1].get("model") == "opus"
