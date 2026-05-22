# Big-wealth Implementation Plan

## Phase 1 — Foundation ✅ DONE

**Goal:** Data layer and indicators, no external AI/cloud needed.

### 1.1 Project scaffold ✅
- [x] `pyproject.toml` + `requirements.txt` (using `ta` lib, Python 3.11)
- [x] `src/` package structure
- [x] `.env.example`
- [x] `config/settings.yaml` — thresholds, price caps, schedule (with full inline comments)
- [x] `config/watchlist_crypto.yaml` — fallback pairs (primary is Claude web search)

### 1.2 Data layer ✅
- [x] `src/data/us_stocks.py` — `fetch_ohlcv`, `fetch_news`, `fetch_multiple`
- [x] `src/data/crypto.py` — `fetch_ohlcv` via Binance.th httpx, `fetch_top_volume_pairs`, `fetch_multiple`
- [x] Unit tests: `tests/test_data.py`

### 1.3 Indicators ✅
- [x] `src/indicators/technical.py` — RSI, MACD, Bollinger Bands, EMA/SMA; `score_signal() → SignalScore`
- [x] Unit tests: `tests/test_indicators.py`

---

## Phase 2 — AI Agent ✅ DONE

**Goal:** Claude AI discovers candidates via web search, analyzes with indicators, returns structured Thai-language signals.  
**Tech:** Claude Code CLI (`claude -p`) with Pro/Max OAuth — no Anthropic API key required.

### 2.1 Pydantic models ✅
- [x] `src/agent/models.py` — `CandidateTicker`, `TradeSignal`, `ScanResult`, `TPAdvice`, `TPLevel`

### 2.2 Scanner — 3-phase pipeline ✅
- [x] `src/agent/scanner.py`
  - **Phase 1 (Discovery):** `_discover_us_candidates()` + `_discover_crypto_candidates()` — Claude Opus 4.7 + WebSearch, buffered news/catalyst in `CandidateTicker.news`
  - **Crypto symbol validation (commit 6b1196d):** discovered symbols intersected with `get_available_symbols()` (Binance.th `TRADING` spot pairs) before OHLCV fetch. If fewer than 5 validate, supplement via `fetch_top_volume_pairs()`.
  - **Phase 2 (Data):** OHLCV + indicators for discovered symbols (no re-search)
  - **Phase 3 (Candidates):** price cap filter, assemble `CandidateTicker` list
  - Fallback: hardcoded symbol list if discovery fails
- [x] Unit tests: `tests/test_scanner.py`

### 2.3 AI Analyzer ✅
- [x] `src/agent/analyzer.py` — Claude Opus 4.7; `pick_top3(candidates, market) → list[TradeSignal]`; receives all validated candidates (no `min_score` pre-filter — commit 0175a5e); buffered news displayed in prompt; fallback to score-based selection if Claude fails
  - Note: `agent.crypto_prescan_min_score` in `settings.yaml` is now dead config (kept for future use; no module reads it)
- [x] Unit tests: `tests/test_analyzer.py`

### 2.4 TP Advisor ✅
- [x] `src/agent/tp_advisor.py` — Claude Opus 4.7; news buffered once before analysis (yfinance for US, Claude web search for crypto); `get_tp_advice() → TPAdvice`
- [x] Unit tests: `tests/test_tp_advisor.py`

### 2.5 Claude CLI wrapper ✅
- [x] `src/cloud/claude_cli.py` — `run_claude(prompt, model, enable_web_search)` subprocess wrapper
  - `--dangerously-skip-permissions` for headless use
  - `--allowedTools WebSearch` when `enable_web_search=True`
  - Always strips `ANTHROPIC_API_KEY` from env — forces OAuth auth
  - Cloud Run: credentials written to `~/.claude/.credentials.json` by `scripts/entrypoint.sh`

---

## Phase 3 — Notifications + Paper Trading ✅ DONE

### 3.1 Formatter ✅
- [x] `src/notifications/formatter.py` — signal cards, daily summary, TP advice, positions, P&L (HTML Telegram format)
- [x] Unit tests: `tests/test_formatter.py`

