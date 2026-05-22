from __future__ import annotations

from src.agent.models import ScanResult, TPAdvice, TradeSignal

_CONFIDENCE_TH = {"high": "สูง", "medium": "ปานกลาง", "low": "ต่ำ"}
_ACTION_LABEL = {
    "hold": "🟢 Hold ต่อ",
    "take_partial_profit": "🟡 ขายบางส่วน",
    "exit": "🔴 Exit ทั้งหมด",
}


def _fmt_price(price: float, market: str) -> str:
    if market == "us_stock":
        return f"${price:.2f}"
    return f"{price:,.4f}" if price < 1 else f"{price:,.2f}"


def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


def format_signal_card(signal: TradeSignal) -> str:
    """Format a single trade signal as an HTML Telegram message."""
    market_label = "US Stock" if signal.market == "us_stock" else "Crypto"
    market_tag = "#USStock" if signal.market == "us_stock" else "#Crypto"
    confidence_th = _CONFIDENCE_TH.get(signal.confidence, signal.confidence)
    entry = _fmt_price(signal.entry, signal.market)
    tp = _fmt_price(signal.tp, signal.market)
    sl = _fmt_price(signal.sl, signal.market)

    return (
        f"🔔 <b>BUY SIGNAL — {signal.symbol}</b> ({market_label})\n\n"
        f"Entry:      {entry}\n"
        f"TP:         {tp} ({_sign(signal.tp_pct)}{signal.tp_pct:.1f}%)\n"
        f"SL:         {sl} ({_sign(signal.sl_pct)}{signal.sl_pct:.1f}%)\n"
        f"Timeframe:  {signal.timeframe_days} วัน\n"
        f"Confidence: {confidence_th}\n\n"
        f"🤖 <b>เหตุผล:</b>\n"
        f"{signal.reasoning_th}\n\n"
        f"#{signal.symbol} {market_tag} #BuySignal"
    )


def format_daily_summary(result: ScanResult) -> str:
    """Format a daily scan summary (US top 3 + Crypto top 3)."""
    lines = [f"📊 <b>Daily Scan — {result.scan_date}</b>\n"]

    if result.top3_us:
        lines.append("🇺🇸 <b>US Stocks</b>")
        for i, s in enumerate(result.top3_us, 1):
            lines.append(
                f"{i}. <b>{s.symbol}</b> — Entry: ${s.entry:.2f} | "
                f"TP: {_sign(s.tp_pct)}{s.tp_pct:.1f}% | SL: {s.sl_pct:.1f}%"
            )
        lines.append("")

    if result.top3_crypto:
        lines.append("₿ <b>Crypto</b>")
        for i, s in enumerate(result.top3_crypto, 1):
            entry = _fmt_price(s.entry, "crypto")
            lines.append(
                f"{i}. <b>{s.symbol}</b> — Entry: {entry} | "
                f"TP: {_sign(s.tp_pct)}{s.tp_pct:.1f}% | SL: {s.sl_pct:.1f}%"
            )

    return "\n".join(lines)


def format_tp_advice(advice: TPAdvice) -> str:
    """Format TP advisor response."""
    pnl = advice.unrealized_pnl_pct
    action_label = _ACTION_LABEL.get(advice.action, advice.action)

    lines = [
        f"📈 <b>TP Advisor — {advice.symbol}</b>\n",
        f"Entry: {advice.entry_price}  |  ปัจจุบัน: {advice.current_price}",
        f"P&amp;L: {_sign(pnl)}{pnl:.2f}%\n",
        f"Action: {action_label}\n",
        "🎯 <b>TP Targets:</b>",
    ]
    for i, lv in enumerate(advice.tp_levels, 1):
        lines.append(f"  {i}. {lv.price} — {lv.rationale_th}")
    lines.append(f"\n🤖 {advice.reasoning_th}")
    return "\n".join(lines)


def format_positions(positions: list[dict]) -> str:
    """Format open paper positions list."""
    if not positions:
        return "📭 ไม่มี open positions ในขณะนี้"

    lines = ["📋 <b>Open Positions</b>\n"]
    for p in positions:
        pnl = p.get("pnl_pct") or 0.0
        emoji = "🟢" if pnl >= 0 else "🔴"
        entry = _fmt_price(p["entry"], p.get("market", "us_stock"))
        lines.append(
            f"{emoji} <b>{p['symbol']}</b>\n"
            f"   Entry: {entry}  |  P&amp;L: {_sign(pnl)}{pnl:.2f}%\n"
            f"   TP: {p['tp']}  |  SL: {p['sl']}"
        )
    return "\n".join(lines)


def format_pnl_summary(summary: dict) -> str:
    """Format overall P&L summary."""
    pnl = summary.get("total_pnl_pct", 0.0)
    return (
        f"💰 <b>P&amp;L Summary</b>\n\n"
        f"Balance:        ${summary.get('balance', 0):,.2f}\n"
        f"Open positions: {summary.get('open_count', 0)}\n"
        f"Closed trades:  {summary.get('closed_count', 0)}\n"
        f"Win rate:       {summary.get('win_rate_pct', 0.0):.1f}%\n"
        f"Total P&amp;L:  {_sign(pnl)}{pnl:.2f}%"
    )


def format_closed_position(pos: dict) -> str:
    """Format a single closed position for the history list."""
    pnl = pos.get("pnl_pct", 0.0)
    emoji = "✅" if pnl >= 0 else "❌"
    reason = pos.get("close_reason", "")
    return f"{emoji} <b>{pos['symbol']}</b> [{reason}] — P&amp;L: {_sign(pnl)}{pnl:.2f}%"
