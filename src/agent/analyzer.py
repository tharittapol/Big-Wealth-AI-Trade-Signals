from __future__ import annotations

import json
import re

from src.agent.models import CandidateTicker, TradeSignal
from src.cloud.claude_cli import run_claude
import structlog

logger = structlog.get_logger()

_SYSTEM_ANALYZER = """คุณคือผู้เชี่ยวชาญการเทรดมืออาชีพที่เชี่ยวชาญ Technical Analysis และ Fundamental Analysis

หน้าที่: วิเคราะห์ candidates ที่ให้มาและเลือก 3 ตัวที่ดีที่สุดสำหรับ Swing Trade 1–5 วัน

เกณฑ์การเลือก (เรียงตามความสำคัญ):
1. Risk:Reward ratio สูง — TP/SL ≥ 2:1
2. Indicators align ชัดเจน — RSI oversold, MACD bullish cross, BB lower touch, EMA cross
3. มี catalyst หรือ news บวกสนับสนุน
4. Volume ยืนยัน momentum
5. แนวรับ-แนวต้านชัดเจน

สำหรับแต่ละ signal ที่เลือก กำหนด:
- entry: ราคาเข้าซื้อที่เหมาะสม (limit order)
- tp: Take Profit ที่แนวต้านถัดไป (R:R ≥ 2:1)
- sl: Stop Loss ต่ำกว่า swing low ล่าสุด ~1-2%
- confidence: "high" | "medium" | "low"
- timeframe_days: จำนวนวันที่คาดหวัง (1-5)
- reasoning_th: เหตุผล 2-3 ประโยคเป็นภาษาไทย ระบุ indicator สำคัญ + catalyst ถ้ามี"""

# ── TP/SL fallback tables (used when Claude CLI is unavailable) ───────────────
_TP_PCT: dict[str, dict[int, float]] = {
    "us_stock": {4: 0.08, 3: 0.06},
    "crypto":   {4: 0.12, 3: 0.08},
}
_TP_PCT_DEFAULT: dict[str, float] = {"us_stock": 0.04, "crypto": 0.06}
_SL_PCT = 0.05
_TIMEFRAME_DAYS: dict[str, int] = {"us_stock": 3, "crypto": 2}

_JSON_INSTRUCTION = (
    '\n\nตอบด้วย JSON เท่านั้น (ห้ามมีข้อความอื่น) ในรูปแบบนี้:\n'
    '{"signals": [{'
    '"symbol": "TICKER", '
    '"entry": 0.00, '
    '"tp": 0.00, '
    '"sl": 0.00, '
    '"confidence": "high", '
    '"timeframe_days": 3, '
    '"reasoning_th": "เหตุผลภาษาไทย"'
    '}]}\n\n'
    'กฎเขียน JSON:\n'
    '- ห้ามใช้ double-quote (") ภายในค่า reasoning_th — ถ้าต้องอ้างชื่อ ticker ให้ใช้วงเล็บไทย 「」 หรือไม่ใส่เครื่องหมายคำพูดเลย\n'
    '- ห้ามมี trailing comma ก่อน } หรือ ]\n'
    '- ใช้ ASCII straight quote (") เท่านั้น — ห้ามใช้ smart quotes\n'
    '- ทุก object ใน array signals ต้องคั่นด้วย ","\n'
)


def pick_top3(candidates: list[CandidateTicker], market: str) -> list[TradeSignal]:
    """
    Select top 3 trade signals for the given market.
    Primary: calls Claude via CLI for AI analysis + Thai reasoning.
    Fallback: score-based selection when CLI is unavailable.
    """
    if not candidates:
        logger.warning("No candidates to analyze", market=market)
        return []

    prompt = _build_prompt(candidates, market) + _JSON_INSTRUCTION
    try:
        response = run_claude(prompt, system_prompt=_SYSTEM_ANALYZER, model="opus")
        signals = _parse_json_response(response, market)
        if signals:
            logger.info("AI signals selected", market=market, count=len(signals),
                        symbols=[s.symbol for s in signals])
            return signals
        logger.warning("AI response parsed but produced no signals, using fallback")
    except Exception as e:
        logger.error("Claude CLI analyzer failed, using score-based fallback",
                     market=market, error=str(e))

    return _score_based_fallback(candidates, market)


