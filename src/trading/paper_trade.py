from __future__ import annotations

from datetime import date

from google.cloud import firestore

from src.agent.models import TradeSignal
from src.cloud.firestore import get_client
import structlog

logger = structlog.get_logger()

INITIAL_BALANCE = 5000.0
_COL_TRADES = "paper_trades"


def _db() -> firestore.Client:
    return get_client()


# ── Write operations ──────────────────────────────────────────────────────────

def open_position(signal: TradeSignal) -> str:
    """
    Create a new paper position in Firestore.
    Document ID: {symbol}_{open_date}. Returns the document ID.
    """
    today = date.today().isoformat()
    doc_id = f"{signal.symbol.replace('/', '_')}_{today}"

    _db().collection(_COL_TRADES).document(doc_id).set({
        "symbol": signal.symbol,
        "market": signal.market,
        "entry": signal.entry,
        "tp": signal.tp,
        "sl": signal.sl,
        "confidence": signal.confidence,
        "timeframe_days": signal.timeframe_days,
        "reasoning_th": signal.reasoning_th,
        "open_date": today,
        "status": "open",
        "current_price": signal.entry,
        "pnl_pct": 0.0,
        "close_date": None,
        "close_price": None,
        "close_reason": None,
    })
    logger.info("Paper position opened", symbol=signal.symbol, entry=signal.entry)
    return doc_id


def update_positions() -> None:
    """Fetch latest price for every open position and update pnl_pct."""
    from src.data import crypto, us_stocks

    for pos in get_open_positions():
        symbol, market = pos["symbol"], pos["market"]
        try:
            df = (
                us_stocks.fetch_ohlcv(symbol, period="5d")
                if market == "us_stock"
                else crypto.fetch_ohlcv(symbol, timeframe="1d", limit=5)
            )
            if df is None or df.empty:
                continue

            current_price = float(df["close"].iloc[-1])
            pnl_pct = (current_price - pos["entry"]) / pos["entry"] * 100

            _db().collection(_COL_TRADES).document(pos["id"]).update({
                "current_price": current_price,
                "pnl_pct": round(pnl_pct, 2),
            })
        except Exception as e:
            logger.warning("Failed to update position", symbol=symbol, error=str(e))


def check_exits() -> list[dict]:
    """
    Close positions whose current price has hit TP or SL.
    Returns list of positions that were closed this run.
    """
    from src.data import crypto, us_stocks

    closed: list[dict] = []

    for pos in get_open_positions():
        symbol, market = pos["symbol"], pos["market"]
        try:
            df = (
                us_stocks.fetch_ohlcv(symbol, period="5d")
                if market == "us_stock"
                else crypto.fetch_ohlcv(symbol, timeframe="1d", limit=5)
            )
            if df is None or df.empty:
                continue

            current_price = float(df["close"].iloc[-1])
            hit_tp = current_price >= pos["tp"]
            hit_sl = current_price <= pos["sl"]

            if not (hit_tp or hit_sl):
                continue

            close_price = pos["tp"] if hit_tp else pos["sl"]
            pnl_pct = round((close_price - pos["entry"]) / pos["entry"] * 100, 2)
            reason = "TP" if hit_tp else "SL"

            _db().collection(_COL_TRADES).document(pos["id"]).update({
                "status": "closed",
                "close_date": date.today().isoformat(),
                "close_price": close_price,
                "pnl_pct": pnl_pct,
                "close_reason": reason,
            })
            logger.info("Paper position closed", symbol=symbol, reason=reason, pnl_pct=pnl_pct)
            closed.append({**pos, "close_price": close_price, "pnl_pct": pnl_pct, "close_reason": reason})

        except Exception as e:
            logger.warning("Failed to check exit", symbol=symbol, error=str(e))

    return closed


# ── Read operations ───────────────────────────────────────────────────────────

def get_open_positions() -> list[dict]:
    """Return all open paper positions."""
    docs = _db().collection(_COL_TRADES).where(filter=firestore.FieldFilter("status", "==", "open")).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def get_history(limit: int = 20) -> list[dict]:
    """Return closed trades, most recent first."""
    docs = (
        _db().collection(_COL_TRADES)
        .where(filter=firestore.FieldFilter("status", "==", "closed"))
        .stream()
    )
    results = [{"id": d.id, **d.to_dict()} for d in docs]
    results.sort(key=lambda x: x.get("close_date") or "", reverse=True)
    return results[:limit]


def get_pnl_summary() -> dict:
    """Return aggregate P&L stats across all trades."""
    all_docs = _db().collection(_COL_TRADES).stream()

    open_count = 0
    closed_pnl: list[float] = []

    for d in all_docs:
        data = d.to_dict()
        if data.get("status") == "open":
            open_count += 1
        elif data.get("pnl_pct") is not None:
            closed_pnl.append(data["pnl_pct"])

    wins = [p for p in closed_pnl if p > 0]
    win_rate = len(wins) / len(closed_pnl) * 100 if closed_pnl else 0.0
    avg_pnl = sum(closed_pnl) / len(closed_pnl) if closed_pnl else 0.0

    return {
        "balance": INITIAL_BALANCE,
        "open_count": open_count,
        "closed_count": len(closed_pnl),
        "win_rate_pct": round(win_rate, 1),
        "total_pnl_pct": round(avg_pnl, 2),
    }
