"""Shared packet data fetcher — single source of truth for Redline BTC.

Reads from the Pipeline Dashboard V3 BTC Data Packet:
  https://aikeluargalee-tech.github.io/pipeline-dashboard-v3/packet/data.json

This aggregates 30+ pipeline JSON files + AMT feed into one JSON.
All Redline fetchers should use this as their primary data source.
"""

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Any

PACKET_URL = (
    "https://aikeluargalee-tech.github.io/"
    "pipeline-dashboard-v3/packet/data.json"
)

PIPELINE_DIR = Path("/home/maswilee/projects/pipeline-dashboard-v3/data")

logger = logging.getLogger(__name__)


def _read_pipeline_file(filename: str) -> Optional[dict[str, Any]]:
    """Read a JSON file from the local pipeline data directory."""
    path = PIPELINE_DIR / filename
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.debug("Pipeline file %s: %s", filename, e)
        return None


def fetch_packet() -> Optional[dict]:
    """Fetch the BTC Data Packet JSON (primary aggregated source)."""
    try:
        with urllib.request.urlopen(PACKET_URL, timeout=15) as r:
            data: dict = json.loads(r.read())
        return data
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("Packet fetch failed from %s: %s", PACKET_URL, e)
        return None


def fetch_brk() -> dict:
    """Extract BRK on-chain data from the pipeline packet.

    Reads reference.brk from data.json — providing NUPL, MVRV-Z, LTH-SOPR,
    RHODL Ratio, hash rate, fee rate, and difficulty from bitview.space.

    Returns empty dict if BRK data is unavailable.
    """
    p = fetch_packet()
    if not p:
        return {}

    brk = (p.get("reference", {}) or {}).get("brk", {})
    if not brk:
        return {}

    return {
        "nupl": brk.get("nupl"),
        "rhodl_ratio": brk.get("rhodl_ratio"),
        "lth_sopr_24h": brk.get("lth_sopr_24h"),
        "sth_sopr_24h": brk.get("sth_sopr_24h"),
        "sopr_24h": brk.get("sopr_24h"),
        "supply_in_profit_share": brk.get("supply_in_profit_share"),
        "mvrv": brk.get("mvrv"),
        "realized_price": brk.get("realized_price"),
        "puell_multiple": brk.get("puell_multiple"),
        "hash_rate_ehs": brk.get("hash_rate_ehs"),
        "hash_rate_drawdown_pct": brk.get("hash_rate_drawdown_pct"),
        "fee_rate_sat_vb": brk.get("fee_rate_sat_vb"),
        "difficulty": brk.get("difficulty"),
        "utxos_over_1y_sopr_24h": brk.get("utxos_1y_sopr"),
        "lth_net_realized_pnl": brk.get("lth_net_realized_pnl"),
        "sth_net_realized_pnl": brk.get("sth_net_realized_pnl"),
    }


