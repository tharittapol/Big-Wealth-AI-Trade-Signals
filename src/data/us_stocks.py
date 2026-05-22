import yfinance as yf
import pandas as pd
from typing import Optional
import structlog

logger = structlog.get_logger()


def fetch_ohlcv(symbol: str, period: str = "60d", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a US stock symbol via yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            logger.warning("No data returned", symbol=symbol)
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "datetime"
        return df.dropna()
    except Exception as e:
        logger.error("Failed to fetch US stock data", symbol=symbol, error=str(e))
        return None


def fetch_news(symbol: str, max_items: int = 5) -> list[dict]:
    """
    Fetch recent news headlines for a symbol via yfinance.
    Returns list of {title, publisher, link, published_utc}.
    """
    try:
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news or []
        results = []
        for item in raw_news[:max_items]:
            content = item.get("content", {})
            results.append({
                "title": content.get("title", ""),
                "publisher": content.get("provider", {}).get("displayName", ""),
                "link": content.get("canonicalUrl", {}).get("url", ""),
                "published_utc": content.get("pubDate", ""),
            })
        return results
    except Exception as e:
        logger.warning("Failed to fetch news", symbol=symbol, error=str(e))
        return []


def fetch_multiple(symbols: list[str], period: str = "60d", min_rows: int = 30) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for multiple symbols, skipping symbols with insufficient data."""
    results: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = fetch_ohlcv(symbol, period=period)
        if df is not None and len(df) >= min_rows:
            results[symbol] = df
        else:
            logger.debug("Skipping symbol (insufficient data)", symbol=symbol)
    return results
