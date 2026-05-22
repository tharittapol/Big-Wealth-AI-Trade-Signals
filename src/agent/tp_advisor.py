from __future__ import annotations

import json
import re

import pandas as pd

from src.agent.models import TPAdvice, TPLevel
from src.cloud.claude_cli import run_claude
from src.data import crypto, us_stocks
from src.indicators.technical import add_indicators
import structlog

logger = structlog.get_logger()

_SYSTEM_TP = """คุณคือที่ปรึกษาการเทรดมืออาชีพ หน้าที่คือแนะนำจุด Take Profit สำหรับ position ที่ถือไว้

วิเคราะห์:
1. ราคาปัจจุบัน vs ราคาที่ซื้อ — P&L ปัจจุบัน
2. แนวต้านสำคัญจาก indicator และ price action (BB upper, EMA, swing highs)
3. Momentum ปัจจุบัน — ยังแข็งแกร่งหรือเริ่มอ่อน
4. แนะนำ 1-3 จุด TP และ action ที่ควรทำ

ตอบเป็นภาษาไทย"""

_SYSTEM_NEWS_SEARCH = (
    "คุณคือผู้ช่วยค้นหาข่าวการเงิน ตอบด้วย JSON เท่านั้น ห้ามมีข้อความอื่น"
)

_JSON_INSTRUCTION = (
    '\n\nตอบด้วย JSON เท่านั้น (ห้ามมีข้อความอื่น) ในรูปแบบนี้:\n'
    '{"tp_levels": [{"price": 0.00, "rationale_th": "เหตุผล"}], '
    '"action": "hold", '
    '"reasoning_th": "เหตุผลรวม"}'
    '\n(action ต้องเป็น hold | take_partial_profit | exit เท่านั้น)'
)


def _fetch_us_news(symbol: str, max_items: int = 5) -> list[dict]:
    """Fetch recent US stock news via yfinance (single call, buffered for analysis)."""
    try:
        return us_stocks.fetch_news(symbol, max_items=max_items)
    except Exception as exc:
        logger.warning("yfinance news fetch failed", symbol=symbol, error=str(exc))
        return []


def _fetch_crypto_news(symbol: str) -> list[dict]:
    """Fetch recent crypto news via Claude web search (single call, buffered for analysis)."""
    prompt = (
        f"ค้นหาข่าวล่าสุดเกี่ยวกับ {symbol} ในช่วง 2 สัปดาห์ที่ผ่านมา\n"
        f"ต้องการข่าวสำคัญที่ส่งผลต่อราคา: upgrade, listing, partnership, regulatory\n\n"
        f'{{"news": [{{"title": "สรุปข่าว", "catalyst": "ประเภท"}}]}}'
    )
    try:
        response = run_claude(
            prompt,
            system_prompt=_SYSTEM_NEWS_SEARCH,
            model="opus",
            enable_web_search=True,
            timeout=180,
        )
        text = re.sub(r"```json\s*|```\s*", "", response)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("news", [])
    except Exception as exc:
        logger.warning("Crypto news fetch failed", symbol=symbol, error=str(exc))
    return []


def get_tp_advice(
    symbol: str,
    entry_date: str,
    entry_price: float,
    market: str = "us_stock",
) -> TPAdvice | None:
    """
    Ask Claude to recommend TP levels for an open position.
    Returns TPAdvice or None if data cannot be fetched or CLI fails.

    News is fetched once and buffered before analysis — no re-search during prompt evaluation.
    """
    df = _fetch_since_entry(symbol, entry_date, market)
    if df is None:
        return None

    df = add_indicators(df)
    current_price = float(df["close"].iloc[-1])
    pnl_pct = (current_price - entry_price) / entry_price * 100

    # Fetch news once and buffer for analysis (no re-search)
    if market == "us_stock":
        news_items = _fetch_us_news(symbol)
    else:
        news_items = _fetch_crypto_news(symbol)

    prompt = _build_prompt(symbol, market, entry_date, entry_price, current_price, pnl_pct, df, news_items)

    try:
        response = run_claude(prompt + _JSON_INSTRUCTION, system_prompt=_SYSTEM_TP, model="opus")
        return _parse_tp_response(response, symbol, market, entry_price, current_price, pnl_pct)
    except Exception as e:
        logger.error("TP advisor CLI call failed", symbol=symbol, error=str(e))
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_since_entry(symbol: str, entry_date: str, market: str) -> pd.DataFrame | None:
    df = (
        us_stocks.fetch_ohlcv(symbol, period="90d")
        if market == "us_stock"
        else crypto.fetch_ohlcv(symbol, timeframe="1d", limit=90)
    )
    if df is None or df.empty:
        logger.error("Cannot fetch data for TP advice", symbol=symbol)
        return None
    try:
        filtered = df[df.index >= pd.Timestamp(entry_date)]
        return filtered if len(filtered) >= 5 else df
    except Exception:
        return df


def _build_prompt(
    symbol: str,
    market: str,
    entry_date: str,
    entry_price: float,
    current_price: float,
    pnl_pct: float,
    df: pd.DataFrame,
    news_items: list[dict],
) -> str:
    last = df.iloc[-1]

    def _g(key: str, digits: int = 2) -> str:
        v = last.get(key)
        return f"{float(v):.{digits}f}" if pd.notna(v) else "N/A"

    price_table = df.tail(10)[["open", "high", "low", "close", "volume"]].to_string()

    if news_items:
        news_lines = "\n".join(
            f"  • {item.get('title', '')} [{item.get('catalyst', '')}]"
            for item in news_items[:5]
        )
        news_section = f"\nข่าวล่าสุด (buffered, no re-search):\n{news_lines}"
    else:
        news_section = "\nข่าว: ไม่มีข้อมูลข่าว"

    return (
        f"Symbol: {symbol} ({market})\n"
        f"Entry date: {entry_date}  |  Entry price: {entry_price}\n"
        f"Current price: {current_price:.4f}  |  P&L: {pnl_pct:+.2f}%\n\n"
        f"Indicators ปัจจุบัน:\n"
        f"RSI: {_g('RSI_14')}  |  MACD hist: {_g('MACDh_12_26_9', 4)}\n"
        f"BB upper: {_g('BBU_20_2.0', 4)}  |  lower: {_g('BBL_20_2.0', 4)}\n"
        f"EMA9: {_g('EMA_9', 4)}  |  EMA21: {_g('EMA_21', 4)}\n\n"
        f"Price data 10 วันล่าสุด:\n{price_table}"
        f"{news_section}\n\n"
        f"แนะนำ TP levels และ action ที่ควรทำ"
    )


def _parse_tp_response(
    text: str,
    symbol: str,
    market: str,
    entry_price: float,
    current_price: float,
    pnl_pct: float,
) -> TPAdvice | None:
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        logger.warning("No JSON found in TP response", symbol=symbol)
        return None
    try:
        data = json.loads(match.group())
        tp_levels = [
            TPLevel(price=float(lv["price"]), rationale_th=lv["rationale_th"])
            for lv in data.get("tp_levels", [])
        ]
        return TPAdvice(
            symbol=symbol,
            market=market,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl_pct=round(pnl_pct, 2),
            tp_levels=tp_levels,
            action=data["action"],
            reasoning_th=data["reasoning_th"],
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Failed to parse TP response JSON", symbol=symbol, error=str(e))
        return None
