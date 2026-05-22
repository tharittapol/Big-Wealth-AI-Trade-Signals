"""Cloud Run Job entrypoint. Also usable locally via python -m src.cloud.main."""
from __future__ import annotations

import argparse

from dotenv import load_dotenv
load_dotenv()

import structlog

logger = structlog.get_logger()


def _scan(market: str) -> None:
    from src.agent.analyzer import pick_top3
    from src.agent.models import ScanResult
    from src.agent.scanner import scan_crypto, scan_us_stocks
    from src.notifications.telegram import send_daily_summary, send_signal
    from src.trading.paper_trade import open_position
    from datetime import date

    result = ScanResult(scan_date=date.today().isoformat())

    if market in ("us", "both"):
        logger.info("Starting US stock scan")
        candidates = scan_us_stocks()
        signals = pick_top3(candidates, "us_stock")
        result.top3_us = signals
        for s in signals:
            send_signal(s)
            if s.confidence == "high":
                open_position(s)
            else:
                logger.info("Skipping paper position (confidence not high)", symbol=s.symbol, confidence=s.confidence)

    if market in ("crypto", "both"):
        logger.info("Starting crypto scan")
        candidates = scan_crypto()
        signals = pick_top3(candidates, "crypto")
        result.top3_crypto = signals
        for s in signals:
            send_signal(s)
            if s.confidence == "high":
                open_position(s)
            else:
                logger.info("Skipping paper position (confidence not high)", symbol=s.symbol, confidence=s.confidence)

    if result.top3_us or result.top3_crypto:
        send_daily_summary(result)
    logger.info("Scan complete", us_count=len(result.top3_us), crypto_count=len(result.top3_crypto))


def _update_paper() -> None:
    from src.trading.paper_trade import check_exits, update_positions
    from src.notifications.telegram import send_alert

    logger.info("Updating paper positions")
    update_positions()
    closed = check_exits()

    if closed:
        lines = ["📋 Paper positions closed today:"]
        for p in closed:
            sign = "+" if p["pnl_pct"] >= 0 else ""
            lines.append(f"  {p['symbol']} [{p['close_reason']}] {sign}{p['pnl_pct']:.1f}%")
        send_alert("\n".join(lines))

    logger.info("Paper update complete", closed_count=len(closed))


def _tp(symbol: str, entry_date: str, entry_price: float, market: str) -> None:
    from src.agent.tp_advisor import get_tp_advice
    from src.notifications.formatter import format_tp_advice

    advice = get_tp_advice(symbol, entry_date, entry_price, market)
    if advice:
        print(format_tp_advice(advice))
    else:
        print(f"❌ Could not fetch data for {symbol}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Big-wealth scanner job")
    parser.add_argument("--mode", required=True, choices=["scan", "update-paper", "tp"])
    parser.add_argument("--market", choices=["us", "crypto", "both", "us_stock"], default="crypto")
    parser.add_argument("--symbol", help="Symbol for TP advisor")
    parser.add_argument("--entry-date", help="Entry date YYYY-MM-DD for TP advisor")
    parser.add_argument("--entry-price", type=float, help="Entry price for TP advisor")
    args = parser.parse_args()

    # Normalize --market to internal market_type string for TP advisor
    _market_type_map = {"us": "us_stock", "us_stock": "us_stock", "crypto": "crypto", "both": "us_stock"}
    market_type = _market_type_map.get(args.market, "us_stock")

    if args.mode == "scan":
        _scan(args.market)
    elif args.mode == "update-paper":
        _update_paper()
    elif args.mode == "tp":
        if not all([args.symbol, args.entry_date, args.entry_price]):
            parser.error("--mode tp requires --symbol, --entry-date, and --entry-price")
        _tp(args.symbol, args.entry_date, args.entry_price, market_type)


if __name__ == "__main__":
    main()