### 3.2 Telegram bot ✅
- [x] `src/notifications/telegram.py` — `send_signal`, `send_daily_summary`, `send_alert`
  - Command handlers: `/positions`, `/pnl`, `/history`, `/tp`
  - `run_bot()` polling loop

### 3.3 Paper trading engine ✅
- [x] `src/trading/paper_trade.py` — Firestore `paper_trades/{symbol_date}` documents
  - `open_position`, `update_positions`, `check_exits`, `get_open_positions`, `get_history`, `get_pnl_summary`
  - Symbol `/` replaced with `_` in doc IDs (Firestore path separator fix)
  - History sorted in Python (no composite index required)
- [x] **High-confidence gate (commit 197c399):** `src/cloud/main.py::_scan` calls `open_position()` only when `signal.confidence == "high"`. Lower-confidence signals are sent to Telegram but excluded from the paper-trading track record.
- [x] Unit tests: `tests/test_paper_trade.py`

### 3.4 Telegram Bot Server ✅
- [x] `src/cloud/bot_server.py` — Cloud Run Service entrypoint (always-on)
  - Background thread: HTTP health-check server on `$PORT` (Cloud Run liveness requirement)
  - Main thread: `run_bot()` polling loop
- [x] `src/notifications/telegram.py::run_bot_webhook(url, port=8080)` — alternative webhook mode (code exists; not deployed)
- [x] `src/notifications/telegram_bot.py` — thin local-dev wrapper (`python -m src.notifications.telegram_bot`)

---

## Phase 4 — Cloud Deployment ✅ DONE

**Goal:** Fully automated on GCP with scheduled jobs and CI/CD.

### 4.1 Docker + Cloud Run Jobs ✅
- [x] `Dockerfile` — multi-stage Python 3.11 slim + Node.js 20 + Claude Code CLI
  - Non-root `appuser` (Claude CLI refuses `--dangerously-skip-permissions` as root)
  - `scripts/entrypoint.sh` writes Claude OAuth credentials before startup
- [x] `scripts/entrypoint.sh` — writes `CLAUDE_CREDENTIALS` env var to `~/.claude/.credentials.json`
- [x] `src/cloud/main.py` — CLI entrypoint: `--mode scan/update-paper/tp --market us/crypto/both`
- [x] `src/cloud/secrets.py` — Secret Manager access with env var fallback
- [x] `src/cloud/firestore.py` — Firestore client singleton

