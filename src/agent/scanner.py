"""Daily market scanner — 3-phase: Discovery → Data → Candidates.

Phase 1 (Discovery): Claude Opus 4.7 + WebSearch finds candidates with news buffered.
Phase 2 (Data): Fetch OHLCV + compute indicators for each discovered symbol.
Phase 3 (Build): Assemble CandidateTicker list; news from discovery is already buffered.
"""
from __future__ import annotations

import json
import re

import structlog
import yaml

from src.agent.models import CandidateTicker
from src.cloud.claude_cli import run_claude
from src.data.crypto import fetch_multiple as crypto_fetch_multiple
from src.data.crypto import fetch_top_volume_pairs
from src.data.crypto import get_available_symbols
from src.data.us_stocks import fetch_multiple
from src.indicators.technical import add_indicators, score_signal

logger = structlog.get_logger()

_FALLBACK_US_SYMBOLS = [
    "SOFI", "PLTR", "NIO", "RIVN", "LCID", "UWMC", "OPEN", "HOOD", "CLOV", "DKNG",
    "SPCE", "SKLZ", "WISH", "CRON", "TLRY",
]

_FALLBACK_CRYPTO_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
]

_SYSTEM_DISCOVERY_US = (
    "คุณคือนักวิเคราะห์หุ้น US ที่เชี่ยวชาญการค้นหาโอกาสลงทุนจากข่าวสารล่าสุด "
    "ตอบด้วย JSON เท่านั้น ห้ามมีข้อความอื่น"
)

_SYSTEM_DISCOVERY_CRYPTO = (
    "คุณคือนักวิเคราะห์ crypto ที่เชี่ยวชาญการค้นหาโอกาสลงทุนจากข่าวสารล่าสุดบน Binance "
    "ตอบด้วย JSON เท่านั้น ห้ามมีข้อความอื่น"
)


