"""Fetch Layer 0 Data — on-chain regime metrics from BTC Data Packet.

Reads from the pipeline packet data.json (single source):
  - MVRV-Z, Cycle Composite, Options Skew
  - ETF Flows (daily + weekly)
  - Coinbase Premium
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.packet_source import fetch_packet, fetch_brk

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fetch_live_data() -> dict:
    """Fetch Layer 0 data from the BTC Data Packet.

    Returns dict with fields matching RegimeInputs dataclass,
    plus BRK on-chain metrics (NUPL, LTH-SOPR, RHODL, hash rate).
    """
    p = fetch_packet()
    brk = fetch_brk()

    if not p:
        logger.warning("Packet fetch failed, using fallback defaults")
        return fetch_mock_data()

    ctx = p.get("context", {})
    ref = p.get("reference", {})

    mvrv_z_raw = ref.get("cycle", {}).get("mvrv_z")
    mvrv_z = float(mvrv_z_raw) if mvrv_z_raw is not None else 0.25
    composite_raw = ref.get("cycle_composite")
    composite = float(composite_raw) if composite_raw is not None else 25.0
    skew = ref.get("options_skew_25d", -5.0)
    etf_weekly = ctx.get("etf_flow_weekly", 0.0) or 0.0
    premium = ctx.get("coinbase_premium", 0.0) or 0.0
    etf_daily = ctx.get("etf_flow_daily", 0.0) or 0.0

    info = (
        f"Layer 0: MVRV-Z={mvrv_z:.3f}, "
        f"Cycle={composite:.1f}, "
        f"ETF={etf_weekly / 1000:.2f}B, "
        f"Premium={premium:.4f}%"
    )
    if brk:
        nupl = brk.get("nupl")
        lth = brk.get("lth_sopr_24h")
        hr_dd = brk.get("hash_rate_drawdown_pct")
        info += f", BRK NUPL={nupl}, LTH-SOPR={lth}, HashDrawdown={hr_dd}"
    logger.info(info)

    result = {
        "mvrv_z_score": mvrv_z,
        "cycle_composite": composite,
        "options_skew_30d": skew,
        "etf_flows_weekly": etf_weekly,
        "coinbase_premium_trend": premium,
        "btc_price": p.get("critical", {}).get("btc_price", p.get("header", {}).get("btc_price", 62000)),
        "_etf_daily": etf_daily,
    }

    # Inject BRK on-chain data
    if brk:
        result["_brk"] = brk

    return result


def fetch_mock_data() -> dict:
    return {
        "mvrv_z_score": 0.25,
        "cycle_composite": 25.0,
        "options_skew_30d": -5.0,
        "etf_flows_weekly": -9706.0,
        "coinbase_premium_trend": 0.0,
        "btc_price": 61708.0,
    }


if __name__ == "__main__":
    data = fetch_live_data()
    print(json.dumps(data, indent=2, default=str))
