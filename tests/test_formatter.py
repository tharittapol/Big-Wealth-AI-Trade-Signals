import pytest
from src.agent.models import ScanResult, TPAdvice, TPLevel, TradeSignal
from src.notifications.formatter import (
    format_closed_position,
    format_daily_summary,
    format_positions,
    format_pnl_summary,
    format_signal_card,
    format_tp_advice,
)


def _us_signal(**kwargs) -> TradeSignal:
    defaults = dict(
        symbol="SOFI", market="us_stock",
        entry=10.0, tp=12.5, sl=9.0,
        confidence="high", timeframe_days=3,
        reasoning_th="SOFI RSI oversold ราคาใกล้แนวรับ MACD กำลัง cross ขึ้น",
    )
    return TradeSignal(**{**defaults, **kwargs})


def _crypto_signal(**kwargs) -> TradeSignal:
    defaults = dict(
        symbol="BTC/USDT", market="crypto",
        entry=60000.0, tp=68000.0, sl=56000.0,
        confidence="medium", timeframe_days=5,
        reasoning_th="BTC ทดสอบแนวรับ EMA21 MACD histogram กลับมาเป็นบวก",
    )
    return TradeSignal(**{**defaults, **kwargs})


# ── format_signal_card ────────────────────────────────────────────────────────

def test_signal_card_contains_symbol():
    card = format_signal_card(_us_signal())
    assert "SOFI" in card


def test_signal_card_contains_prices():
    card = format_signal_card(_us_signal())
    assert "$10.00" in card   # entry
    assert "$12.50" in card   # tp
    assert "$9.00" in card    # sl


def test_signal_card_contains_pct_change():
    card = format_signal_card(_us_signal())
    assert "+25.0%" in card   # tp_pct = (12.5-10)/10*100
    assert "-10.0%" in card   # sl_pct = (9-10)/10*100


def test_signal_card_has_thai_reasoning():
    card = format_signal_card(_us_signal())
    assert "แนวรับ" in card


def test_signal_card_has_hashtags():
    card = format_signal_card(_us_signal())
    assert "#SOFI" in card
    assert "#USStock" in card


def test_signal_card_crypto_format():
    card = format_signal_card(_crypto_signal())
    assert "BTC/USDT" in card
    assert "#Crypto" in card
    assert "60,000.00" in card


def test_signal_card_confidence_in_thai():
    card = format_signal_card(_us_signal(confidence="high"))
    assert "สูง" in card
    card2 = format_signal_card(_us_signal(confidence="medium"))
    assert "ปานกลาง" in card2


# ── format_daily_summary ──────────────────────────────────────────────────────

def test_daily_summary_contains_both_markets():
    result = ScanResult(
        scan_date="2026-05-18",
        top3_us=[_us_signal()],
        top3_crypto=[_crypto_signal()],
    )
    summary = format_daily_summary(result)
    assert "US Stocks" in summary
    assert "Crypto" in summary
    assert "SOFI" in summary
    assert "BTC/USDT" in summary


def test_daily_summary_empty_markets():
    result = ScanResult(scan_date="2026-05-18", top3_us=[], top3_crypto=[])
    summary = format_daily_summary(result)
    assert "2026-05-18" in summary


def test_daily_summary_shows_tp_pct():
    result = ScanResult(scan_date="2026-05-18", top3_us=[_us_signal()], top3_crypto=[])
    summary = format_daily_summary(result)
    assert "+25.0%" in summary


# ── format_tp_advice ───────────────────────────────────────────────────────────

def _make_advice(**kwargs) -> TPAdvice:
    defaults = dict(
        symbol="AAPL", market="us_stock",
        entry_price=48.0, current_price=52.0,
        unrealized_pnl_pct=8.33,
        tp_levels=[
            TPLevel(price=55.0, rationale_th="แนวต้าน BB upper"),
            TPLevel(price=58.0, rationale_th="แนวต้าน swing high"),
        ],
        action="hold",
        reasoning_th="ราคายังวิ่งขึ้นต่อได้ momentum ดี",
    )
    return TPAdvice(**{**defaults, **kwargs})


def test_tp_advice_contains_symbol():
    text = format_tp_advice(_make_advice())
    assert "AAPL" in text


def test_tp_advice_shows_pnl():
    text = format_tp_advice(_make_advice())
    assert "+8.33%" in text


def test_tp_advice_shows_action_in_thai():
    text = format_tp_advice(_make_advice(action="hold"))
    assert "Hold" in text
    text2 = format_tp_advice(_make_advice(action="exit"))
    assert "Exit" in text2


def test_tp_advice_lists_tp_levels():
    text = format_tp_advice(_make_advice())
    assert "55.0" in text
    assert "58.0" in text
    assert "BB upper" in text


# ── format_positions ──────────────────────────────────────────────────────────

def test_positions_empty():
    text = format_positions([])
    assert "ไม่มี" in text


def test_positions_shows_symbol_and_pnl():
    positions = [{"symbol": "SOFI", "market": "us_stock", "entry": 10.0, "tp": 12.5, "sl": 9.0, "pnl_pct": 5.5}]
    text = format_positions(positions)
    assert "SOFI" in text
    assert "+5.50%" in text


def test_positions_red_emoji_for_loss():
    positions = [{"symbol": "AAL", "market": "us_stock", "entry": 15.0, "tp": 18.0, "sl": 13.0, "pnl_pct": -3.2}]
    text = format_positions(positions)
    assert "🔴" in text


# ── format_pnl_summary ────────────────────────────────────────────────────────

def test_pnl_summary_shows_balance():
    text = format_pnl_summary({"balance": 5000, "open_count": 2, "closed_count": 5, "win_rate_pct": 60.0, "total_pnl_pct": 8.5})
    assert "$5,000.00" in text
    assert "60.0%" in text
    assert "+8.50%" in text


# ── format_closed_position ────────────────────────────────────────────────────

def test_closed_position_win():
    text = format_closed_position({"symbol": "SOFI", "pnl_pct": 12.0, "close_reason": "TP"})
    assert "✅" in text
    assert "+12.00%" in text


def test_closed_position_loss():
    text = format_closed_position({"symbol": "AAL", "pnl_pct": -5.0, "close_reason": "SL"})
    assert "❌" in text
    assert "-5.00%" in text
