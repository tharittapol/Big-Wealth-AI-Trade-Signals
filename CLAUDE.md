# Big-wealth — AI Trading Agent

## Project Overview

**Big-wealth** is an AI-powered trading assistant for US stocks and Cryptocurrency.
It scans the market daily, picks the **top 3 best opportunities** per market,
sends Telegram notifications with entry/TP/SL and Thai-language reasoning,
supports paper trading, and runs on Google Cloud Platform.

**Supported markets:**
- US Stocks via Yahoo Finance (`yfinance`) — price ≤ $50/share (Dime broker requires min 1 share per sell)
- Crypto via Binance.th API (`httpx` + CCXT auth) — top pairs by 24h volume
- Broker channels: Dime (US stocks), BinanceTH (Crypto)

**Trading style:** Swing trade 1–5 days. Focus on high-profit, high-probability setups.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| AI Agent | Claude Code CLI (`claude -p`) — Pro/Max OAuth, no API key needed |
| AI Model | `claude-opus-4-7` (discovery + analysis + TP advisor) |
| US Stock Data | `yfinance` (OHLCV + news) |
| Crypto Data | Binance.th REST API via `httpx` (OHLCV + top volume pairs) |
| Technical Analysis | `ta` library (RSI, MACD, Bollinger Bands, EMA/SMA) |
| Notification | Telegram Bot (`python-telegram-bot`) |
| Scheduler | Google Cloud Scheduler + Cloud Run Jobs |
| Config / Secrets | Google Secret Manager |
| Storage | Google Cloud Firestore (trade log, paper trades) |
| Containerization | Docker (multi-stage, non-root user) |
| CI/CD | GitHub Actions → Cloud Build → GCP Artifact Registry → Cloud Run |

---

## Architecture

```
Cloud Scheduler (daily cron)
        │
        ▼
Cloud Run Job (scanner-us-stocks / scanner-crypto)
        │
        ├─ [US Stocks — Mon–Fri 20:00 UTC+7]
        │   ├─ DISCOVERY: Claude Opus 4.7 + WebSearch → 10–15 candidates ≤$50 with buffered news
        │   ├─ DATA: fetch_ohlcv() via yfinance + compute_indicators() for each candidate
        │   └─ ANALYSIS: Claude Opus 4.7 → ranks candidates + returns top 3 with Thai reasoning
        │
        ├─ [Crypto — Daily 20:00 UTC+7]
        │   ├─ DISCOVERY: Claude Opus 4.7 + WebSearch → 10–15 Binance.th pairs with buffered news
        │   ├─ DATA: fetch_ohlcv() via Binance.th + compute_indicators()
        │   └─ ANALYSIS: Claude Opus 4.7 → ranks candidates + returns top 3 with Thai reasoning
        │
        ├─ paper_trade_engine()   → open paper positions only for high-confidence signals
        └─ notify_telegram()      → 3 US + 3 Crypto signal cards + daily summary

Cloud Run Service (always-on, min-instances=1)
        │
        ▼
[big-wealth-bot]
   ├─ Telegram bot in polling mode (run_bot())
   ├─ Health-check HTTP server on $PORT (Cloud Run liveness)
   └─ Handles user commands: /positions /pnl /history /tp
```

### Claude CLI Auth in Cloud Run

Claude Code CLI uses **OAuth session** (Pro/Max plan) — no `ANTHROPIC_API_KEY` credits needed:

- **Local:** CLI reads `~/.claude/.credentials.json` — your existing `claude login` session
- **Cloud Run:** `scripts/entrypoint.sh` writes the credentials from `CLAUDE_CREDENTIALS` Secret Manager secret to `/home/appuser/.claude/.credentials.json` before the job starts
- `ANTHROPIC_API_KEY` is always stripped from subprocess env so OAuth takes priority everywhere

---

## Core Modules

