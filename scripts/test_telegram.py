"""Send a test signal to verify Telegram bot + channel connection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.agent.models import TradeSignal
from src.notifications.telegram import send_signal


def main():
    signal = TradeSignal(
        symbol="TEST",
        market="crypto",
        entry=60000.0,
        tp=68000.0,
        sl=56000.0,
        confidence="high",
        timeframe_days=3,
        reasoning_th="นี่คือ test signal จาก Big-wealth bot ✅ ระบบเชื่อมต่อ Telegram สำเร็จ",
    )
    send_signal(signal)
    print("✅ Test signal sent to channel!")


if __name__ == "__main__":
    main()
