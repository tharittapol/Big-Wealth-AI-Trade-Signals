import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from src.agent.models import TradeSignal
from src.trading.paper_trade import open_position, get_open_positions, get_pnl_summary

# เปิด paper position
signal = TradeSignal(
    symbol="BTC/USDT", market="crypto",
    entry=60000.0, tp=68000.0, sl=56000.0,
    confidence="high", timeframe_days=3,
    reasoning_th="Test paper trade",
)
doc_id = open_position(signal)
print(f"✅ Opened position: {doc_id}")

# ดู open positions
positions = get_open_positions()
print(f"Open positions: {len(positions)}")
for p in positions:
    print(f"  {p['symbol']} — entry: {p['entry']}")

# ดู P&L summary
summary = get_pnl_summary()
print(f"P&L Summary: {summary}")
