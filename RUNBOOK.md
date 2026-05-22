# Big-wealth — คู่มือการใช้งาน

---

## สารบัญ

1. [สิ่งที่ต้องเตรียมก่อน (Prerequisites)](#1-prerequisites)
2. [Setup ครั้งแรก (First-time Setup)](#2-first-time-setup)
3. [การทดสอบและรันบน Local](#3-local-run--test)
4. [วิธีใช้งานระบบ (Usage Guide)](#4-usage-guide)
5. [Deploy บน Cloud (GCP)](#5-cloud-deployment-gcp)
6. [Maintenance และ Update](#6-maintenance--updates)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

### Software ที่ต้องติดตั้ง

| Software | Version | ดาวน์โหลด |
|---|---|---|
| Python | 3.12+ | python.org |
| Git | ล่าสุด | git-scm.com |
| Node.js | 20+ | nodejs.org |
| Claude Code CLI | ล่าสุด | `npm install -g @anthropic-ai/claude-code` |
| Google Cloud CLI (`gcloud`) | ล่าสุด | cloud.google.com/sdk |

> **Claude Code CLI Auth:**
> ระบบใช้ Claude Code CLI ผ่าน **OAuth (Pro/Max plan)** — ไม่ต้องใช้ `ANTHROPIC_API_KEY` credits
> ```bash
> claude login      # login ครั้งแรก (เปิด browser)
> claude --version  # ตรวจสอบ
> ```

### API Keys / Services ที่ต้องขอ

| Key | วิธีขอ | ใช้ทำอะไร |
|---|---|---|
| **Claude Code CLI Pro/Max** | claude.ai/upgrade | AI discovery + analysis (OAuth, ไม่ต้อง API key) |
| `TELEGRAM_BOT_TOKEN` | Telegram → @BotFather → `/newbot` | ส่ง signal + รับ command |
| `TELEGRAM_CHANNEL_ID` | ดูขั้นตอนด้านล่าง | channel ที่รับ signal |
| `BINANCE_API_KEY` | binance.th → โปรไฟล์ → API Management | ดึงราคา Crypto |
| `BINANCE_SECRET_KEY` | เดียวกัน | Binance.th auth |
| GCP Project | console.cloud.google.com | Firestore + Cloud Run + Secret Manager |

---

## 2. First-time Setup

### 2.1 Clone และ setup Python

```bash
git clone https://github.com/YOUR_USERNAME/big-wealth.git
cd big-wealth

# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac/Linux
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 2.2 สร้าง .env file

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Mac/Linux
```

เปิดไฟล์ `.env` แล้วกรอกค่า:

```env
TELEGRAM_BOT_TOKEN=123456789:AAFxxxxxxx
TELEGRAM_CHANNEL_ID=-100123456789
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key
GCP_PROJECT_ID=your-gcp-project-id
```

> **หมายเหตุ:** ไม่ต้องใส่ `ANTHROPIC_API_KEY` — ระบบใช้ Claude CLI OAuth (Pro/Max plan) แทน

### 2.3 Login Claude Code CLI

```bash
claude login
# เปิด browser → login ด้วย Claude account ที่มี Pro/Max plan
```

### 2.4 สร้าง Telegram Bot และหา Channel ID

**สร้าง Bot:**
1. เปิด Telegram → คุยกับ `@BotFather`
2. พิมพ์ `/newbot` → ตั้งชื่อ → ตั้ง username (ลงท้าย `bot`)
3. Copy **Token** ใส่ `.env`

**หา Channel ID:**
1. สร้าง Telegram Channel (หรือใช้ที่มีอยู่)
2. เพิ่ม bot เป็น Admin (สิทธิ์ Post Messages)
3. Forward message จาก channel ไปให้ `@userinfobot`
4. จะได้ ID เช่น `-1001234567890` → ใส่ใน `TELEGRAM_CHANNEL_ID`

> **หมายเหตุ Telegram Bot:** Bot ไม่สามารถรับคำสั่งใน Channel ได้ — คำสั่ง `/positions`, `/pnl`, `/history`, `/tp` ต้องพิมพ์ใน **DM กับ bot** หรือ **Group ที่มี bot**

### 2.5 ขอ Binance.th API Key

1. Login [binance.th](https://www.binance.th)
2. ไป **โปรไฟล์ → API Management**
3. กด **สร้าง API Key** → Label: `big-wealth-bot`
4. เปิดสิทธิ์: ✅ **Read Only** เท่านั้น (ไม่ต้องการสิทธิ์ Trade)
5. Copy `API Key` และ `Secret Key` ใส่ `.env`

### 2.6 ตั้งค่า GCP Project และ Firestore

```bash
# Login
gcloud auth login
gcloud auth application-default login

# สร้าง project
gcloud projects create YOUR-PROJECT-ID --name="Big Wealth"
gcloud config set project YOUR-PROJECT-ID

# เปิด APIs
gcloud services enable \
  firestore.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# สร้าง Firestore database
gcloud firestore databases create --location=asia-southeast1

# ใส่ project ID ใน .env
# GCP_PROJECT_ID=YOUR-PROJECT-ID
```

---

## 3. Local Run & Test

### 3.1 รัน Unit Tests (ไม่ต้องใช้ external APIs)

```bash
pytest tests/ -v
# คาด: ทั้งหมด 106 tests ผ่าน
```

### 3.2 ทดสอบดึงข้อมูลจริง (ต้องมี Binance API Key)

```bash
python scripts/test_fetch.py
```

### 3.3 รัน AI Scanner บน Local (ต้องมี Claude CLI + Binance)

ระบบใช้ **3 Phase**:
1. **Discovery** — Claude Opus 4.7 + WebSearch ค้นหาหุ้น/crypto จากข่าว (~1-3 นาที)
2. **Data** — ดึง OHLCV + คำนวณ indicators (RSI, MACD, BB, EMA)
3. **Analysis** — Claude Opus 4.7 + indicators + ข่าว → top 3 signals

```bash
# Crypto scan
python -m src.cloud.main --mode scan --market crypto

# US Stock scan
python -m src.cloud.main --mode scan --market us

# หรือใช้ script ทดสอบ
python scripts/run_scan.py
```

### 3.4 ทดสอบ TP Advisor

```bash
python -m src.cloud.main --mode tp \
  --symbol BTC/USDT \
  --entry-date 2026-05-10 \
  --entry-price 60000 \
  --market crypto
```

### 3.5 ทดสอบ Telegram

```bash
python scripts/test_telegram.py
# ตรวจสอบว่า signal card ส่งเข้า channel ได้
```

### 3.6 รัน Telegram Bot (รับ commands)

```bash
python -m src.notifications.telegram_bot
```

เปิด Telegram → DM กับ bot แล้วลอง:
- `/pnl` — ดู P&L summary
- `/positions` — ดู open positions
- `/history` — ดู trade ที่ปิดแล้ว

### 3.7 ทดสอบ Paper Trading (ต้องมี GCP + Firestore)

```bash
python scripts/test_paper_trade.py
```

---

## 4. Usage Guide

### 4.1 Signal Card ที่จะได้รับ

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
  SOFI ราคาทดสอบแนวรับแข็งแกร่งที่ $10 RSI oversold
  MACD กำลัง cross ขึ้น ข่าวผลประกอบการ Q1 ดีกว่าคาด 37%

#SOFI #USStock #BuySignal
```

**วิธีอ่าน Signal:**
- **Entry** — ราคาแนะนำให้เข้าซื้อ (limit order ใกล้ราคานี้)
- **TP** — Take Profit เป้าหมายกำไร
- **SL** — Stop Loss จุดตัดขาดทุน
- **Timeframe** — ระยะเวลาที่คาดว่าจะถึง TP (swing trade)

### 4.2 คำสั่ง Telegram Bot (DM หรือ Group)

| Command | ตัวอย่าง | ผลลัพธ์ |
|---|---|---|
| `/positions` | `/positions` | Paper positions ที่เปิดอยู่ + P&L ปัจจุบัน |
| `/pnl` | `/pnl` | Win rate, กำไรสะสม, จำนวน trade |
| `/history` | `/history` | 10 trade ล่าสุดที่ปิดแล้ว |
| `/tp` | `/tp SOFI 2026-05-18 10.50 us_stock` | AI แนะนำ TP levels สำหรับ position ที่ถืออยู่ |

### 4.3 ตารางเวลา (Cloud)

| เวลา (ไทย) | UTC | วัน | Event |
|---|---|---|---|
| **20:00 น.** | 13:00 | จ–ศ | US Stock scan → 3 signals (Telegram); paper position เปิดเฉพาะ signal ที่ `confidence == "high"` |
| **20:00 น.** | 13:00 | ทุกวัน | Crypto scan → 3 signals (Telegram); paper position เปิดเฉพาะ signal ที่ `confidence == "high"` |
| **08:00 น.** | 01:00 | ทุกวัน | Update paper positions (mark-to-market, check TP/SL) |

---

## 5. Cloud Deployment (GCP)

### 5.1 เตรียม Service Account

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=asia-southeast1
export SA_NAME=big-wealth-runner
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# สร้าง Service Account
gcloud iam service-accounts create $SA_NAME \
  --display-name="Big Wealth Runner" \
  --project=$PROJECT_ID

# ให้ roles
for ROLE in roles/run.invoker roles/secretmanager.secretAccessor \
            roles/datastore.user roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE"
done
```

### 5.2 เพิ่ม Secrets ใน Secret Manager

```bash
# Telegram
echo -n "123456789:AAF..." | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=- --project=$PROJECT_ID
echo -n "-100xxxxxxx" | gcloud secrets create TELEGRAM_CHANNEL_ID --data-file=- --project=$PROJECT_ID

# Binance
echo -n "your_key" | gcloud secrets create BINANCE_API_KEY --data-file=- --project=$PROJECT_ID
echo -n "your_secret" | gcloud secrets create BINANCE_SECRET_KEY --data-file=- --project=$PROJECT_ID

# Claude OAuth credentials (ใช้แทน ANTHROPIC_API_KEY)
cat ~/.claude/.credentials.json | gcloud secrets create CLAUDE_CREDENTIALS --data-file=- --project=$PROJECT_ID
```

> **CLAUDE_CREDENTIALS** คือ OAuth token ของ Claude Code CLI Pro/Max plan
> ไฟล์อยู่ที่ `~/.claude/.credentials.json` บนเครื่อง local
> Token มีอายุ ~1 ปี — ต้อง update ใน Secret Manager เมื่อ token หมดอายุ (ดูหัวข้อ 6.3)

```bash
# ให้ Service Account เข้าถึง secrets
for SECRET in TELEGRAM_BOT_TOKEN TELEGRAM_CHANNEL_ID \
              BINANCE_API_KEY BINANCE_SECRET_KEY CLAUDE_CREDENTIALS; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

### 5.3 Setup Config Secrets (Secret Manager YAML serving)

Bootstrap `SETTINGS_YAML` (และสร้าง `WATCHLIST_CRYPTO_YAML` placeholder) ครั้งเดียว — หลังจากนั้นแก้ `config/settings.yaml` แล้ว push → GitHub Actions deploy ให้เอง โดยไม่ต้อง rebuild Docker:

```bash
bash scripts/init_config_secrets.sh $PROJECT_ID $SA_EMAIL
```

Script ทำสิ่งต่อไปนี้ (re-runnable):
1. สร้าง (หรือ add new version) ของ `SETTINGS_YAML` ← `config/settings.yaml`
2. สร้าง (หรือ add new version) ของ `WATCHLIST_CRYPTO_YAML` ← `config/watchlist_crypto.yaml` (สำหรับ parity เท่านั้น — ไม่ถูก mount)
3. ให้ Service Account เข้าถึง secrets ได้
4. Mount เฉพาะ `SETTINGS_YAML` เป็นไฟล์ใน Cloud Run Jobs ทั้ง 3 และ Service `big-wealth-bot` ผ่าน `--update-secrets` (additive — ไม่ทับ env-var secret ที่มีอยู่)
   - `/app/config/settings.yaml` ← `SETTINGS_YAML:latest`

> **ทำไมไม่ mount `WATCHLIST_CRYPTO_YAML`?** Cloud Run ไม่อนุญาตให้ 2 file-secret volume share parent directory (`/app/config/`) เดียวกัน. และ active crypto fallback list ปัจจุบันเป็น `_FALLBACK_CRYPTO_SYMBOLS` ใน `src/agent/scanner.py` — yaml file ไม่ได้ถูกอ่านอยู่แล้ว.

> **หลังจาก bootstrap แล้ว:** แก้ `config/settings.yaml` → push → workflow `update-config.yml` ทำงาน (ดูหัวข้อ 6.2)

### 5.4 สร้าง Artifact Registry

```bash
gcloud artifacts repositories create big-wealth \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID
```

### 5.5 Build Docker Image (ใช้ Cloud Build — ไม่ต้องมี Docker Desktop)

```bash
gcloud builds submit \
  --tag $REGION-docker.pkg.dev/$PROJECT_ID/big-wealth/scanner:latest \
  --project=$PROJECT_ID \
  .
```

### 5.6 สร้าง Cloud Run Jobs

```bash
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/big-wealth/scanner:latest"
SECRETS="TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,\
TELEGRAM_CHANNEL_ID=TELEGRAM_CHANNEL_ID:latest,\
BINANCE_API_KEY=BINANCE_API_KEY:latest,\
BINANCE_SECRET_KEY=BINANCE_SECRET_KEY:latest,\
CLAUDE_CREDENTIALS=CLAUDE_CREDENTIALS:latest"

# US Stock Scanner
gcloud run jobs create scanner-us-stocks \
  --image=$IMAGE --region=$REGION --project=$PROJECT_ID \
  --service-account=$SA_EMAIL --max-retries=1 --task-timeout=3600 \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --set-secrets="$SECRETS" \
  --args="--mode,scan,--market,us"

# Crypto Scanner
gcloud run jobs create scanner-crypto \
  --image=$IMAGE --region=$REGION --project=$PROJECT_ID \
  --service-account=$SA_EMAIL --max-retries=1 --task-timeout=3600 \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --set-secrets="$SECRETS" \
  --args="--mode,scan,--market,crypto"

# Paper Trade Updater
gcloud run jobs create paper-trade-updater \
  --image=$IMAGE --region=$REGION --project=$PROJECT_ID \
  --service-account=$SA_EMAIL --max-retries=1 --task-timeout=600 \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --set-secrets="$SECRETS" \
  --args="--mode,update-paper"
```

### 5.7 ตั้ง Cloud Scheduler

```bash
# Scheduler Service Account
gcloud iam service-accounts create big-wealth-scheduler \
  --display-name="Big Wealth Scheduler" --project=$PROJECT_ID

SCHEDULER_SA="big-wealth-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SCHEDULER_SA" --role="roles/run.invoker"

# Deploy ด้วย script อัตโนมัติ
export SA_EMAIL=$SCHEDULER_SA
bash infra/create_scheduler_jobs.sh
```

### 5.8 ทดสอบ Cloud Deployment

```bash
# ทดสอบ crypto scan
gcloud run jobs execute scanner-crypto \
  --region=$REGION --project=$PROJECT_ID --wait

# ดู logs
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=scanner-crypto" \
  --project=$PROJECT_ID --limit=30 \
  --format="table(timestamp, textPayload)"
```

**ผลที่คาดหวัง:**
```
[entrypoint] Claude credentials written to ~/.claude/.credentials.json
Claude CLI call complete  cost_usd=0.15  model=opus  web_search=True
US discovery complete  count=15
AI signals selected  count=3  market=us_stock  symbols=['SOFI', 'RIVN', 'NU']
Signal sent to channel  symbol=SOFI
Paper position opened  entry=10.50  symbol=SOFI
Scan complete  us_count=3  crypto_count=3
```

### 5.9 Deploy Telegram Bot Service (`big-wealth-bot`)

Bot เป็น **Cloud Run Service** (always-on) ไม่ใช่ Job — รัน Telegram polling 24/7 + ฟัง `$PORT` สำหรับ Cloud Run health check

```bash
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/big-wealth/scanner:latest"
SECRETS="TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,\
TELEGRAM_CHANNEL_ID=TELEGRAM_CHANNEL_ID:latest,\
BINANCE_API_KEY=BINANCE_API_KEY:latest,\
BINANCE_SECRET_KEY=BINANCE_SECRET_KEY:latest,\
CLAUDE_CREDENTIALS=CLAUDE_CREDENTIALS:latest,\
/app/config/settings.yaml=SETTINGS_YAML:latest"

gcloud run deploy big-wealth-bot \
  --image=$IMAGE \
  --region=$REGION --project=$PROJECT_ID \
  --service-account=$SA_EMAIL \
  --min-instances=1 --max-instances=1 \
  --cpu=1 --memory=1Gi \
  --no-allow-unauthenticated \
  --port=8080 \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID" \
  --set-secrets="$SECRETS" \
  --command="python" \
  --args="-m,src.cloud.bot_server"
```

**ตรวจสอบว่า Bot ทำงาน:**
```bash
gcloud run services describe big-wealth-bot --region=$REGION --project=$PROJECT_ID \
  --format="value(status.url,status.conditions[0].status)"

# ดู logs ของ bot Service
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=big-wealth-bot" \
  --project=$PROJECT_ID --limit=30 \
  --format="table(timestamp, textPayload)"
```

> **หมายเหตุ:**
> - `--min-instances=1` ทำให้ bot warm ตลอด — polling ไม่หลุด
> - `--no-allow-unauthenticated` ปลอดภัย เพราะ bot poll ออกไปหา Telegram ไม่มี traffic เข้าจากภายนอก
> - หากต้องการเปลี่ยน config — แก้ `config/*.yaml` แล้ว push → workflow `update-config.yml` restart bot ให้อัตโนมัติ (ดู 6.2)

### 5.10 ตั้งค่า CI/CD (GitHub Actions)

ใน GitHub repository → Settings → Secrets → เพิ่ม:
- `WIF_PROVIDER` — Workload Identity Provider
- `WIF_SERVICE_ACCOUNT` — Service Account email
- `GCP_PROJECT_ID` — GCP project ID

หลังจากนั้นทุก `git push` ไปที่ `main` จะ build + deploy อัตโนมัติ

---

## 6. Maintenance & Updates

### 6.1 Update Code

```bash
# แก้ไข code → รัน tests
pytest tests/ -v

# Push → CI/CD deploy อัตโนมัติ
git push origin main

# หรือ build + deploy ด้วยมือ
gcloud builds submit \
  --tag $REGION-docker.pkg.dev/$PROJECT_ID/big-wealth/scanner:latest .

for JOB in scanner-us-stocks scanner-crypto paper-trade-updater; do
  gcloud run jobs update $JOB \
    --image $REGION-docker.pkg.dev/$PROJECT_ID/big-wealth/scanner:latest \
    --region=$REGION --project=$PROJECT_ID --quiet
done
```

### 6.2 Update Config (no Docker rebuild)

แก้ `config/settings.yaml` → commit → push `main` — workflow `.github/workflows/update-config.yml` จะ:

1. Upload `SETTINGS_YAML` version ใหม่ไปที่ Secret Manager
2. Restart Service `big-wealth-bot` ทันที (bot ใช้ config ใหม่ทันที)
3. Cloud Run Jobs (`scanner-us-stocks`, `scanner-crypto`, `paper-trade-updater`) ใช้ config ใหม่ในการรันรอบถัดไป

Workflow ฟังเฉพาะ `config/settings.yaml` — แก้ `watchlist_crypto.yaml` ไม่มี effect เพราะ file นั้นไม่ได้ถูก mount และ code ไม่ได้อ่าน (active fallback อยู่ใน `_FALLBACK_CRYPTO_SYMBOLS` ใน `src/agent/scanner.py`).

**Manual fallback (ถ้า workflow disabled):**

```bash
gcloud secrets versions add SETTINGS_YAML \
  --data-file=config/settings.yaml --project=$PROJECT_ID
gcloud run services update big-wealth-bot \
  --region=$REGION --project=$PROJECT_ID --quiet
```

ค่าหลักใน `settings.yaml` ที่มักปรับ:

```yaml
agent:
  us_stock_max_price: 50.0   # ราคาสูงสุด (USD)
  top_picks_count: 3         # signals ต่อวัน

signal:
  threshold: 3               # indicators ที่ต้อง fire (2-4)
```

> **หมายเหตุ:** การแก้ `src/**` ยังคงต้อง rebuild Docker (workflow `deploy.yml`) — section 6.1

### 6.3 Refresh Claude OAuth Token (ต้องทำทุก ~1 ปี)

OAuth token มีอายุ ~1 ปี เมื่อใกล้หมดอายุ:

```bash
# 1. Login ใหม่บน local
claude login

# 2. Update secret ใน Secret Manager
cat ~/.claude/.credentials.json | gcloud secrets versions add CLAUDE_CREDENTIALS \
  --data-file=- --project=$PROJECT_ID

# Cloud Run jobs จะใช้ token ใหม่อัตโนมัติในครั้งถัดไป
```

### 6.4 Update API Keys

```bash
echo -n "new_key_value" | gcloud secrets versions add SECRET_NAME \
  --data-file=- --project=$PROJECT_ID
```

### 6.5 ดู Logs

```bash
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=scanner-crypto" \
  --project=$PROJECT_ID --limit=50 \
  --format="table(timestamp, textPayload)"
```

### 6.6 Trigger Job ด้วยมือ

```bash
gcloud run jobs execute scanner-crypto --region=$REGION --project=$PROJECT_ID --wait
gcloud run jobs execute scanner-us-stocks --region=$REGION --project=$PROJECT_ID --wait
gcloud run jobs execute paper-trade-updater --region=$REGION --project=$PROJECT_ID --wait
```

### 6.7 หยุด/เปิด Scheduler

```bash
# หยุด
gcloud scheduler jobs pause scanner-crypto --location=$REGION --project=$PROJECT_ID
gcloud scheduler jobs pause scanner-us-stocks --location=$REGION --project=$PROJECT_ID

# เปิดใหม่
gcloud scheduler jobs resume scanner-crypto --location=$REGION --project=$PROJECT_ID
gcloud scheduler jobs resume scanner-us-stocks --location=$REGION --project=$PROJECT_ID
```

---

## 7. Troubleshooting

| ปัญหา | สาเหตุ | วิธีแก้ |
|---|---|---|
| `Claude Code CLI not found` | ยังไม่ได้ติดตั้ง | `npm install -g @anthropic-ai/claude-code` |
| `Claude CLI: Not logged in` (local) | ยังไม่ได้ login | `claude login` |
| `Claude CLI exited 1` (Cloud Run) | `CLAUDE_CREDENTIALS` ไม่ถูกต้องหรือหมดอายุ | ดูหัวข้อ 6.3 — refresh token |
| `[entrypoint] WARNING: CLAUDE_CREDENTIALS not set` | ลืม mount secret | เพิ่ม `--set-secrets=CLAUDE_CREDENTIALS=CLAUDE_CREDENTIALS:latest` |
| `No data returned` (US stock) | Symbol ผิดหรือ yfinance timeout | ตรวจ symbol, ลองใหม่ |
| `400 Bad Request` (Binance.th) | Pair ไม่มีใน Binance.th | ปกติไม่ควรเกิดอีก — `get_available_symbols()` filter discoveries แล้วก่อน fetch OHLCV. ถ้ายังเจอ ตรวจ logs `Discovery validation discovered=N valid_on_binanceth=M` |
| `Telegram: Chat not found` | Bot ไม่ได้เป็น Admin | เพิ่ม bot เป็น Admin ของ channel |
| `Telegram bot ไม่ตอบ command` (local) | Command ใน Channel ไม่ได้รับ | พิมพ์ใน **DM กับ bot** หรือ **Group** แทน |
| `Bot Service ไม่ตอบ commands` (Cloud) | Service down หรือ healthcheck fail | `gcloud run services describe big-wealth-bot --region=$REGION` → ดู `ready=True`; ดู logs ของ revision ล่าสุด |
| `Config update ไม่มีผล` | secrets ไม่ได้ mount หรือ workflow fail | ตรวจ `.github/workflows/update-config.yml` run; ตรวจ `gcloud secrets versions list SETTINGS_YAML` ตรงกับ `config/` ใน repo; restart bot Service ด้วยมือ |
| `run_bot_webhook ใช้งานยังไง` | code มี webhook function แต่ deploy เป็น polling | ไม่ต้องใช้ก็ได้ — `bot_server.py` เรียก `run_bot()` (polling). `run_bot_webhook()` เก็บไว้เป็น option หาก traffic โต |
| `Firestore: Permission denied` | ยังไม่ได้ auth | `gcloud auth application-default login` |
| `Firestore: requires composite index` | `.where()` + `.order_by()` ต่างกัน | sort ใน Python แทน |
| `ModuleNotFoundError: yaml` | `pyyaml` ไม่ได้ติดตั้ง | `pip install -r requirements.txt` |

---

## Quick Reference

```bash
# Tests
pytest tests/ -v

# Local scan
python -m src.cloud.main --mode scan --market crypto
python -m src.cloud.main --mode scan --market us

# Local TP advisor
python -m src.cloud.main --mode tp --symbol BTC/USDT --entry-date 2026-05-10 --entry-price 62000 --market crypto

# Local paper update
python -m src.cloud.main --mode update-paper

# Local Telegram bot
python -m src.notifications.telegram_bot

# Cloud: trigger scan
gcloud run jobs execute scanner-crypto --region=asia-southeast1 --project=$PROJECT_ID --wait

# Cloud: logs (Job)
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=scanner-crypto" \
  --project=$PROJECT_ID --limit=30 --format="table(timestamp, textPayload)"

# Cloud: deploy bot Service (one-time — full command in 5.9)
gcloud run deploy big-wealth-bot --image=$IMAGE ...

# Cloud: trigger config-only redeploy (after editing config/*.yaml)
gcloud run services update big-wealth-bot --region=$REGION --project=$PROJECT_ID --quiet

# Cloud: bot logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=big-wealth-bot" \
  --project=$PROJECT_ID --limit=30 --format="table(timestamp, textPayload)"
```
