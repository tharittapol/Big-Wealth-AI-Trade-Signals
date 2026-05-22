"""Binance.th market data fetcher using the REST API directly.

Uses https://api.binance.th (v1 API) because ccxt does not support Binance.th.
Public endpoints (klines, ticker, exchangeInfo) work without authentication;
the API key header is included when available for better rate limits.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
import pandas as pd
import structlog

logger = structlog.get_logger()

_BASE_URL = "https://api.binance.th"

_INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1d", "3d": "3d", "1w": "1w", "1M": "1M",
}


def _get_client() -> httpx.Client:
    api_key = os.getenv("BINANCE_API_KEY", "")
    headers = {"X-MBX-APIKEY": api_key} if api_key else {}
    return httpx.Client(base_url=_BASE_URL, headers=headers, timeout=30.0)


def _to_binance_symbol(symbol: str) -> str:
    """'BTC/USDT' → 'BTCUSDT'"""
    return symbol.replace("/", "")


def _from_binance_symbol(symbol: str, quote: str = "USDT") -> str:
    """'BTCUSDT' → 'BTC/USDT'"""
    if symbol.endswith(quote):
        return f"{symbol[:-len(quote)]}/{quote}"
    return symbol


def _raw_to_df(raw: list) -> pd.DataFrame:
    """Convert Binance.th klines response to OHLCV DataFrame.

    Kline format: [openTime, open, high, low, close, volume, closeTime,
                   quoteVol, trades, takerBase, takerQuote, ignore]
    Prices are returned as strings by the API.
    """
    df = pd.DataFrame(raw, columns=[
        "datetime", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base", "taker_quote", "ignore",
    ])
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
    df = df.set_index("datetime")
    return df[["open", "high", "low", "close", "volume"]].astype(float).dropna()


def fetch_ohlcv(symbol: str, timeframe: str = "1d", limit: int = 60) -> Optional[pd.DataFrame]:
    """Fetch OHLCV candlestick data from Binance.th."""
    interval = _INTERVAL_MAP.get(timeframe, "1d")
    try:
        with _get_client() as client:
            resp = client.get("/api/v1/klines", params={
                "symbol": _to_binance_symbol(symbol),
                "interval": interval,
                "limit": limit,
            })
            resp.raise_for_status()
            raw = resp.json()
        if not raw:
            logger.warning("No data returned", symbol=symbol)
            return None
        return _raw_to_df(raw)
    except Exception as e:
        logger.error("Failed to fetch crypto data", symbol=symbol, error=str(e))
        return None


def fetch_top_volume_pairs(limit: int = 50, quote: str = "USDT") -> list[str]:
    """Fetch top N spot pairs by 24h quote volume from Binance.th.

    Binance.th's ticker/24hr endpoint requires a symbol parameter, so this
    first retrieves all active USDT pairs from exchangeInfo, then queries
    each one's 24hr ticker (capped at 120 to bound runtime).
    """
    try:
        with _get_client() as client:
            resp = client.get("/api/v1/exchangeInfo")
            resp.raise_for_status()
            info = resp.json()

            usdt_symbols = [
                s["symbol"]
                for s in info.get("symbols", [])
                if s["symbol"].endswith(quote) and s.get("status") == "TRADING"
            ]

            volumes: list[tuple[str, float]] = []
            for sym in usdt_symbols[:120]:
                try:
                    r = client.get("/api/v1/ticker/24hr", params={"symbol": sym})
                    r.raise_for_status()
                    data = r.json()
                    vol = float(data.get("quoteVolume") or 0)
                    if vol > 0:
                        volumes.append((sym, vol))
                except Exception:
                    continue

        volumes.sort(key=lambda x: x[1], reverse=True)
        return [_from_binance_symbol(sym, quote) for sym, _ in volumes[:limit]]

    except Exception as e:
        logger.error("Failed to fetch top volume pairs", error=str(e))
        return []


def get_available_symbols(quote: str = "USDT") -> set[str]:
    """Return set of all TRADING spot pairs on Binance.th in 'BTC/USDT' format."""
    try:
        with _get_client() as client:
            resp = client.get("/api/v1/exchangeInfo")
            resp.raise_for_status()
            info = resp.json()
        return {
            _from_binance_symbol(s["symbol"], quote)
            for s in info.get("symbols", [])
            if s["symbol"].endswith(quote) and s.get("status") == "TRADING"
        }
    except Exception as e:
        logger.warning("Failed to fetch available symbols from Binance.th", error=str(e))
        return set()


def fetch_multiple(
    symbols: list[str],
    timeframe: str = "1d",
    limit: int = 60,
    min_rows: int = 30,
) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for multiple symbols, skipping failures."""
    results: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if df is not None and len(df) >= min_rows:
            results[symbol] = df
        elif df is None:
            logger.warning("Skipping symbol", symbol=symbol)
    return results