### `src/data/`
- `us_stocks.py` — yfinance fetcher: OHLCV daily + news headlines + `fetch_multiple`
- `crypto.py` — Binance.th OHLCV via httpx + `fetch_top_volume_pairs` + `fetch_multiple` + `get_available_symbols()` (validates discovered crypto symbols against Binance.th exchangeInfo before OHLCV fetch)

### `src/indicators/`
- `technical.py` — RSI, MACD, BB, EMA/SMA crossover; `score_signal()` returns 0–4

### `src/agent/`
- `scanner.py` — 3-phase scan pipeline: Discovery → Data → CandidateTicker assembly
- `analyzer.py` — Claude Opus 4.7: given candidates with data + news → picks top 3, Thai reasoning; fallback to score-based selection
- `tp_advisor.py` — Claude Opus 4.7 TP recommendation; news fetched once and buffered
- `models.py` — `CandidateTicker`, `TradeSignal`, `ScanResult`, `TPAdvice`

### `src/cloud/`
- `claude_cli.py` — `run_claude()` subprocess wrapper with OAuth support
- `main.py` — Cloud Run Job entrypoint: `--mode scan/update-paper/tp --market us/crypto/both`; the `_scan` function gates `open_position()` on `signal.confidence == "high"`
- `bot_server.py` — Cloud Run Service entrypoint; health-check HTTP server on `$PORT` (background thread) + Telegram polling loop (`run_bot()`) in main thread
- `secrets.py` — Secret Manager access with env var fallback
- `firestore.py` — Firestore client singleton

### `src/trading/`
- `paper_trade.py` — open/close paper positions, P&L tracking, Firestore `paper_trades` collection

### `src/notifications/`
- `telegram.py` — `send_signal`, `send_daily_summary`, `send_alert`; command handlers `/positions`, `/pnl`, `/history`, `/tp`; `run_bot()` (polling, used by bot Service) and `run_bot_webhook(url, port)` (alternative webhook mode, code only — not deployed)
- `telegram_bot.py` — thin `__main__` wrapper that calls `run_bot()` for local dev
- `formatter.py` — HTML Telegram card formatting (Thai + English)

### `config/`
- `settings.yaml` — all thresholds, price caps, schedule reference (fully commented)
- `watchlist_crypto.yaml` — fallback crypto pairs (used only if discovery AND Binance volume fetch fail)

### `scripts/`
- `entrypoint.sh` — writes Claude OAuth credentials at container startup
- `init_config_secrets.sh` — re-runnable bootstrap; creates `SETTINGS_YAML` + `WATCHLIST_CRYPTO_YAML` in Secret Manager and mounts only `SETTINGS_YAML` as a file in all 3 Cloud Run Jobs and the `big-wealth-bot` Service via `--update-secrets` (additive)
- `run_scan.py` — local scan test
- `test_fetch.py` — local data fetch test
- `test_paper_trade.py` — local paper trading test
- `test_telegram.py` — local Telegram test

---

## Signal Logic

### US Stocks
1. **Claude Opus 4.7 + WebSearch** discovers 10–15 candidates: trending stocks with news catalysts ≤$50/share. News/catalyst buffered into `CandidateTicker.news`.
2. **OHLCV + indicators** computed for each candidate (no re-search)
3. **Claude Opus 4.7** receives: price data + indicators + buffered news → ranks all → returns top 3

### Crypto
1. **Claude Opus 4.7 + WebSearch** discovers 10–15 pairs with news catalysts. Buffered news into `CandidateTicker.news`.
2. **Binance.th symbol validation:** discovered symbols are intersected with `get_available_symbols()` (Binance.th `TRADING` spot pairs). If fewer than 5 survive validation, supplement with `fetch_top_volume_pairs()` fallback.
3. **OHLCV + indicators** computed for all validated symbols — no min_score pre-filter (Claude receives the full validated set).
4. **Claude Opus 4.7** receives: validated candidates + buffered news → ranks → returns top 3.

