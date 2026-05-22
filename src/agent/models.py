from __future__ import annotations
from pydantic import BaseModel, computed_field
from typing import Any


class CandidateTicker(BaseModel):
    symbol: str
    market: str  # "us_stock" | "crypto"
    current_price: float
    indicators: dict[str, Any]  # score, fired, rsi, macd_hist, ema9, ema21, bb_lower, bb_upper, ...
    news: list[dict[str, str]] = []  # [{title, publisher, link, published_utc}]
    ohlcv_recent: list[dict[str, Any]] = []  # last 20 OHLCV rows as plain dicts


class TradeSignal(BaseModel):
    symbol: str
    market: str  # "us_stock" | "crypto"
    entry: float
    tp: float
    sl: float
    confidence: str  # "high" | "medium" | "low"
    timeframe_days: int  # 1–5
    reasoning_th: str  # Thai-language reasoning

    @computed_field
    @property
    def tp_pct(self) -> float:
        return round((self.tp - self.entry) / self.entry * 100, 2) if self.entry > 0 else 0.0

    @computed_field
    @property
    def sl_pct(self) -> float:
        return round((self.sl - self.entry) / self.entry * 100, 2) if self.entry > 0 else 0.0


class ScanResult(BaseModel):
    scan_date: str
    top3_us: list[TradeSignal] = []
    top3_crypto: list[TradeSignal] = []


class TPLevel(BaseModel):
    price: float
    rationale_th: str


class TPAdvice(BaseModel):
    symbol: str
    market: str
    entry_price: float
    current_price: float
    unrealized_pnl_pct: float
    tp_levels: list[TPLevel]
    action: str  # "hold" | "take_partial_profit" | "exit"
    reasoning_th: str
