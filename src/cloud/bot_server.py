"""Telegram bot server — deployed as Cloud Run Service (always-on, min-instances=1).

Cloud Run requires a port listener for health checks.
A minimal HTTP server handles health checks on PORT while the bot polls Telegram.
"""
from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
load_dotenv()

import structlog

logger = structlog.get_logger()


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass  # suppress access logs


def _start_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info("Health check server started", port=port)
    server.serve_forever()


def main() -> None:
    port = int(os.environ.get("PORT", 8080))

    # Start health-check HTTP server in background thread
    t = threading.Thread(target=_start_health_server, args=(port,), daemon=True)
    t.start()

    # Run Telegram bot (polling) in main thread
    from src.notifications.telegram import run_bot
    logger.info("Starting Telegram bot (polling mode)")
    run_bot()


if __name__ == "__main__":
    main()