### Claude AI Output (per signal)
```json
{
  "symbol": "SOFI",
  "market": "us_stock",
  "entry": 10.50,
  "tp": 13.00,
  "sl": 9.50,
  "confidence": "high",
  "timeframe_days": 3,
  "reasoning_th": "SOFI ราคาทดสอบแนวรับแข็งแกร่ง RSI oversold MACD กำลัง cross ขึ้น..."
}
```

---

## Paper Trading

- Telegram card is sent for every selected signal (3 per market).
- A paper position is opened in Firestore (`paper_trades/{symbol_YYYY-MM-DD}`) **only when `signal.confidence == "high"`**. The confidence gate lives in `src/cloud/main.py::_scan`, not in `paper_trade.py` — lower-confidence signals are surfaced to Telegram but excluded from the paper-trading track record.
- Document ID uses `_` for `/` in symbol (e.g., `BTC_USDT_2026-05-20`) — Firestore path separator fix.
- Daily update: mark-to-market against live price.
- On TP/SL hit: close position, record P&L.
- Telegram commands: `/positions`, `/pnl`, `/history`.
- History sorted in Python (not Firestore) to avoid composite index requirement.

---

## TP Advisor

User sends to Telegram bot:
```
/tp BTC/USDT 2026-05-10 62000 crypto
/tp SOFI 2026-05-15 11.00 us_stock
```
Claude receives: historical data from entry date to today + current price + buffered news → recommends TP levels with Thai reasoning.

---

## Telegram Signal Card Format

```
🔔 BUY SIGNAL — SOFI (US Stock)

Entry:      $10.50
TP:         $13.00 (+23.8%)
SL:         $9.50  (-9.5%)
Timeframe:  3 วัน
Confidence: สูง

📊 Indicators:
  RSI: 35 (oversold)
  MACD: Bullish cross
  BB: Price at lower band
  EMA: 9>21 crossover

🤖 เหตุผล:
  SOFI ราคาทดสอบแนวรับแข็งแกร่งที่ $10 RSI เข้าโซน oversold
  MACD กำลัง cross ขึ้น มีข่าวผลประกอบการ Q1 ดีกว่าคาด 37%

#SOFI #USStock #BuySignal
```

---

## Environment Variables / Secrets

All secrets stored in **Google Secret Manager**, accessed at runtime:

| Secret Name | Purpose |
|---|---|
| `CLAUDE_CREDENTIALS` | Claude Code CLI OAuth session JSON (`~/.claude/.credentials.json`) |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot |
| `TELEGRAM_CHANNEL_ID` | Target broadcast channel |
| `BINANCE_API_KEY` | Binance.th market data |
| `BINANCE_SECRET_KEY` | Binance.th auth |
| `SETTINGS_YAML` | Mounted as a file at `/app/config/settings.yaml` — overrides the bundled image copy at runtime (no Docker rebuild for config changes) |
| `WATCHLIST_CRYPTO_YAML` | Stored in Secret Manager for parity, **not mounted** on Cloud Run (Cloud Run rejects two file-secret volumes in the same directory; active crypto fallback is hardcoded as `_FALLBACK_CRYPTO_SYMBOLS` in `src/agent/scanner.py`) |
| `GCP_PROJECT_ID` | GCP project (env var, not Secret Manager) |
| `ANTHROPIC_API_KEY` | Stored but not used (OAuth preferred) |

---

## Cloud Run Resources

| Resource | Type | UTC | UTC+7 | Notes |
|---|---|---|---|---|
| `scanner-us-stocks` | Job | `0 13 * * 1-5` | 20:00 Mon–Fri | Before NYSE open |
| `scanner-crypto` | Job | `0 13 * * *` | 20:00 daily | Crypto is 24/7 |
| `paper-trade-updater` | Job | `0 1 * * *` | 08:00 daily | Morning mark-to-market |
| `big-wealth-bot` | **Service** (`min-instances=1`) | n/a | 24/7 | Telegram polling + `$PORT` health check; handles `/positions`, `/pnl`, `/history`, `/tp` |

