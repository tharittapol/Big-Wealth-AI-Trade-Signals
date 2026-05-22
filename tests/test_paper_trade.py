import pytest
from unittest.mock import MagicMock, patch, call
from src.agent.models import TradeSignal
from src.trading import paper_trade


def _make_signal(**kwargs) -> TradeSignal:
    defaults = dict(
        symbol="SOFI", market="us_stock",
        entry=10.0, tp=12.5, sl=9.0,
        confidence="high", timeframe_days=3,
        reasoning_th="RSI oversold MACD cross ขึ้น",
    )
    return TradeSignal(**{**defaults, **kwargs})


def _mock_db():
    """Build a mock Firestore client with chainable collection/document/query methods."""
    db = MagicMock()
    doc_ref = MagicMock()
    col_ref = MagicMock()
    col_ref.document.return_value = doc_ref
    col_ref.where.return_value = col_ref
    col_ref.order_by.return_value = col_ref
    col_ref.limit.return_value = col_ref
    col_ref.stream.return_value = iter([])
    db.collection.return_value = col_ref
    return db, col_ref, doc_ref


# ── open_position ──────────────────────────────────────────────────────────────

def test_open_position_calls_set_with_correct_fields():
    db, col_ref, doc_ref = _mock_db()
    with patch("src.trading.paper_trade._db", return_value=db):
        doc_id = paper_trade.open_position(_make_signal())

    doc_ref.set.assert_called_once()
    data = doc_ref.set.call_args[0][0]
    assert data["symbol"] == "SOFI"
    assert data["entry"] == 10.0
    assert data["tp"] == 12.5
    assert data["sl"] == 9.0
    assert data["status"] == "open"
    assert data["market"] == "us_stock"


def test_open_position_returns_doc_id_with_symbol_and_date():
    db, _, _ = _mock_db()
    with patch("src.trading.paper_trade._db", return_value=db):
        doc_id = paper_trade.open_position(_make_signal())
    assert doc_id.startswith("SOFI_")


# ── get_open_positions ────────────────────────────────────────────────────────

def test_get_open_positions_returns_list():
    db, col_ref, _ = _mock_db()
    mock_doc = MagicMock()
    mock_doc.id = "SOFI_2026-05-18"
    mock_doc.to_dict.return_value = {"symbol": "SOFI", "status": "open", "entry": 10.0, "tp": 12.5, "sl": 9.0}
    col_ref.stream.return_value = iter([mock_doc])

    with patch("src.trading.paper_trade._db", return_value=db):
        positions = paper_trade.get_open_positions()

    assert len(positions) == 1
    assert positions[0]["symbol"] == "SOFI"
    assert positions[0]["id"] == "SOFI_2026-05-18"


def test_get_open_positions_returns_empty_when_none():
    db, _, _ = _mock_db()
    with patch("src.trading.paper_trade._db", return_value=db):
        positions = paper_trade.get_open_positions()
    assert positions == []


# ── check_exits ───────────────────────────────────────────────────────────────

def _open_pos(symbol="SOFI", entry=10.0, tp=12.5, sl=9.0):
    return {"id": f"{symbol}_2026-05-18", "symbol": symbol, "market": "us_stock",
            "entry": entry, "tp": tp, "sl": sl, "status": "open"}


def test_check_exits_closes_on_tp_hit():
    import pandas as pd, numpy as np
    close = np.array([13.0] * 5)   # above tp=12.5
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": np.ones(5)},
                      index=pd.date_range("2026-05-14", periods=5, freq="D"))
    db, col_ref, doc_ref = _mock_db()

    with patch("src.trading.paper_trade.get_open_positions", return_value=[_open_pos()]), \
         patch("src.data.us_stocks.fetch_ohlcv", return_value=df), \
         patch("src.trading.paper_trade._db", return_value=db):
        closed = paper_trade.check_exits()

    assert len(closed) == 1
    assert closed[0]["close_reason"] == "TP"
    assert closed[0]["pnl_pct"] > 0


def test_check_exits_closes_on_sl_hit():
    import pandas as pd, numpy as np
    close = np.array([8.5] * 5)   # below sl=9.0
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": np.ones(5)},
                      index=pd.date_range("2026-05-14", periods=5, freq="D"))
    db, _, _ = _mock_db()

    with patch("src.trading.paper_trade.get_open_positions", return_value=[_open_pos()]), \
         patch("src.data.us_stocks.fetch_ohlcv", return_value=df), \
         patch("src.trading.paper_trade._db", return_value=db):
        closed = paper_trade.check_exits()

    assert len(closed) == 1
    assert closed[0]["close_reason"] == "SL"
    assert closed[0]["pnl_pct"] < 0


def test_check_exits_no_action_when_price_in_range():
    import pandas as pd, numpy as np
    close = np.array([11.0] * 5)   # between sl=9 and tp=12.5
    df = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": np.ones(5)},
                      index=pd.date_range("2026-05-14", periods=5, freq="D"))

    with patch("src.trading.paper_trade.get_open_positions", return_value=[_open_pos()]), \
         patch("src.data.us_stocks.fetch_ohlcv", return_value=df), \
         patch("src.trading.paper_trade._db", return_value=MagicMock()):
        closed = paper_trade.check_exits()

    assert closed == []


# ── get_pnl_summary ───────────────────────────────────────────────────────────

def test_get_pnl_summary_win_rate():
    db, col_ref, _ = _mock_db()
    docs = []
    for pnl, status in [(10.0, "closed"), (-5.0, "closed"), (8.0, "closed"), (0, "open")]:
        m = MagicMock()
        m.to_dict.return_value = {"status": status, "pnl_pct": pnl if status == "closed" else None}
        docs.append(m)
    col_ref.stream.return_value = iter(docs)

    with patch("src.trading.paper_trade._db", return_value=db):
        summary = paper_trade.get_pnl_summary()

    assert summary["closed_count"] == 3
    assert summary["open_count"] == 1
    assert summary["win_rate_pct"] == pytest.approx(66.7, rel=0.01)
    assert summary["balance"] == paper_trade.INITIAL_BALANCE


def test_get_pnl_summary_empty():
    db, _, _ = _mock_db()
    with patch("src.trading.paper_trade._db", return_value=db):
        summary = paper_trade.get_pnl_summary()
    assert summary["win_rate_pct"] == 0.0
    assert summary["closed_count"] == 0
