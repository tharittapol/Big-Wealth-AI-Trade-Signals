"""Tests for scanner.py — mocks Claude discovery and data fetching."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.agent.models import CandidateTicker


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_df(rows: int = 35, base: float = 20.0) -> pd.DataFrame:
    close = base + np.linspace(0, 3, rows)
    idx = pd.date_range("2026-01-01", periods=rows, freq="D")
    idx.name = "datetime"
    return pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.ones(rows) * 1_000_000,
    }, index=idx)


_DISCOVERY_US = [
    {"symbol": "SOFI", "news_summary": "SOFI beats Q1 earnings; revenue +37%", "catalyst": "Earnings beat"},
    {"symbol": "PLTR", "news_summary": "PLTR lands new DoD contract", "catalyst": "Contract win"},
]

_DISCOVERY_CRYPTO = [
    {"symbol": "BTC/USDT", "news_summary": "Bitcoin ETF inflow record high", "catalyst": "ETF demand"},
    {"symbol": "ETH/USDT", "news_summary": "Ethereum Pectra upgrade went live", "catalyst": "Network upgrade"},
]


# ── _df_to_records ─────────────────────────────────────────────────────────────

def test_df_to_records_produces_records_with_datetime():
    from src.agent.scanner import _df_to_records
    df = _make_df(5)
    records = _df_to_records(df)
    assert len(records) == 5
    assert "close" in records[0]
    assert "datetime" in records[0]


# ── _discover_us_candidates ────────────────────────────────────────────────────

def test_discover_us_candidates_parses_claude_json(mocker):
    mocker.patch(
        "src.agent.scanner.run_claude",
        return_value='{"candidates": [{"symbol": "SOFI", "news_summary": "Earnings beat", "catalyst": "Earnings"}]}',
    )
    from src.agent.scanner import _discover_us_candidates

    result = _discover_us_candidates()

    assert result == [{"symbol": "SOFI", "news_summary": "Earnings beat", "catalyst": "Earnings"}]


def test_discover_us_candidates_falls_back_on_error(mocker):
    mocker.patch(
        "src.agent.scanner.run_claude",
        side_effect=RuntimeError("CLI not found"),
    )
    from src.agent.scanner import _discover_us_candidates

    result = _discover_us_candidates()

    assert isinstance(result, list)
    assert len(result) > 0  # fallback list returned


def test_discover_us_candidates_falls_back_on_empty_response(mocker):
    mocker.patch("src.agent.scanner.run_claude", return_value='{"candidates": []}')
    from src.agent.scanner import _discover_us_candidates

    result = _discover_us_candidates()

    assert len(result) > 0  # fallback list used when Claude returns empty


# ── _discover_crypto_candidates ────────────────────────────────────────────────

def test_discover_crypto_candidates_parses_claude_json(mocker):
    mocker.patch(
        "src.agent.scanner.run_claude",
        return_value='{"candidates": [{"symbol": "BTC/USDT", "news_summary": "ETF inflow", "catalyst": "ETF"}]}',
    )
    from src.agent.scanner import _discover_crypto_candidates

    result = _discover_crypto_candidates()

    assert result == [{"symbol": "BTC/USDT", "news_summary": "ETF inflow", "catalyst": "ETF"}]


def test_discover_crypto_candidates_returns_empty_on_error(mocker):
    mocker.patch(
        "src.agent.scanner.run_claude",
        side_effect=RuntimeError("CLI not found"),
    )
    from src.agent.scanner import _discover_crypto_candidates

    result = _discover_crypto_candidates()

    assert result == []  # crypto falls back to [] (caller uses Binance top volume)


# ── scan_us_stocks ─────────────────────────────────────────────────────────────

def test_scan_us_stocks_returns_candidates(mocker):
    mocker.patch("src.agent.scanner._discover_us_candidates", return_value=_DISCOVERY_US)
    mocker.patch(
        "src.agent.scanner.fetch_multiple",
        return_value={"SOFI": _make_df(), "PLTR": _make_df()},
    )

    from src.agent.scanner import scan_us_stocks
    result = scan_us_stocks(max_candidates=2, price_cap=50.0)

    assert isinstance(result, list)
    assert all(isinstance(c, CandidateTicker) for c in result)


def test_scan_us_stocks_buffers_news_from_discovery(mocker):
    mocker.patch("src.agent.scanner._discover_us_candidates", return_value=_DISCOVERY_US)
    mocker.patch(
        "src.agent.scanner.fetch_multiple",
        return_value={"SOFI": _make_df()},
    )

    from src.agent.scanner import scan_us_stocks
    result = scan_us_stocks()

    sofi = next((c for c in result if c.symbol == "SOFI"), None)
    assert sofi is not None
    assert len(sofi.news) > 0
    assert any("earnings" in item.get("title", "").lower() for item in sofi.news)


def test_scan_us_stocks_buffers_catalyst(mocker):
    mocker.patch("src.agent.scanner._discover_us_candidates", return_value=_DISCOVERY_US)
    mocker.patch(
        "src.agent.scanner.fetch_multiple",
        return_value={"SOFI": _make_df()},
    )

    from src.agent.scanner import scan_us_stocks
    result = scan_us_stocks()

    sofi = next((c for c in result if c.symbol == "SOFI"), None)
    assert sofi is not None
    assert any(item.get("catalyst") == "Earnings beat" for item in sofi.news)


def test_scan_us_stocks_filters_price_cap(mocker):
    expensive_df = _make_df()
    expensive_df["close"] = 100.0  # above $50 cap

    mocker.patch(
        "src.agent.scanner._discover_us_candidates",
        return_value=[{"symbol": "NVDA", "news_summary": "GPU demand", "catalyst": "AI"}],
    )
    mocker.patch("src.agent.scanner.fetch_multiple", return_value={"NVDA": expensive_df})

    from src.agent.scanner import scan_us_stocks
    result = scan_us_stocks(price_cap=50.0)

    assert result == []


def test_scan_us_stocks_skips_insufficient_data(mocker):
    mocker.patch(
        "src.agent.scanner._discover_us_candidates",
        return_value=[{"symbol": "SOFI", "news_summary": "", "catalyst": ""}],
    )
    mocker.patch("src.agent.scanner.fetch_multiple", return_value={"SOFI": _make_df(rows=5)})

    from src.agent.scanner import scan_us_stocks
    result = scan_us_stocks()

    assert result == []


def test_scan_us_stocks_fallback_on_discovery_failure(mocker):
    mocker.patch(
        "src.agent.scanner._discover_us_candidates",
        side_effect=RuntimeError("Claude web search failed"),
    )
    mocker.patch("src.agent.scanner.fetch_multiple", return_value={"SOFI": _make_df()})

    from src.agent.scanner import scan_us_stocks
    # Should not raise; discovery failure falls back to hardcoded symbols
    result = scan_us_stocks()

    assert isinstance(result, list)


# ── scan_crypto ────────────────────────────────────────────────────────────────

def test_scan_crypto_returns_candidates(mocker):
    mocker.patch("src.agent.scanner._discover_crypto_candidates", return_value=_DISCOVERY_CRYPTO)
    mocker.patch(
        "src.agent.scanner.crypto_fetch_multiple",
        return_value={"BTC/USDT": _make_df(), "ETH/USDT": _make_df()},
    )

    from src.agent.scanner import scan_crypto
    result = scan_crypto(min_score=0)

    assert isinstance(result, list)
    assert all(isinstance(c, CandidateTicker) for c in result)


def test_scan_crypto_buffers_news_from_discovery(mocker):
    mocker.patch("src.agent.scanner._discover_crypto_candidates", return_value=_DISCOVERY_CRYPTO)
    mocker.patch(
        "src.agent.scanner.crypto_fetch_multiple",
        return_value={"BTC/USDT": _make_df()},
    )

    from src.agent.scanner import scan_crypto
    result = scan_crypto(min_score=0)

    btc = next((c for c in result if c.symbol == "BTC/USDT"), None)
    assert btc is not None
    assert len(btc.news) > 0
    assert any("ETF" in item.get("title", "") for item in btc.news)


def test_scan_crypto_filters_by_min_score(mocker):
    mocker.patch("src.agent.scanner._discover_crypto_candidates", return_value=_DISCOVERY_CRYPTO)
    # flat price → all indicators score 0
    mocker.patch(
        "src.agent.scanner.crypto_fetch_multiple",
        return_value={"BTC/USDT": _make_df(), "ETH/USDT": _make_df()},
    )

    from src.agent.scanner import scan_crypto
    result = scan_crypto(min_score=99)  # impossible threshold → all filtered

    assert result == []


def test_scan_crypto_uses_binance_fallback_when_discovery_empty(mocker):
    mocker.patch("src.agent.scanner._discover_crypto_candidates", return_value=[])
    mock_top = mocker.patch(
        "src.agent.scanner.fetch_top_volume_pairs",
        return_value=["BTC/USDT", "ETH/USDT"],
    )
    mocker.patch("src.agent.scanner.crypto_fetch_multiple", return_value={})

    from src.agent.scanner import scan_crypto
    scan_crypto()

    mock_top.assert_called_once()


def test_scan_crypto_uses_hardcoded_fallback_when_binance_also_fails(mocker):
    mocker.patch("src.agent.scanner._discover_crypto_candidates", return_value=[])
    mocker.patch("src.agent.scanner.fetch_top_volume_pairs", return_value=[])
    mock_fetch = mocker.patch("src.agent.scanner.crypto_fetch_multiple", return_value={})

    from src.agent.scanner import scan_crypto
    scan_crypto()

    # Should call fetch with _FALLBACK_CRYPTO_SYMBOLS
    called_symbols = mock_fetch.call_args[0][0]
    assert len(called_symbols) > 0
