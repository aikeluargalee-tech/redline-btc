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
from typing import Optional

PACKET_URL = (
    "https://aikeluargalee-tech.github.io/"
    "pipeline-dashboard-v3/packet/data.json"
)


def _to_float(val, default=0.0):
    """Coerce N/A strings and None to numeric defaults."""
    if val is None:
        return default
    if isinstance(val, str) and val.strip().upper() == "N/A":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

logger = logging.getLogger(__name__)


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
    """Fetch enriched signals from the packet URL — NO local file dependencies.

    All enriched data (crash, black_swan, S/R bands, sentiment, liquidity,
    positioning, derivatives) now lives in packet["enriched"].  Single-source
    of truth: https://aikeluargalee-tech.github.io/pipeline-dashboard-v3/packet/data.json
    """
    packet = fetch_packet() or {}
    enriched_pkt = packet.get("enriched", {}) if packet else {}
    critical_pkt = packet.get("critical", {}) if packet else {}

    if not enriched_pkt:
        logger.warning("Packet 'enriched' section missing — returning defaults")

    # All fields come from the packet's enriched section
    enriched: dict = {
        # Risk signals
        "crash_score": int(enriched_pkt.get("crash_score", 0)),
        "crash_status": enriched_pkt.get("crash_status", "NORMAL"),
        "crash_active_signals": enriched_pkt.get("crash_active_signals", []),
        "black_swan_score": int(enriched_pkt.get("black_swan_score", 0)),
        "black_swan_max": int(enriched_pkt.get("black_swan_max", 17)),
        "black_swan_status": enriched_pkt.get("black_swan_status", "NORMAL"),

        # Context
        "dxy": enriched_pkt.get("dxy", 100.0),
        "correlation_r": enriched_pkt.get("correlation_r", 0.0),
        "btc_equity_correlation": enriched_pkt.get("btc_equity_correlation", 0.0),
        "realized_vol_1h_pct": enriched_pkt.get("realized_vol_1h_pct", 0.0),
        "realized_vol_1d_pct": enriched_pkt.get("realized_vol_1d_pct", 0.0),
        "fng_value": enriched_pkt.get("fng_value", 0),
        "fng_classification": enriched_pkt.get("fng_classification", "unknown"),
        "cot_signal": enriched_pkt.get("cot_signal", "NEUTRAL"),
        "vix": enriched_pkt.get("vix", "N/A"),
        "funding_rate": enriched_pkt.get("funding_rate", "N/A"),
        "coinbase_premium": enriched_pkt.get("coinbase_premium", 0),

        # Derivatives
        "oi_trend": enriched_pkt.get("oi_trend", "FLAT"),
        "oi_change_24h_pct": enriched_pkt.get("oi_change_24h_pct", 0),

        # Liquidity
        "liquidity_verdict": enriched_pkt.get("liquidity_verdict", "UNKNOWN"),
        "taker_buy_ratio": enriched_pkt.get("taker_buy_ratio", 0.5),
        "oi_delta": enriched_pkt.get("oi_delta", "FLAT"),
        "funding_signal": enriched_pkt.get("funding_signal", "NEUTRAL"),

        # S/R Bands
        "sr_1h_support": enriched_pkt.get("sr_1h_support"),
        "sr_1h_resistance": enriched_pkt.get("sr_1h_resistance"),
        "sr_1d_support": enriched_pkt.get("sr_1d_support"),
        "sr_1d_resistance": enriched_pkt.get("sr_1d_resistance"),
        "atr_1h_pct": enriched_pkt.get("atr_1h_pct", 0.0),
        "atr_1d_pct": enriched_pkt.get("atr_1d_pct", 0.0),
        "btc_price": enriched_pkt.get("btc_price", 0),

        # L5 momentum inputs — from packet critical/enriched (were missing → L5 momentum always neutral)
        "cvd_24h": _to_float(enriched_pkt.get("cvd_24h", critical_pkt.get("cvd_per_tf", {}).get("1D", 0))),
        "taker_ratio_24h": _to_float(enriched_pkt.get("taker_ratio_24h", critical_pkt.get("taker_ratio_24h", 1.0)), 1.0),
        "vp_state": enriched_pkt.get("vp_state", critical_pkt.get("vp_state", "unknown")),
        "oi_absolute_usd_billions": _to_float(enriched_pkt.get("oi_absolute_usd_billions", critical_pkt.get("oi_absolute_usd_billions", 0))),
    }

    return enriched


def fetch_heatmap() -> Optional[dict]:
    """Fetch heatmap (Layer 6) data from the packet's heatmap section.

    Reads from the published data.json which now includes the heatmap key
    populated by packet_to_json.py → load_heatmap_data().

    Returns None if packet fetch fails or heatmap section is missing.
    """
    p = fetch_packet()
    if not p:
        return None
    return p.get("heatmap")

