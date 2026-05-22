 ---
  Full Auto Workflow: First Step → Notification

  US Stocks (Mon–Fri, 20:00 UTC+7)

  Cloud Scheduler
    └─ triggers Cloud Run Job: scanner-us-stocks
          │
          ▼
  1. DISCOVERY (scanner.py)
     Claude Opus 4.7 + WebSearch
     → finds 10–15 trending US stocks ≤$50/share with news catalysts
     → stores each as CandidateTicker(symbol, news=...)
          │
          ▼
  2. DATA FETCH (us_stocks.py)
     yfinance → OHLCV daily candles for each candidate
     technical.py → RSI, MACD, Bollinger Bands, EMA/SMA, score_signal() (0–4)
          │
          ▼
  3. ANALYSIS (analyzer.py)
     Claude Opus 4.7 receives: price data + indicators + buffered news
     → ranks all candidates → returns top 3 as TradeSignal JSON
          │
          ▼
  4. PAPER TRADE GATE (main.py::_scan)
     if signal.confidence == "high":
         open_position() → writes to Firestore paper_trades collection
          │
          ▼
  5. NOTIFICATION (telegram.py)
     send_signal() → HTML card per signal (3 cards)
     send_daily_summary() → summary of all 3
     → posted to Telegram channel

  ---
  Crypto (Daily, 20:00 UTC+7)

  Cloud Scheduler
    └─ triggers Cloud Run Job: scanner-crypto
          │
          ▼
  1. DISCOVERY (scanner.py)
     Claude Opus 4.7 + WebSearch
     → finds 10–15 Binance.th pairs with catalysts
     → buffered news into CandidateTicker.news
          │
          ▼
  2. SYMBOL VALIDATION (crypto.py)
     get_available_symbols() → hits Binance.th exchangeInfo
     → intersects discovered symbols with TRADING spot pairs
     → if <5 survive: supplement with fetch_top_volume_pairs()
          │
          ▼
  3. DATA FETCH (crypto.py)
     Binance.th REST API → OHLCV for all validated symbols
     technical.py → same indicators (no min_score filter — full set sent to Claude)
          │
          ▼
  4. ANALYSIS (analyzer.py)
     Claude Opus 4.7 → ranks validated candidates + returns top 3 TradeSignals
          │
          ▼
  5. PAPER TRADE GATE + NOTIFICATION
     (same as US stocks above)

  ---
  Supporting Daily Job

  paper-trade-updater (08:00 UTC+7 daily)
    └─ mark-to-market all open positions against live price
    └─ auto-close if TP or SL hit, record P&L in Firestore

  Always-On Bot Service

  big-wealth-bot (24/7, Cloud Run Service)
    ├─ HTTP health-check on $PORT (Cloud Run liveness probe)
    └─ Telegram polling loop
         ├─ /positions → open paper trades from Firestore
         ├─ /pnl      → realized P&L summary
         ├─ /history  → closed trades (sorted in Python)
         └─ /tp       → calls tp_advisor.py (Claude Opus 4.7 + news)

  All config (settings.yaml) lives in Google Secret Manager and is mounted at runtime — no Docker rebuild needed to change thresholds.