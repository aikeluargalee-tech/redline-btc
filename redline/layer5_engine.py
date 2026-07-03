"""Layer 5 — Analysis Engine (Enriched)

Feeds all layers with market analysis data from the BTC Data Packet
plus enriched signals from pipeline files (crash, structural, sentiment, liquidity).

Produces: momentum, leverage, funding bias, volatility regime, sentiment overlay,
support/resistance levels, liquidity health, crash risk.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def analyze_enriched(enriched: dict) -> dict:
    """Analyze market structure from enriched pipeline data.

    Args:
        enriched: Dict from packet_source.fetch_enriched() with all signals.

    Returns:
        Dictionary with detailed analysis.
    """
    btc_price = enriched.get("btc_price", 62000)

    # --- Momentum from CVD + correlation + volume ---
    cvd_24h = enriched.get("cvd_24h", 0)
    taker_ratio = enriched.get("taker_ratio_24h", 1.0)
    corr_r = enriched.get("correlation_r", 0.0)
    realized_vol = enriched.get("realized_vol_1h_pct", 0.0)

    # Momentum direction
    if isinstance(cvd_24h, (int, float)):
        if cvd_24h > 200:
            momentum = "bullish"
        elif cvd_24h < -200:
            momentum = "bearish"
        elif cvd_24h > 0:
            momentum = "slightly_bullish"
        elif cvd_24h < 0:
            momentum = "slightly_bearish"
        else:
            momentum = "neutral"
    else:
        momentum = "neutral"

    # --- Volatility regime ---
    if realized_vol > 80:
        vol_regime = "high"
    elif realized_vol > 50:
        vol_regime = "elevated"
    elif realized_vol > 20:
        vol_regime = "normal"
    else:
        vol_regime = "low"

    # --- Leverage / OI ---
    oi_change = enriched.get("oi_change_24h", 0)
    oi_abs = enriched.get("oi_absolute_usd_billions", 0)
    if isinstance(oi_change, (int, float)):
        if abs(oi_change) > 3.0:
            leverage = "extreme"
        elif abs(oi_change) > 1.0:
            leverage = "elevated"
        else:
            leverage = "normal"
    else:
        leverage = "normal"

    # --- Funding ---
    funding = enriched.get("funding_rate", 0)
    if isinstance(funding, (int, float)):
        if funding < -0.0005:
            funding_bias = "short"
        elif funding > 0.0005:
            funding_bias = "long"
        else:
            funding_bias = "neutral"
    else:
        funding_bias = "neutral"

    # --- Sentiment ---
    fng = enriched.get("fng_value", 0)
    fng_value = 0
    if isinstance(fng, (int, float)):
        if fng <= 15:
            sentiment_label = "extreme_fear"
        elif fng <= 35:
            sentiment_label = "fear"
        elif fng <= 55:
            sentiment_label = "neutral"
        elif fng <= 75:
            sentiment_label = "greed"
        else:
            sentiment_label = "extreme_greed"
    else:
        sentiment_label = "unknown"
        fng_value = fng if isinstance(fng, (int, float)) else 0

    # --- S/R proximity ---
    sr_1d_support = enriched.get("sr_1d_support")
    sr_1d_resistance = enriched.get("sr_1d_resistance")
    sr_1h_support = enriched.get("sr_1h_support")
    sr_1h_resistance = enriched.get("sr_1h_resistance")

    nearest_support = sr_1d_support or sr_1h_support or 0
    nearest_resistance = sr_1d_resistance or sr_1h_resistance or 0
    support_dist_pct = 0
    resistance_dist_pct = 0

    if nearest_support and btc_price > 0:
        support_dist_pct = ((btc_price - nearest_support) / btc_price) * 100
    if nearest_resistance and btc_price > 0:
        resistance_dist_pct = ((nearest_resistance - btc_price) / btc_price) * 100

    # --- Liquidity health ---
    liq_verdict = enriched.get("liquidity_verdict", "UNKNOWN")
    if liq_verdict == "HEALTHY":
        liquidity_health = "healthy"
    elif liq_verdict in ("STRESSED", "CAUTION"):
        liquidity_health = "stressed"
    elif liq_verdict == "CRITICAL":
        liquidity_health = "critical"
    else:
        liquidity_health = "unknown"

    # --- Crash / Black Swan risk ---
    crash_score = enriched.get("crash_score", 0)
    black_swan_score = enriched.get("black_swan_score", 0)

    if black_swan_score >= 10 or crash_score >= 4:
        tail_risk = "high"
    elif black_swan_score >= 5 or crash_score >= 2:
        tail_risk = "elevated"
    else:
        tail_risk = "low"

    # --- Cross-asset correlation signal ---
    if isinstance(corr_r, (int, float)):
        if corr_r < -0.7:
            correlation_signal = "strong_divergence"
        elif corr_r < -0.4:
            correlation_signal = "divergence"
        elif corr_r > 0.7:
            correlation_signal = "risk_on"
        elif corr_r > 0.4:
            correlation_signal = "risk_on_weak"
        else:
            correlation_signal = "neutral"
    else:
        correlation_signal = "unknown"

    # --- Final assessment ---
    atr_1d = enriched.get("atr_1d_pct", 0)
    atr_1h = enriched.get("atr_1h_pct", 0)

    return {
        "momentum": momentum,
        "leverage": leverage,
        "funding_bias": funding_bias,
        "liquidation_risk": bool(nearest_support or nearest_resistance),
        "volume_profile": enriched.get("vp_state", "unknown"),
        "volatility_regime": vol_regime,
        "realized_vol_1h_pct": realized_vol,
        "sentiment": sentiment_label,
        "fng_value": fng_value if isinstance(fng, (int, float)) else fng,
        "tail_risk": tail_risk,
        "crash_score": crash_score,
        "black_swan_score": black_swan_score,
        "liquidity_health": liquidity_health,
        "liquidity_verdict": liq_verdict,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "support_distance_pct": round(support_dist_pct, 2),
        "resistance_distance_pct": round(resistance_dist_pct, 2),
        "atr_1d_pct": round(atr_1d, 2) if isinstance(atr_1d, (int, float)) else 0.0,
        "atr_1h_pct": round(atr_1h, 2) if isinstance(atr_1h, (int, float)) else 0.0,
        "btc_equity_correlation": corr_r,
        "correlation_signal": correlation_signal,
        "oi_change_24h_pct": oi_change if isinstance(oi_change, (int, float)) else 0.0,
        "cot_signal": enriched.get("cot_signal", "NEUTRAL"),
        "funding_signal": enriched.get("funding_signal", "NEUTRAL"),
        "taker_buy_ratio": enriched.get("taker_buy_ratio", 0.5),
    }


def check_enriched_risk_signals(enriched: dict) -> dict:
    """Check enriched pipeline data for additional risk signals.

    These supplement the 4 core L1 triggers and feed into L1 assessment.

    Returns dict with risk verdict and any triggered signals.
    """
    triggered = []
    risk_level = "normal"

    crash_score = enriched.get("crash_score", 0)
    black_swan = enriched.get("black_swan_score", 0)
    liquidity = enriched.get("liquidity_verdict", "HEALTHY")
    dxy = enriched.get("dxy", 100.0)
    realized_vol = enriched.get("realized_vol_1d_pct", 0)

    if crash_score >= 3:
        triggered.append(f"Crash precursor elevated ({crash_score}/5)")
        risk_level = "elevated"
    if black_swan >= 8:
        triggered.append(f"Black swan risk elevated ({black_swan}/17)")
        risk_level = "elevated"
    if liquidity in ("STRESSED", "CRITICAL"):
        triggered.append(f"Liquidity {liquidity}")
        risk_level = "elevated"
    if isinstance(dxy, (int, float)) and dxy > 106:
        triggered.append(f"DXY strength ({dxy}) — dollar stress")
        risk_level = "elevated"
    if realized_vol > 100:
        triggered.append(f"Extreme volatility ({realized_vol}%)")
        risk_level = "elevated"

    if len(triggered) >= 3:
        risk_level = "critical"

    return {
        "risk_level": risk_level,
        "triggered_signals": triggered,
        "crash_score": crash_score,
        "black_swan_score": black_swan,
        "liquidity_verdict": liquidity,
        "dxy": dxy,
    }
