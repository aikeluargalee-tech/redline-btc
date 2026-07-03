"""Unit tests for Layer 5 — Enriched Analysis Engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer5_engine import analyze_enriched, check_enriched_risk_signals


def test_analyze_enriched_returns_momentum_leverage_sentiment():
    """analyze_enriched returns momentum, leverage, and sentiment fields."""
    enriched_data = {
        "btc_price": 61708,
        "cvd_24h": 250,
        "taker_ratio_24h": 1.1,
        "correlation_r": 0.5,
        "realized_vol_1h_pct": 30.0,
        "oi_change_24h_pct": 1.5,
        "oi_absolute_usd_billions": 15.0,
        "oi_trend": "increasing",
        "funding_rate": 0.0003,
        "fng_value": 45,
        "sr_1d_support": 60000,
        "sr_1d_resistance": 63000,
        "crash_score": 1,
        "black_swan_score": 3,
        "liquidity_verdict": "HEALTHY",
    }
    result = analyze_enriched(enriched_data)
    
    assert "momentum" in result
    assert "leverage" in result
    assert "sentiment" in result
    assert result["momentum"] in ["bullish", "bearish", "slightly_bullish", "slightly_bearish", "neutral"]
    assert result["leverage"] in ["normal", "elevated", "extreme"]
    assert isinstance(result["sentiment"], str)


def test_check_enriched_risk_signals_returns_normal():
    """check_enriched_risk_signals returns normal when no risk signals present."""
    enriched_data = {
        "crash_score": 1,
        "black_swan_score": 3,
        "liquidity_verdict": "HEALTHY",
        "dxy": 103.0,
        "realized_vol_1d_pct": 50.0,
    }
    result = check_enriched_risk_signals(enriched_data)
    
    assert result["risk_level"] == "normal"
    assert len(result["triggered_signals"]) == 0
    assert "crash_score" in result
    assert "black_swan_score" in result
    assert "liquidity_verdict" in result


def test_fng_value_is_numeric():
    """fng_value in analyze_enriched output is numeric."""
    enriched_data = {
        "btc_price": 61708,
        "cvd_24h": 0,
        "taker_ratio_24h": 1.0,
        "correlation_r": 0.0,
        "realized_vol_1h_pct": 25.0,
        "oi_change_24h_pct": 0.5,
        "funding_rate": 0.0,
        "fng_value": 65,
        "crash_score": 0,
        "black_swan_score": 2,
        "liquidity_verdict": "HEALTHY",
    }
    result = analyze_enriched(enriched_data)
    
    assert "fng_value" in result
    assert isinstance(result["fng_value"], (int, float))
    assert result["fng_value"] == 65
    assert result["sentiment"] == "greed"