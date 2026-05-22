from __future__ import annotations

import asyncio
import os

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from src.agent.models import ScanResult, TradeSignal
from src.notifications.formatter import (
    format_closed_position,
    format_daily_summary,
    format_positions,
    format_pnl_summary,
    format_signal_card,
    format_tp_advice,
)
import structlog

logger = structlog.get_logger()


def _bot() -> Bot:
    return Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])


def _channel_id() -> str:
    return os.environ["TELEGRAM_CHANNEL_ID"]


# ── Push functions (called by scanner job) ────────────────────────────────────

def send_signal(signal: TradeSignal) -> None:
    """Post a trade signal card to the broadcast channel."""
    text = format_signal_card(signal)
    asyncio.run(_bot().send_message(chat_id=_channel_id(), text=text, parse_mode=ParseMode.HTML))
    logger.info("Signal sent to channel", symbol=signal.symbol)


def send_daily_summary(result: ScanResult) -> None:
    """Post a daily scan summary to the broadcast channel."""
    text = format_daily_summary(result)
    asyncio.run(_bot().send_message(chat_id=_channel_id(), text=text, parse_mode=ParseMode.HTML))
    logger.info("Daily summary sent", scan_date=result.scan_date)


def send_alert(message: str) -> None:
    """Post a plain-text alert (e.g. job failure) to the channel."""
    asyncio.run(_bot().send_message(chat_id=_channel_id(), text=message))


# ── Command handlers (private chat / group) ───────────────────────────────────

async def _cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from src.trading.paper_trade import get_open_positions
    positions = get_open_positions()
    await update.message.reply_text(format_positions(positions), parse_mode=ParseMode.HTML)


async def _cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from src.trading.paper_trade import get_pnl_summary
    summary = get_pnl_summary()
    await update.message.reply_text(format_pnl_summary(summary), parse_mode=ParseMode.HTML)


async def _cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from src.trading.paper_trade import get_history
    history = get_history(limit=10)
    if not history:
        await update.message.reply_text("📭 ยังไม่มีประวัติการเทรด")
        return
    lines = ["📜 <b>Trade History (10 รายการล่าสุด)</b>\n"]
    lines.extend(format_closed_position(h) for h in history)
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def _cmd_tp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /tp SYMBOL YYYY-MM-DD PRICE [us_stock|crypto]
    Example: /tp BTCUSDT 2026-05-10 62000 crypto
    """
    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(
            "❌ Format: <code>/tp SYMBOL YYYY-MM-DD PRICE [us_stock|crypto]</code>\n"
            "Example: <code>/tp SOFI 2026-05-10 12.50 us_stock</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    symbol = args[0].upper()
    entry_date = args[1]
    try:
        entry_price = float(args[2])
    except ValueError:
        await update.message.reply_text("❌ PRICE ต้องเป็นตัวเลข เช่น 12.50 หรือ 62000")
        return

    market = args[3] if len(args) > 3 else "us_stock"
    if market not in ("us_stock", "crypto"):
        await update.message.reply_text("❌ market ต้องเป็น us_stock หรือ crypto")
        return

    await update.message.reply_text(f"🔍 กำลังวิเคราะห์ {symbol}...")

    from src.agent.tp_advisor import get_tp_advice
    advice = get_tp_advice(symbol, entry_date, entry_price, market)
    if advice is None:
        await update.message.reply_text(f"❌ ไม่สามารถวิเคราะห์ {symbol} ได้ในขณะนี้")
        return

    await update.message.reply_text(format_tp_advice(advice), parse_mode=ParseMode.HTML)


# ── Bot runner ────────────────────────────────────────────────────────────────

def _build_app() -> Application:
    app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("positions", _cmd_positions))
    app.add_handler(CommandHandler("pnl", _cmd_pnl))
    app.add_handler(CommandHandler("history", _cmd_history))
    app.add_handler(CommandHandler("tp", _cmd_tp))
    return app


def run_bot() -> None:
    """Start the Telegram bot in polling mode (local dev only)."""
    app = _build_app()
    logger.info("Telegram bot started (polling mode)...")
    app.run_polling()


def run_bot_webhook(webhook_url: str, port: int = 8080) -> None:
    """Start the Telegram bot in webhook mode (Cloud Run Service).

    Telegram pushes updates to webhook_url; the bot listens on 0.0.0.0:port.
    Cloud Run handles TLS termination so the bot itself speaks plain HTTP.
    """
    app = _build_app()
    logger.info("Telegram bot started (webhook mode)", webhook_url=webhook_url, port=port)
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url,
    )