### 4.2 GCP Infrastructure ✅
- [x] **Artifact Registry** — `asia-southeast1-docker.pkg.dev/{PROJECT_ID}/big-wealth/scanner`
- [x] **Firestore** — `paper_trades` collection with sorted-in-Python history query
- [x] **Secret Manager** — 8 secrets:
  - `ANTHROPIC_API_KEY` (stored but not used — kept for reference)
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`
  - `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`
  - `CLAUDE_CREDENTIALS` — OAuth JSON from `~/.claude/.credentials.json` (Pro plan)
  - `SETTINGS_YAML` — mounted as a file at `/app/config/settings.yaml` (commit 513d40e + Phase 4 completion 2026-05-21)
  - `WATCHLIST_CRYPTO_YAML` — created for parity, **not mounted** (Cloud Run rejects two file-secret volumes in the same directory; active fallback list is hardcoded in `src/agent/scanner.py:_FALLBACK_CRYPTO_SYMBOLS`)
- [x] **Service Account** — `big-wealth-runner@{PROJECT_ID}.iam.gserviceaccount.com`
- [x] **Cloud Run Jobs** — `scanner-us-stocks`, `scanner-crypto`, `paper-trade-updater`
- [x] **Cloud Run Service** — `big-wealth-bot` (always-on, `min-instances=1`, mounts config secrets)
- [x] **Cloud Scheduler** — 3 jobs at UTC times

### 4.3 Cloud Scheduler ✅
- [x] `scanner-us-stocks`: `0 13 * * 1-5` (13:00 UTC = 20:00 UTC+7, Mon–Fri)
- [x] `scanner-crypto`: `0 13 * * *` (13:00 UTC = 20:00 UTC+7, daily)
- [x] `paper-trade-updater`: `0 1 * * *` (01:00 UTC = 08:00 UTC+7, daily)

### 4.4 CI/CD ✅
- [x] `.github/workflows/deploy.yml` — push to `main` → Cloud Build → Artifact Registry → update Cloud Run Jobs (ignores `config/**`, `*.md`, `docs/**`)
- [x] Workload Identity Federation (no long-lived GCP keys in GitHub)

### 4.5 Secret Manager Config Serving ✅ (commit 513d40e + bootstrap 2026-05-21)
- [x] `scripts/init_config_secrets.sh` — re-runnable bootstrap; creates both `SETTINGS_YAML` + `WATCHLIST_CRYPTO_YAML` secrets and mounts only `SETTINGS_YAML` on all 3 Jobs + the bot Service via `--update-secrets` (additive; preserves existing env-var secret mounts)
- [x] `.github/workflows/update-config.yml` — push to `config/settings.yaml` on `main` → uploads `SETTINGS_YAML` to Secret Manager → restarts `big-wealth-bot` Service so it picks up new config immediately
- [x] Bundled `config/settings.yaml` in the Docker image is overridden by the Secret Manager file mount at runtime; no Docker rebuild needed for `settings.yaml` changes
- [x] Cloud Run Jobs (`scanner-us-stocks`, `scanner-crypto`, `paper-trade-updater`) pick up new config on their next scheduled execution
- Note: `WATCHLIST_CRYPTO_YAML` is created in Secret Manager for documentation parity but is NOT mounted (Cloud Run does not permit two file-secret volumes at the same `mountPath`). Active crypto fallback is hardcoded as `_FALLBACK_CRYPTO_SYMBOLS` in `src/agent/scanner.py`.

---

## Phase 5 — Polish & Monitoring

### 5.1 Error handling
- [ ] Telegram alert on job failure (currently logs only)
- [ ] Retry with exponential backoff for Binance/yfinance API calls
- [ ] Crypto fallback: if Claude discovers pairs not on Binance.th → filter against available pairs first

### 5.2 Backtesting
- [ ] `src/backtest/runner.py` — replay signal logic on 90d historical data
- [ ] Metrics: win rate, avg R:R, max drawdown
- [ ] Report sent to Telegram on demand

### 5.3 Observability
- [ ] GCP Cloud Logging dashboard
- [ ] Error rate alert policy (notify Telegram on > N failures/day)

### 5.4 OAuth Credential Rotation
- [ ] Script to refresh `CLAUDE_CREDENTIALS` secret when OAuth token nears expiry (~1 year TTL)
- [ ] Monitor token expiry date: currently expires ~May 2027

---

## API Keys / Services Required

| Service | Required? | Notes |
|---|---|---|
| Claude Code CLI (Pro/Max plan) | **Yes** | OAuth session — `claude login` locally. Credentials stored in Secret Manager as `CLAUDE_CREDENTIALS` for Cloud Run. No `ANTHROPIC_API_KEY` credits needed. |
| `TELEGRAM_BOT_TOKEN` | **Yes** | @BotFather → `/newbot` |
| `TELEGRAM_CHANNEL_ID` | **Yes** | Channel where signals are sent |
| `BINANCE_API_KEY` | **Yes** | binance.th Read Only — for crypto OHLCV |
| `BINANCE_SECRET_KEY` | **Yes** | Same |
| GCP Project | **Yes** | Firestore + Cloud Run + Secret Manager |
| `ANTHROPIC_API_KEY` | No | Not used (OAuth preferred); kept in Secret Manager for reference |

---

## Test Suite

106 tests — all passing:

```bash
pytest tests/ -v
# tests/test_data.py          ✅
# tests/test_indicators.py    ✅
# tests/test_scanner.py       ✅
# tests/test_analyzer.py      ✅
# tests/test_tp_advisor.py    ✅
# tests/test_formatter.py     ✅
# tests/test_paper_trade.py   ✅
```
