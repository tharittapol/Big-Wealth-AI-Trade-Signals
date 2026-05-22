import pandas as pd
import ta
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import BollingerBands
from dataclasses import dataclass, field


@dataclass
class SignalScore:
    symbol: str
    score: int
    fired: list[str] = field(default_factory=list)
    latest: dict = field(default_factory=dict)

    @property
    def is_signal(self) -> bool:
        return self.score >= 3


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI, MACD, Bollinger Bands, EMA(9/21), SMA(50/200) columns to a copy of df."""
    df = df.copy()
    close = df["close"]

    df["RSI_14"] = RSIIndicator(close=close, window=14).rsi()

    macd = MACD(close=close, window_fast=12, window_slow=26, window_sign=9)
    df["MACD_12_26_9"] = macd.macd()
    df["MACDs_12_26_9"] = macd.macd_signal()
    df["MACDh_12_26_9"] = macd.macd_diff()

    bb = BollingerBands(close=close, window=20, window_dev=2)
    df["BBU_20_2.0"] = bb.bollinger_hband()
    df["BBM_20_2.0"] = bb.bollinger_mavg()
    df["BBL_20_2.0"] = bb.bollinger_lband()

    df["EMA_9"] = EMAIndicator(close=close, window=9).ema_indicator()
    df["EMA_21"] = EMAIndicator(close=close, window=21).ema_indicator()
    df["SMA_50"] = SMAIndicator(close=close, window=50).sma_indicator()
    df["SMA_200"] = SMAIndicator(close=close, window=200).sma_indicator()

    return df


def score_signal(df: pd.DataFrame, symbol: str = "", bb_touch_tolerance: float = 0.01) -> SignalScore:
    """
    Score a ticker's last bar against 4 bullish conditions.
    Returns SignalScore with score 0-4 and which indicators fired.
    """
    df = add_indicators(df)
    if len(df) < 2:
        return SignalScore(symbol=symbol, score=0)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    score = 0
    fired: list[str] = []

    # 1. RSI oversold (< 40)
    rsi = last.get("RSI_14")
    if pd.notna(rsi) and rsi < 40:
        score += 1
        fired.append(f"RSI={rsi:.1f} (oversold <40)")

    # 2. MACD histogram bullish zero-cross
    hist_now = last.get("MACDh_12_26_9")
    hist_prev = prev.get("MACDh_12_26_9")
    if pd.notna(hist_now) and pd.notna(hist_prev) and hist_now > 0 and hist_prev <= 0:
        score += 1
        fired.append(f"MACD bullish cross (hist={hist_now:.4f})")

    # 3. Bollinger Bands — close at or below lower band (+tolerance buffer)
    bb_lower = last.get("BBL_20_2.0")
    close = last.get("close")
    if pd.notna(bb_lower) and pd.notna(close) and close <= bb_lower * (1 + bb_touch_tolerance):
        score += 1
        fired.append(f"BB lower touch (close={close:.4f}, lower={bb_lower:.4f})")

    # 4. EMA 9 crossed above EMA 21
    ema9_now = last.get("EMA_9")
    ema21_now = last.get("EMA_21")
    ema9_prev = prev.get("EMA_9")
    ema21_prev = prev.get("EMA_21")
    if all(pd.notna(v) for v in [ema9_now, ema21_now, ema9_prev, ema21_prev]):
        if ema9_now > ema21_now and ema9_prev <= ema21_prev:
            score += 1
            fired.append(f"EMA9 crossed above EMA21")

    def _r(v, ndigits: int = 4):
        return round(float(v), ndigits) if pd.notna(v) else None

    latest = {
        "close": _r(close),
        "rsi": _r(rsi, 2),
        "macd_hist": _r(hist_now),
        "bb_lower": _r(bb_lower),
        "bb_upper": _r(last.get("BBU_20_2.0")),
        "ema9": _r(ema9_now),
        "ema21": _r(ema21_now),
        "sma50": _r(last.get("SMA_50")),
        "sma200": _r(last.get("SMA_200")),
    }

    return SignalScore(symbol=symbol, score=score, fired=fired, latest=latest)