---

## Local Development

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Must have Claude Code CLI logged in
claude login    # one-time setup
claude --version

# Run scanner locally
python -m src.cloud.main --mode scan --market crypto
python -m src.cloud.main --mode scan --market us

# Run TP advisor
python -m src.cloud.main --mode tp --symbol BTC/USDT --entry-date 2026-05-10 --entry-price 62000 --market crypto

# Run Telegram bot
python -m src.notifications.telegram_bot

# Run tests
pytest tests/ -v
```

---

## Project Structure

```
Big-wealth/
├── CLAUDE.md
├── IMPLEMENTATION_PLAN.md
├── RUNBOOK.md
├── README.md
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── .env.example
├── config/
│   ├── watchlist_crypto.yaml      ← fallback only
│   └── settings.yaml              ← fully commented
├── scripts/
│   ├── entrypoint.sh              ← Cloud Run: write Claude credentials
│   ├── init_config_secrets.sh    ← one-time setup: SETTINGS_YAML + WATCHLIST_CRYPTO_YAML
│   ├── run_scan.py
│   ├── test_fetch.py
│   ├── test_paper_trade.py
│   └── test_telegram.py
├── src/
│   ├── data/
│   │   ├── us_stocks.py
│   │   └── crypto.py
│   ├── indicators/
│   │   └── technical.py
│   ├── agent/
│   │   ├── models.py
│   │   ├── scanner.py
│   │   ├── analyzer.py
│   │   └── tp_advisor.py
│   ├── trading/
│   │   └── paper_trade.py
│   ├── notifications/
│   │   ├── telegram.py
│   │   ├── telegram_bot.py        ← __main__ wrapper → run_bot() (local dev)
│   │   └── formatter.py
│   └── cloud/
│       ├── main.py
│       ├── bot_server.py          ← Cloud Run Service: bot polling + $PORT health check
│       ├── claude_cli.py
│       ├── secrets.py
│       └── firestore.py
├── tests/
│   ├── test_data.py
│   ├── test_indicators.py
│   ├── test_scanner.py
│   ├── test_analyzer.py
│   ├── test_tp_advisor.py
│   ├── test_formatter.py
│   └── test_paper_trade.py
├── infra/
│   ├── cloudbuild.yaml
│   ├── cloud_scheduler_jobs.yaml
│   ├── create_scheduler_jobs.sh
│   └── firestore.indexes.json
└── .github/
    └── workflows/
        ├── deploy.yml             ← Docker build + Cloud Run Jobs update (ignores config/**)
        └── update-config.yml      ← config/** only: upload to Secret Manager + restart bot Service
```

---

## Coding Conventions

- All data fetching returns `pd.DataFrame` with standardized OHLCV columns
- AI agent responses validated with Pydantic models
- Secrets never in code — always from Secret Manager (env var fallback for local dev)
- All Firestore writes are idempotent (upsert by date+symbol)
- Firestore document IDs: replace `/` with `_` (path separator conflict)
- Use `structlog` for structured JSON logging (Cloud Logging compatible)
- Type hints on all public functions
- Tests use `pytest` with `pytest-mock` for external API calls
- Thai-language reasoning is in `reasoning_th` field of `TradeSignal`
- Claude CLI: always strip `ANTHROPIC_API_KEY` from subprocess env (force OAuth)
- Config files (`settings.yaml`, `watchlist_crypto.yaml`) are served from Secret Manager at runtime in production — local edits land in the deployed system via the `update-config.yml` GitHub workflow, not a Docker rebuild
- No comments unless the WHY is non-obvious

## Essential Workflow

1. Before starting to code, read `IMPLEMENTATION_PLAN.md` and select tasks not yet checked.
2. If any requirement is unclear, **ask before writing any code**.
3. Follow `IMPLEMENTATION_PLAN.md` step by step.
4. On task completion: mark `[ ]` → `[x]` in `IMPLEMENTATION_PLAN.md`.
