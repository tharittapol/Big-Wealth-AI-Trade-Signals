import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from src.data import us_stocks, crypto


def _make_yf_df(n: int = 30) -> pd.DataFrame:
    close = 100.0 + np.arange(n, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Volume": np.ones(n) * 1e6},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


def _make_binanceth_raw(n: int = 30) -> list:
    """Binance.th klines format: 12-element arrays, prices as strings."""
    return [
        [i * 86_400_000, str(100 + i), str(101 + i), str(99 + i), str(100.5 + i), str(1e6),
         (i + 1) * 86_400_000 - 1, str(1e8), 100, str(5e5), str(5e5), "0"]
        for i in range(n)
    ]


def _make_crypto_df(n: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    price = 100.0
    return pd.DataFrame({
        "open": [price] * n, "high": [price + 1] * n,
        "low": [price - 1] * n, "close": [price] * n,
        "volume": [1_000_000.0] * n,
    }, index=idx)


def _mock_client(json_data):
    """Return a MagicMock httpx.Client context manager that responds with json_data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_cl = MagicMock()
    mock_cl.__enter__.return_value = mock_cl
    mock_cl.get.return_value = mock_resp
    return mock_cl


# ── US stocks: OHLCV ─────────────────────────────────────────────────────────

def test_us_fetch_ohlcv_normalizes_columns():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_yf_df()
    with patch("src.data.us_stocks.yf.Ticker", return_value=mock_ticker):
        df = us_stocks.fetch_ohlcv("AAPL")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 30


def test_us_fetch_ohlcv_returns_none_on_empty():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    with patch("src.data.us_stocks.yf.Ticker", return_value=mock_ticker):
        result = us_stocks.fetch_ohlcv("INVALID")
    assert result is None


def test_us_fetch_ohlcv_returns_none_on_exception():
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = RuntimeError("network error")
    with patch("src.data.us_stocks.yf.Ticker", return_value=mock_ticker):
        result = us_stocks.fetch_ohlcv("BOOM")
    assert result is None


def test_us_fetch_multiple_skips_insufficient_data():
    short_df = _make_yf_df(n=5)
    full_df = _make_yf_df(n=40)

    def side_effect(symbol):
        m = MagicMock()
        m.history.return_value = short_df if symbol == "SHORT" else full_df
        return m

    with patch("src.data.us_stocks.yf.Ticker", side_effect=side_effect):
        results = us_stocks.fetch_multiple(["SHORT", "GOOD"], min_rows=30)
    assert "SHORT" not in results
    assert "GOOD" in results


# ── US stocks: News ───────────────────────────────────────────────────────────

def test_us_fetch_news_returns_normalized_list():
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            "content": {
                "title": "AAPL hits record",
                "pubDate": "2026-05-18T10:00:00Z",
                "provider": {"displayName": "Reuters"},
                "canonicalUrl": {"url": "https://example.com/news/1"},
            }
        }
    ]
    with patch("src.data.us_stocks.yf.Ticker", return_value=mock_ticker):
        news = us_stocks.fetch_news("AAPL", max_items=3)
    assert len(news) == 1
    assert news[0]["title"] == "AAPL hits record"
    assert news[0]["publisher"] == "Reuters"


def test_us_fetch_news_returns_empty_on_exception():
    mock_ticker = MagicMock()
    mock_ticker.news = None
    with patch("src.data.us_stocks.yf.Ticker", return_value=mock_ticker):
        news = us_stocks.fetch_news("AAPL")
    assert news == []


def test_us_fetch_news_respects_max_items():
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {"content": {"title": f"News {i}", "pubDate": "", "provider": {}, "canonicalUrl": {}}}
        for i in range(10)
    ]
    with patch("src.data.us_stocks.yf.Ticker", return_value=mock_ticker):
        news = us_stocks.fetch_news("AAPL", max_items=3)
    assert len(news) == 3


# ── Crypto: OHLCV ─────────────────────────────────────────────────────────────

def test_crypto_fetch_ohlcv_normalizes_columns():
    mock_cl = _mock_client(_make_binanceth_raw(30))
    with patch("src.data.crypto._get_client", return_value=mock_cl):
        df = crypto.fetch_ohlcv("BTC/USDT")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 30


def test_crypto_fetch_ohlcv_returns_none_on_empty():
    mock_cl = _mock_client([])
    with patch("src.data.crypto._get_client", return_value=mock_cl):
        result = crypto.fetch_ohlcv("INVALID/USDT")
    assert result is None


def test_crypto_fetch_ohlcv_returns_none_on_exception():
    mock_cl = MagicMock()
    mock_cl.__enter__.return_value = mock_cl
    mock_cl.get.side_effect = Exception("API error")
    with patch("src.data.crypto._get_client", return_value=mock_cl):
        result = crypto.fetch_ohlcv("BTC/USDT")
    assert result is None


def test_crypto_fetch_multiple_skips_failures():
    def ohlcv_side_effect(symbol, **kwargs):
        return None if symbol == "BAD/USDT" else _make_crypto_df(40)

    with patch("src.data.crypto.fetch_ohlcv", side_effect=ohlcv_side_effect):
        results = crypto.fetch_multiple(["BTC/USDT", "BAD/USDT"], min_rows=30)
    assert "BTC/USDT" in results
    assert "BAD/USDT" not in results


# ── Crypto: top volume pairs ──────────────────────────────────────────────────

def test_crypto_fetch_top_volume_pairs_returns_sorted_list():
    exchange_info = {
        "symbols": [
            {"symbol": "BTCUSDT", "status": "TRADING"},
            {"symbol": "ETHUSDT", "status": "TRADING"},
            {"symbol": "SOLUSDT", "status": "TRADING"},
            {"symbol": "XRPBTC",  "status": "TRADING"},  # non-USDT, excluded
        ]
    }
    ticker_volumes = {"BTCUSDT": "5000000", "ETHUSDT": "3000000", "SOLUSDT": "2000000"}

    def get_side_effect(url, **kwargs):
        mock_resp = MagicMock()
        if "exchangeInfo" in url:
            mock_resp.json.return_value = exchange_info
        else:
            sym = (kwargs.get("params") or {}).get("symbol", "")
            mock_resp.json.return_value = {"quoteVolume": ticker_volumes.get(sym, "0")}
        return mock_resp

    mock_cl = MagicMock()
    mock_cl.__enter__.return_value = mock_cl
    mock_cl.get.side_effect = get_side_effect

    with patch("src.data.crypto._get_client", return_value=mock_cl):
        pairs = crypto.fetch_top_volume_pairs(limit=3)

    assert pairs == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    assert "XRP/BTC" not in pairs


def test_crypto_fetch_top_volume_pairs_returns_empty_on_error():
    mock_cl = MagicMock()
    mock_cl.__enter__.return_value = mock_cl
    mock_cl.get.side_effect = Exception("network error")
    with patch("src.data.crypto._get_client", return_value=mock_cl):
        pairs = crypto.fetch_top_volume_pairs()
    assert pairs == []
