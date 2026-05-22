# Big-wealth — AI Trading Signals Bot

> **AI-powered daily trading signals for US Stocks and Crypto**  
> ค้นหาโอกาสลงทุนด้วย Claude AI + Technical Analysis ทุกวัน

---

## ⚡ รับสัญญาณเทรดก่อนใคร — เข้าร่วม Telegram กลุ่มของเรา

ระบบ AI วิเคราะห์หุ้น US และ Crypto ทุกวัน เวลา **20:00 น.** — ส่งสัญญาณ BUY พร้อม Entry, TP, SL และเหตุผลภาษาไทย

---

## 📊 ตัวอย่าง Signal ที่ได้รับ

```
🔔 BUY SIGNAL — SOFI (US Stock)

Entry:       $10.50
TP:          $13.00  (+23.8%)
SL:          $9.50   (-9.5%)
Timeframe:   3 วัน
Confidence:  สูง

📊 Indicators:
  RSI: 35 (oversold)
  MACD: Bullish crossover
  BB: Price at lower band
  EMA 9>21: Bullish crossover

🤖 เหตุผล:
  SOFI ราคาทดสอบแนวรับแข็งแกร่งที่ $10 RSI เข้าโซน oversold
  MACD กำลัง cross ขึ้น มีข่าวผลประกอบการ Q1 ดีกว่าคาด 37%
  นักวิเคราะห์ปรับ target ราคาขึ้น — momentum เริ่มกลับตัว

#SOFI #USStock #BuySignal
```

## 🤖 ระบบทำงานอย่างไร

```
ทุกวัน 20:00 น. (UTC+7)
         │
         ▼
  🔍 DISCOVERY PHASE
  Claude AI + Web Search
  ค้นหาหุ้น/crypto จากข่าวล่าสุด
  (Earnings beats, Analyst upgrades,
   ETF inflows, Protocol upgrades)
         │
         ▼
  📈 DATA PHASE  
  ดึงข้อมูล OHLCV จริง
  คำนวณ RSI, MACD, Bollinger Bands, EMA
         │
         ▼
  🧠 ANALYSIS PHASE
  Claude AI วิเคราะห์ indicator + ข่าว
  คัดเลือก Top 3 โอกาสที่ดีที่สุด (3 US stock / 3 Crypto)
         │
         ▼
  📱 TELEGRAM
  ส่ง Signal Cards พร้อมเหตุผลภาษาไทย
```

**US Stocks:** วิเคราะห์ news catalysts และ ราคา ≤ $200 (ปรับเปลี่ยนได้) — Mon–Fri  
**Crypto:** วิเคราะห์ news catalysts หรือ Binance top pairs — ทุกวัน

---

## 📱 คำสั่ง Telegram Bot

| Command | ผลลัพธ์ |
|---|---|
| `/positions` | ดู paper positions ที่เปิดอยู่ + P&L ปัจจุบัน |
| `/pnl` | สรุป Win Rate, กำไร/ขาดทุนสะสม |
| `/history` | ประวัติ 10 trade ล่าสุด |
| `/tp SOFI 2026-05-18 10.50 us_stock` | AI แนะนำ TP levels สำหรับ position ที่ถืออยู่ |

---

## 🛠️ Tech Stack (Open Source)

| Layer | Technology |
|---|---|
| AI Discovery | Claude Opus 4.7 + WebSearch (Claude Code CLI) |
| AI Analysis | Claude Opus 4.7 (Thai-language reasoning) |
| US Stock Data | Yahoo Finance (`yfinance`) |
| Crypto Data | Binance.th REST API (`httpx`) |
| Technical Analysis | RSI, MACD, Bollinger Bands, EMA/SMA (`ta` library) |
| Notifications | Telegram Bot |
| Cloud | Google Cloud Run + Cloud Scheduler |
| Storage | Google Cloud Firestore (paper trading) |
| Language | Python 3.11 |

---

## 🚀 Self-Hosting (สำหรับนักพัฒนา)

ต้องการรันระบบบน GCP เอง — ดูคู่มือที่ [RUNBOOK.md](RUNBOOK.md)

**Requirements:**
- Claude Code CLI (Pro/Max plan) — ใช้แทน API key
- Telegram Bot Token
- Binance API Key (Read Only)
- Google Cloud Project (Firestore + Cloud Run)

```bash
git clone https://github.com/tharittapol/big-wealth.git
# ดูขั้นตอน setup ทั้งหมดใน RUNBOOK.md
```

---

## 📈 Track Record (Paper Trading)

ระบบรัน Paper Trading อัตโนมัติเพื่อติดตาม performance:

- **เปิด position:** ทุกครั้งที่ส่ง signal
- **ปิด position:** เมื่อถึง TP หรือ SL
- **ดู P&L:** ผ่านคำสั่ง `/pnl` ใน Telegram

> Paper Trading ใช้เงินสมมติ $5,000 เพื่อ track performance ของ signal — ไม่ใช่เงินจริง

---

## ⚠️ ข้อแม้และความเสี่ยง

- Signal ทั้งหมดเป็นเพียงการวิเคราะห์ — **ไม่ใช่คำแนะนำทางการเงิน**
- การลงทุนมีความเสี่ยง อาจได้รับเงินคืนน้อยกว่าลงทุน
- ระบบ AI มีโอกาสผิดพลาด — ควร **ตัดสินใจเองก่อนลงทุนทุกครั้ง**
- Swing trade 1–5 วัน เหมาะกับผู้ที่รับความเสี่ยงได้

---

## 📞 ติดต่อ

- **Telegram Username:** [@TeleBig007](https://t.me/TeleBig007)
- **เข้าร่วม Telegram:** ติดต่อผ่าน Telegram DM

---

*Powered by Claude AI + Python — Running 24/7 on Google Cloud*