def fetch_enriched() -> dict:
    """Fetch packet data PLUS enriched signals from pipeline files.

    Returns a dict merging core packet data with:
      - crash_precursor, black_swan scores → L1 risk
      - S/R bands → L5 structure
      - sentiment, liquidity_status → L5 context
    """
    packet = fetch_packet() or {}

    # Read pipeline files not in the packet
    crash = _read_pipeline_file("crash_precursor.json") or {}
    black = _read_pipeline_file("black_swan.json") or {}
    structural = _read_pipeline_file("structural.json") or {}
    sentiment = _read_pipeline_file("sentiment.json") or {}
    liq = _read_pipeline_file("liquidity_status.json") or {}
    positioning = _read_pipeline_file("positioning.json") or {}

    # Crash precursor
    crash_data = crash.get("crash_precursor", crash)
    if isinstance(crash_data, dict):
        crash_score = crash_data.get("composite", 0)
    else:
        crash_score = crash.get("composite", 0)
    crash_status = crash.get("status", "NORMAL")

    # Black swan
    black_score = black.get("score", 0)
    black_max = black.get("max", 17)
    black_status = black.get("status", "NORMAL")

    # Structural S/R bands
    sr_bands = structural.get("sr_bands", {})
    sr_1h = sr_bands.get("1h", {})
    sr_1d = sr_bands.get("1d", {})
    nearest_support_1h = None
    nearest_resistance_1h = None
    nearest_support_1d = None
    nearest_resistance_1d = None

    # Get nearest S/R from 1h supports
    for s in sr_1h.get("supports", []):
        c = float(s.get("center", 0))
        if nearest_support_1h is None or c > nearest_support_1h:
            nearest_support_1h = c
    for r_ in sr_1h.get("resistances", []):
        c = float(r_.get("center", 0))
        if nearest_resistance_1h is None or c < nearest_resistance_1h:
            nearest_resistance_1h = c

    # Get nearest S/R from 1d
    for s in sr_1d.get("supports", []):
        c = float(s.get("center", 0))
        if nearest_support_1d is None or c > nearest_support_1d:
            nearest_support_1d = c
    for r_ in sr_1d.get("resistances", []):
        c = float(r_.get("center", 0))
        if nearest_resistance_1d is None or c < nearest_resistance_1d:
            nearest_resistance_1d = c

    # Sentiment
    fg = sentiment.get("fear_greed", {})
    if isinstance(fg, dict):
        fng_value = fg.get("value", 0)
        fng_class = fg.get("classification", "unknown")
    else:
        fng_value = sentiment.get("fear_greed", 0)
        fng_class = "unknown"

    # Liquidity
    liq_data = liq
    liquidity_verdict = liq_data.get("liquidity_verdict", "UNKNOWN")
    taker_buy_ratio = float(liq_data.get("taker_buy_ratio", 0.5))
    oi_delta = liq_data.get("oi_delta", "FLAT")
    funding_signal = liq_data.get("funding_signal", "NEUTRAL")

    # Positioning
    cot = positioning.get("cot", {})
    cot_signal = cot.get("signal", "NEUTRAL")

    # Derivatives — OI trend
    deriv = _read_pipeline_file("derivatives.json") or {}
    oi_history = deriv.get("oi_history", [])
    oi_trend = deriv.get("oi_trend", "FLAT")
    oi_change_24h_deriv = deriv.get("oi_change_24h", 0)
    # Compute OI trend from history if available
    if len(oi_history) >= 2:
        recent = [h.get("btc", 0) for h in oi_history[-5:] if isinstance(h, dict)]
        if len(recent) >= 2:
            avg_first = sum(recent[:len(recent)//2]) / (len(recent)//2)
            avg_last = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
            if avg_last > avg_first * 1.01:
                oi_trend_derived = "rising"
            elif avg_last < avg_first * 0.99:
                oi_trend_derived = "falling"
            else:
                oi_trend_derived = "flat"
            oi_trend = oi_trend or oi_trend_derived

    # Context from packet
    ctx = packet.get("context", {}) if packet else {}

    enriched: dict = {
        # Enriched risk signals
        "crash_score": int(crash_score),
        "crash_status": crash_status,
        "crash_active_signals": crash.get("active_signals", []),
        "black_swan_score": int(black_score),
        "black_swan_max": int(black_max),
        "black_swan_status": black_status,
        "dxy": ctx.get("dxy", 100.0),
        "correlation_r": ctx.get("correlation_r", 0.0),
        "btc_equity_correlation": ctx.get("correlation_r", 0.0),
        "realized_vol_1h_pct": ctx.get("realized_vol_1h_pct", 0.0),
        "realized_vol_1d_pct": ctx.get("realized_vol_1d_pct", 0.0),
        "fng_value": fng_value,
        "fng_classification": fng_class,
        "cot_signal": cot_signal,

        # Derivatives
        "oi_trend": oi_trend,
        "oi_change_24h_pct": oi_change_24h_deriv,

        # Liquidity
        "liquidity_verdict": liquidity_verdict,
        "taker_buy_ratio": taker_buy_ratio,
        "oi_delta": oi_delta,
        "funding_signal": funding_signal,

        # S/R Bands
        "sr_1h_support": nearest_support_1h,
        "sr_1h_resistance": nearest_resistance_1h,
        "sr_1d_support": nearest_support_1d,
        "sr_1d_resistance": nearest_resistance_1d,
        "atr_1h_pct": sr_1h.get("atr_pct", 0.0),
        "atr_1d_pct": sr_1d.get("atr_pct", 0.0),
        "btc_price": ctx.get("btc_price", 0) or packet.get("critical", {}).get("btc_price", 0) or 62000,
    }

    return enriched

