"""Entry point for running the Telegram bot command listener."""
from dotenv import load_dotenv
load_dotenv()

from src.notifications.telegram import run_bot

if __name__ == "__main__":
    run_bot()
