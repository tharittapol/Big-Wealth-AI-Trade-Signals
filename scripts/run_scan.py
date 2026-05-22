"""Run a manual scan locally and print results (does not send to Telegram)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import argparse
from src.agent.scanner import scan_crypto, scan_us_stocks
from src.agent.analyzer import pick_top3


def main():
    parser = argparse.ArgumentParser(description="Run a local scan")
    parser.add_argument("--market", choices=["us", "crypto", "both"], default="crypto")
    args = parser.parse_args()

    if args.market in ("crypto", "both"):
        print("=== Scanning Crypto ===")
        candidates = scan_crypto(min_score=1)
        print(f"Candidates: {len(candidates)}")
        for c in candidates[:8]:
            print(f"  {c.symbol:15s} score={c.indicators['score']}/4  price={c.current_price:.4f}")

        if candidates:
            print("\n--- Asking Claude to pick top 3 ---")
            signals = pick_top3(candidates, "crypto")
            for s in signals:
                print(f"\n  {s.symbol}")
                print(f"  Entry: {s.entry}  TP: {s.tp} (+{s.tp_pct:.1f}%)  SL: {s.sl} ({s.sl_pct:.1f}%)")
                print(f"  เหตุผล: {s.reasoning_th}")

    if args.market in ("us", "both"):
        print("\n=== Scanning US Stocks ===")
        candidates = scan_us_stocks()
        print(f"Candidates: {len(candidates)}")
        for c in candidates[:8]:
            print(f"  {c.symbol:10s} score={c.indicators['score']}/4  price=${c.current_price:.2f}")

        if candidates:
            print("\n--- Asking Claude to pick top 3 ---")
            signals = pick_top3(candidates, "us_stock")
            for s in signals:
                print(f"\n  {s.symbol}")
                print(f"  Entry: ${s.entry:.2f}  TP: ${s.tp:.2f} (+{s.tp_pct:.1f}%)  SL: ${s.sl:.2f} ({s.sl_pct:.1f}%)")
                print(f"  เหตุผล: {s.reasoning_th}")


if __name__ == "__main__":
    main()