def _build_prompt(candidates: list[CandidateTicker], market: str) -> str:
    lines = [f"วิเคราะห์ {len(candidates)} candidates สำหรับตลาด {market.upper()} แล้วเลือก top 3:\n"]
    for c in candidates:
        ind = c.indicators
        lines.append(f"### {c.symbol}  (ราคา: {c.current_price:.4f})")
        lines.append(f"Signal score: {ind.get('score', 0)}/4  |  Fired: {ind.get('fired', [])}")
        lines.append(
            f"RSI: {ind.get('RSI_14', 'N/A')}  |  MACD hist: {ind.get('MACDh_12_26_9', 'N/A')}  |  "
            f"EMA9: {ind.get('EMA_9', 'N/A')}  |  EMA21: {ind.get('EMA_21', 'N/A')}"
        )
        lines.append(
            f"BB lower: {ind.get('BBL_20_2.0', 'N/A')}  |  BB upper: {ind.get('BBU_20_2.0', 'N/A')}"
        )
        # News/catalyst — buffered from discovery phase (no re-search)
        if c.news:
            news_lines = []
            for item in c.news:
                title = item.get("title", "")
                catalyst = item.get("catalyst", "")
                if catalyst:
                    news_lines.append(f"  • {title} [{catalyst}]")
                elif title:
                    news_lines.append(f"  • {title}")
            if news_lines:
                lines.append("News/Catalyst:\n" + "\n".join(news_lines))
        else:
            lines.append("News: ไม่มีข่าว")
        lines.append("")
    return "\n".join(lines)


def _parse_json_response(text: str, market: str) -> list[TradeSignal]:
    """Extract JSON from Claude's response and build TradeSignal list."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        logger.warning("No JSON found in analyzer response")
        return []

    raw = match.group()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        try:
            from json_repair import loads as repair_loads
            data = repair_loads(raw)
            logger.info("Analyzer JSON repaired", original_error=str(e))
        except Exception as repair_err:
            logger.warning(
                "JSON decode failed even after repair",
                error=str(e),
                repair_error=str(repair_err),
            )
            return []

    if not isinstance(data, dict):
        logger.warning("Repaired JSON is not a dict", type=type(data).__name__)
        return []

    signals: list[TradeSignal] = []
    for s in data.get("signals", []):
        try:
            signals.append(TradeSignal(
                symbol=s["symbol"],
                market=market,
                entry=float(s["entry"]),
                tp=float(s["tp"]),
                sl=float(s["sl"]),
                confidence=s["confidence"],
                timeframe_days=int(s["timeframe_days"]),
                reasoning_th=s["reasoning_th"],
            ))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Skipping malformed signal", error=str(e), raw=s)
    return signals


# ── Score-based fallback ──────────────────────────────────────────────────────

def _score_based_fallback(candidates: list[CandidateTicker], market: str) -> list[TradeSignal]:
    """Pick top 3 by indicator score when Claude CLI is unavailable."""
    ranked = sorted(candidates, key=lambda c: c.indicators.get("score", 0), reverse=True)
    return [_build_signal(c, market) for c in ranked[:3]]


def _build_signal(candidate: CandidateTicker, market: str) -> TradeSignal:
    entry = candidate.current_price
    score = candidate.indicators.get("score", 0)

    tp_map = _TP_PCT.get(market, _TP_PCT["us_stock"])
    tp_pct = tp_map.get(score, _TP_PCT_DEFAULT.get(market, 0.05))
    tp = round(entry * (1 + tp_pct), 4)

    bb_lower = candidate.indicators.get("BBL_20_2.0") or 0.0
    hard_stop = entry * (1 - _SL_PCT)
    sl = round(max(bb_lower, hard_stop), 4) if bb_lower and 0 < bb_lower < entry else round(hard_stop, 4)

    if score >= 4:
        confidence = "high"
    elif score >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return TradeSignal(
        symbol=candidate.symbol,
        market=market,
        entry=entry,
        tp=tp,
        sl=sl,
        confidence=confidence,
        timeframe_days=_TIMEFRAME_DAYS.get(market, 3),
        reasoning_th=_generate_reasoning_th(candidate),
    )


def _generate_reasoning_th(candidate: CandidateTicker) -> str:
    fired: list[str] = candidate.indicators.get("fired", [])
    score: int = candidate.indicators.get("score", 0)
    rsi = candidate.indicators.get("RSI_14")

    parts: list[str] = []
    for item in fired:
        item_lower = item.lower()
        if "rsi" in item_lower:
            rsi_str = f"{rsi:.1f}" if rsi is not None else "?"
            parts.append(f"RSI={rsi_str} อยู่ใน oversold zone — มีโอกาส bounce")
        elif "macd" in item_lower:
            parts.append("MACD ตัดขึ้น (bullish cross) — momentum กำลังเปลี่ยนทิศ")
        elif "bb" in item_lower or "lower" in item_lower:
            parts.append("ราคาอยู่ที่ Bollinger Band ล่าง — แนวรับทางสถิติ")
        elif "ema" in item_lower:
            parts.append("EMA 9 ตัดขึ้นเหนือ EMA 21 — short-term trend กลับมา bullish")

    if not parts:
        return f"ผ่านเกณฑ์พื้นฐาน score {score}/4 — indicator ยังไม่ fire ชัดเจน"
    return f"Score {score}/4 | " + " | ".join(parts)
