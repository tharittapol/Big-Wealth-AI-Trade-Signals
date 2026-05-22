"""Quick smoke-test for data fetching and indicator scoring."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.us_stocks import fetch_ohlcv, fetch_news
from src.data.crypto import fetch_ohlcv as crypto_ohlcv, fetch_top_volume_pairs
from src.indicators.technical import score_signal


def main():
    # US Stock
    print("=== US Stock: AAPL ===")
    df = fetch_ohlcv("AAPL")
    if df is not None:
        print(f"  Rows: {len(df)}, Last close: ${df['close'].iloc[-1]:.2f}")
        news = fetch_news("AAPL", max_items=3)
        print(f"  News: {[n['title'][:60] for n in news]}")
        sig = score_signal(df, "AAPL")
        print(f"  Signal score: {sig.score}/4  |  Fired: {sig.fired}")
    else:
        print("  ❌ No data returned")

    # Crypto
    print("\n=== Crypto: Top 5 pairs by volume ===")
    pairs = fetch_top_volume_pairs(limit=5)
    print(f"  Pairs: {pairs}")

    print("\n=== Crypto: BTC/USDT ===")
    df_btc = crypto_ohlcv("BTC/USDT")
    if df_btc is not None:
        print(f"  Rows: {len(df_btc)}, Last close: {df_btc['close'].iloc[-1]:,.0f} USDT")
        sig_btc = score_signal(df_btc, "BTC/USDT")
        print(f"  Signal score: {sig_btc.score}/4  |  Fired: {sig_btc.fired}")
    else:
        print("  ❌ No data returned")


if __name__ == "__main__":
    main()