def _extract_json_candidates(text: str) -> list[dict]:
    """Extract candidates list from Claude text response (handles markdown fences)."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group())
    return data.get("candidates", [])


def _discover_us_candidates(max_candidates: int = 15, price_cap: float = 50.0) -> list[dict]:
    """Phase 1: Claude Opus 4.7 + WebSearch → list[{symbol, news_summary, catalyst}].

    Falls back to _FALLBACK_US_SYMBOLS on any error or empty response.
    """
    prompt = (
        f"ค้นหาหุ้น US ที่มีโอกาสขึ้นในอีก 3-5 วัน จำนวน {max_candidates} ตัว\n\n"
        f"เกณฑ์:\n"
        f"- ราคาปัจจุบัน ≤ ${price_cap} ต่อหุ้น (สำคัญมาก ห้ามเกิน)\n"
        f"- มี catalyst บวกล่าสุด: earnings beat, analyst upgrade, product launch, partnership, M&A\n"
        f"- Volume และ momentum สูงขึ้น\n"
        f"- เหมาะสำหรับ swing trade 1-5 วัน\n\n"
        f'ตอบด้วย JSON: {{"candidates": [{{"symbol": "SOFI", '
        f'"news_summary": "สรุปข่าวสำคัญ 1-2 ประโยคภาษาไทย", '
        f'"catalyst": "ประเภท catalyst"}}]}}'
    )
    try:
        response = run_claude(
            prompt,
            system_prompt=_SYSTEM_DISCOVERY_US,
            model="opus",
            enable_web_search=True,
            timeout=300,
        )
        candidates = _extract_json_candidates(response)
        if candidates:
            logger.info("US discovery complete", count=len(candidates))
            return candidates
        logger.warning("US discovery returned empty list, using fallback")
    except Exception as exc:
        logger.warning("US discovery failed, using fallback", error=str(exc))

    return [{"symbol": s, "news_summary": "", "catalyst": ""} for s in _FALLBACK_US_SYMBOLS]


def _discover_crypto_candidates(max_candidates: int = 15) -> list[dict]:
    """Phase 1: Claude Opus 4.7 + WebSearch → list[{symbol, news_summary, catalyst}].

    Returns empty list on failure — caller falls back to Binance top volume.
    """
    prompt = (
        f"ค้นหา crypto trading pairs บน Binance ที่มีโอกาสขึ้นในอีก 3-5 วัน จำนวน {max_candidates} pairs\n\n"
        f"เกณฑ์:\n"
        f"- ต้องเป็น pair ที่ซื้อขายได้บน Binance จริง (format: BTC/USDT)\n"
        f"- มี catalyst บวก: network upgrade, mainnet launch, exchange listing, ETF approval, partnership\n"
        f"- Volume 24h สูงและ momentum ขาขึ้น\n\n"
        f'ตอบด้วย JSON: {{"candidates": [{{"symbol": "BTC/USDT", '
        f'"news_summary": "สรุปข่าวสำคัญ 1-2 ประโยคภาษาไทย", '
        f'"catalyst": "ประเภท catalyst"}}]}}'
    )
    try:
        response = run_claude(
            prompt,
            system_prompt=_SYSTEM_DISCOVERY_CRYPTO,
            model="opus",
            enable_web_search=True,
            timeout=300,
        )
        candidates = _extract_json_candidates(response)
        if candidates:
            logger.info("Crypto discovery complete", count=len(candidates))
            return candidates
        logger.warning("Crypto discovery returned empty list")
    except Exception as exc:
        logger.warning("Crypto discovery failed", error=str(exc))

    return []


def _load_settings() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def _df_to_records(df) -> list[dict]:
    records = df.reset_index().to_dict(orient="records")
    # Convert Timestamp values to ISO strings for JSON serialisation
    for rec in records:
        for k, v in rec.items():
            try:
                rec[k] = v.isoformat()
            except AttributeError:
                pass
    return records


def scan_us_stocks(
    max_candidates: int = 15,
    price_cap: float | None = None,
) -> list[CandidateTicker]:
    """Scan US stocks via 3-phase pipeline.

    Phase 1: Claude Opus 4.7 + WebSearch discovers candidates with buffered news.
    Phase 2: Fetch OHLCV + compute indicators for each candidate.
    Phase 3: Filter by price cap; assemble CandidateTicker with buffered news.

    If price_cap is None, reads agent.us_stock_max_price from settings.yaml.
    """
    cfg = _load_settings()
    period = cfg["data"]["us_stocks"]["period"]
    min_rows = cfg["data"]["us_stocks"]["min_rows"]
    if price_cap is None:
        price_cap = float(cfg["agent"]["us_stock_max_price"])

    # Phase 1: Discovery (with fallback at scan level too in case mock raises)
    try:
        discovered = _discover_us_candidates(max_candidates, price_cap)
    except Exception as exc:
        logger.warning("Discovery raised in scan_us_stocks, using fallback", error=str(exc))
        discovered = [{"symbol": s, "news_summary": "", "catalyst": ""} for s in _FALLBACK_US_SYMBOLS]

    symbols = [d["symbol"] for d in discovered]
    news_buffer: dict[str, dict] = {d["symbol"]: d for d in discovered}

    # Phase 2: Data fetch
    ohlcv_map = fetch_multiple(symbols, period=period)

    # Phase 3: Build candidates
    candidates: list[CandidateTicker] = []
    for symbol, df in ohlcv_map.items():
        if df is None or len(df) < min_rows:
            logger.debug("Skipping symbol: insufficient data", symbol=symbol)
            continue

        current_price = float(df["close"].iloc[-1])
        if current_price > price_cap:
            logger.debug("Skipping symbol: above price cap", symbol=symbol, price=current_price)
            continue

        df = add_indicators(df)
        sig = score_signal(df, symbol)

        # Build news list from buffered discovery data
        discovery = news_buffer.get(symbol, {})
        news: list[dict] = []
        if discovery.get("news_summary"):
            news.append({
                "title": discovery["news_summary"],
                "catalyst": discovery.get("catalyst", ""),
            })

        last_row = df.iloc[-1]
        indicators = {
            "score": sig.score,
            "fired": sig.fired,
            "RSI_14": round(float(last_row.get("RSI_14", 0) or 0), 2),
            "MACDh_12_26_9": round(float(last_row.get("MACDh_12_26_9", 0) or 0), 4),
            "BBU_20_2.0": round(float(last_row.get("BBU_20_2.0", 0) or 0), 4),
            "BBL_20_2.0": round(float(last_row.get("BBL_20_2.0", 0) or 0), 4),
            "EMA_9": round(float(last_row.get("EMA_9", 0) or 0), 4),
            "EMA_21": round(float(last_row.get("EMA_21", 0) or 0), 4),
        }

        candidates.append(CandidateTicker(
            symbol=symbol,
            market="us_stock",
            current_price=current_price,
            indicators=indicators,
            news=news,
            ohlcv_recent=_df_to_records(df.tail(10)),
        ))

    logger.info("US scan complete", candidates=len(candidates))
    return candidates


def scan_crypto(min_score: int = 0) -> list[CandidateTicker]:
    """Scan crypto via 3-phase pipeline.

    Phase 1: Claude Opus 4.7 + WebSearch discovers candidates with buffered news.
            Falls back to Binance top volume if discovery fails.
    Phase 2: Fetch OHLCV + compute indicators.
    Phase 3: Filter by min_score; assemble CandidateTicker with buffered news.
    """
    cfg = _load_settings()
    timeframe = cfg["data"]["crypto"]["timeframe"]
    limit = cfg["data"]["crypto"]["limit"]
    min_rows = cfg["data"]["crypto"]["min_rows"]
    top_volume_limit = cfg["data"]["crypto"]["top_volume_limit"]

    # Phase 1: Discovery
    discovered = _discover_crypto_candidates()

    # Validate discovered symbols against what Binance.th actually supports
    available = get_available_symbols()
    if available:
        validated = [d for d in discovered if d["symbol"] in available]
        logger.info(
            "Discovery validation",
            discovered=len(discovered),
            valid_on_binanceth=len(validated),
        )
    else:
        validated = discovered  # exchangeInfo unavailable; try all and let fetch handle errors

    news_buffer: dict[str, dict] = {d["symbol"]: d for d in validated}

    # If fewer than 5 validated symbols, supplement with Binance.th top-volume pairs
    _MIN_SYMBOLS = 5
    if len(validated) < _MIN_SYMBOLS:
        logger.info("Too few validated symbols, supplementing with top-volume pairs", count=len(validated))
        top_pairs = fetch_top_volume_pairs(limit=top_volume_limit) or _FALLBACK_CRYPTO_SYMBOLS
        existing = {d["symbol"] for d in validated}
        extra = [p for p in top_pairs if p not in existing]
        symbols = [d["symbol"] for d in validated] + extra
    else:
        symbols = [d["symbol"] for d in validated]

    # Phase 2: Data fetch
    ohlcv_map = crypto_fetch_multiple(symbols, timeframe=timeframe, limit=limit, min_rows=min_rows)
    if not ohlcv_map:
        dropped = [s for s in symbols if s not in ohlcv_map]
        logger.warning(
            "All crypto OHLCV fetches dropped — symbols may be too new for >=min_rows days of data",
            requested=len(symbols),
            min_rows=min_rows,
            dropped_sample=dropped[:5],
        )
    else:
        logger.info("Crypto OHLCV fetched", symbols_with_data=len(ohlcv_map), requested=len(symbols))

    # Phase 3: Build candidates
    candidates: list[CandidateTicker] = []
    for symbol, df in ohlcv_map.items():
        if df is None or len(df) < min_rows:
            continue

        df = add_indicators(df)
        sig = score_signal(df, symbol)

        if sig.score < min_score:
            continue

        current_price = float(df["close"].iloc[-1])

        discovery = news_buffer.get(symbol, {})
        news: list[dict] = []
        if discovery.get("news_summary"):
            news.append({
                "title": discovery["news_summary"],
                "catalyst": discovery.get("catalyst", ""),
            })

        last_row = df.iloc[-1]
        indicators = {
            "score": sig.score,
            "fired": sig.fired,
            "RSI_14": round(float(last_row.get("RSI_14", 0) or 0), 2),
            "MACDh_12_26_9": round(float(last_row.get("MACDh_12_26_9", 0) or 0), 4),
            "BBU_20_2.0": round(float(last_row.get("BBU_20_2.0", 0) or 0), 4),
            "BBL_20_2.0": round(float(last_row.get("BBL_20_2.0", 0) or 0), 4),
            "EMA_9": round(float(last_row.get("EMA_9", 0) or 0), 4),
            "EMA_21": round(float(last_row.get("EMA_21", 0) or 0), 4),
        }

        candidates.append(CandidateTicker(
            symbol=symbol,
            market="crypto",
            current_price=current_price,
            indicators=indicators,
            news=news,
            ohlcv_recent=_df_to_records(df.tail(10)),
        ))

    logger.info("Crypto scan complete", candidates=len(candidates))
    return candidates
