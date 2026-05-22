import pytest
import pandas as pd
import numpy as np
from src.indicators.technical import add_indicators, score_signal, SignalScore


def make_df(n: int = 60, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame(
        {
            "open": close * 0.999,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, n).astype(float),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


def test_add_indicators_adds_expected_columns():
    df = add_indicators(make_df())
    for col in ["RSI_14", "MACD_12_26_9", "MACDh_12_26_9", "BBU_20_2.0", "BBL_20_2.0",
                "EMA_9", "EMA_21", "SMA_50", "SMA_200"]:
        assert col in df.columns, f"Missing column: {col}"


def test_add_indicators_does_not_mutate_original():
    df = make_df()
    original_cols = list(df.columns)
    add_indicators(df)
    assert list(df.columns) == original_cols


def test_score_signal_returns_signal_score():
    result = score_signal(make_df(), symbol="TEST")
    assert isinstance(result, SignalScore)
    assert result.symbol == "TEST"
    assert 0 <= result.score <= 4
    assert isinstance(result.fired, list)
    assert "close" in result.latest


def test_score_signal_is_signal_property():
    df = make_df()
    result = score_signal(df)
    assert result.is_signal == (result.score >= 3)


def test_score_signal_rsi_fires_on_downtrend():
    """A sustained downtrend should push RSI below 40."""
    n = 60
    close = np.linspace(200, 50, n)   # steep decline
    df = pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close,
         "volume": np.ones(n) * 1e6},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )
    result = score_signal(df, "DOWNTREND")
    assert result.latest["rsi"] is not None
    assert result.latest["rsi"] < 40
    assert any("RSI" in f for f in result.fired)


def test_score_signal_bb_lower_fires():
    """Force close below BB lower band."""
    df = make_df()
    df_ind = add_indicators(df)
    # Set last close well below its BB lower band
    bb_lower = df_ind["BBL_20_2.0"].iloc[-1]
    df.iloc[-1, df.columns.get_loc("close")] = bb_lower * 0.97
    result = score_signal(df, "BB_TEST")
    assert any("BB" in f for f in result.fired)


def test_score_signal_too_short_returns_zero():
    df = make_df(n=1)
    result = score_signal(df, "SHORT")
    assert result.score == 0
