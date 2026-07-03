"""Fetch BTC Data Packet — Layer 4/5 analysis data.

Reads from the pipeline packet data.json (single source):
  - ADX, CVD, OI, funding, VP, balance, orderbook, liq clusters
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.packet_source import fetch_packet

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def fetch_live_data() -> dict:
    """Fetch live BTC data packet from the pipeline packet data.json."""
    p = fetch_packet()
    if not p:
        return fetch_mock_data()

    crit = p.get("critical", {})
    ctx = p.get("context", {})
    ref = p.get("reference", {})

    # Derive MTF direction from amt_mtf text
    amt_mtf = crit.get("amt_mtf", "")
    structure_1d = "bearish" if "1D BEARISH" in amt_mtf else ("bullish" if "1D BULLISH" in amt_mtf else "neutral")
    structure_4h = "bearish" if "4H BEARISH" in amt_mtf else ("bullish" if "4H BULLISH" in amt_mtf else "neutral")

    result = {
        "btc_price": crit.get("btc_price", p.get("header", {}).get("btc_price", 61708)),
        "amt_adx": crit.get("amt_adx", 0),
        "amt_mtf": amt_mtf,
        "cvd_per_tf": crit.get("cvd_per_tf", {}),
        "oi_per_tf": crit.get("oi_per_tf", {}),
        "session_cvd": crit.get("session_cvd", 0),
        "oi_absolute_usd_billions": crit.get("oi_absolute_usd_billions", 0),
        "taker_ratio_24h": crit.get("taker_ratio_24h", 1.0),
        "vp_poc": crit.get("vp_poc"),
        "vp_vah": crit.get("vp_vah"),
        "vp_val": crit.get("vp_val"),
        "vp_shape": crit.get("vp_shape", ""),
        "vp_state": crit.get("vp_state", ""),
        "balance_state": crit.get("balance_state", ""),
        "balance_width_pct": crit.get("balance_width_pct", 0),
        "adx_regime": crit.get("adx_regime", ""),
        "cvd_24h": ctx.get("cvd_24h", 0),
        "funding_rate": ctx.get("funding_rate", 0),
        "long_short_ratio": ctx.get("long_short_ratio", 1.0),
        "perp_basis_pct": ctx.get("perp_basis_pct", 0),
        "liq_clusters": ctx.get("liq_clusters", ""),
        "coinbase_premium": ctx.get("coinbase_premium", 0),
        "vix": ctx.get("vix", 0),
        "us10y": ctx.get("us10y", 0),
        "fng_value": ctx.get("fng_value", 0),
        "order_book_top5": ctx.get("order_book_top5", {}),
        "structure_1d": structure_1d,
        "structure_4h": structure_4h,
        "sr_1h": ref.get("sr_1h", ""),
        "sr_1d": ref.get("sr_1d", ""),
    }

    logger.info(
        f"Data packet: BTC=${result['btc_price']:.0f}, "
        f"ADX={result['amt_adx']}, "
        f"CVD={result['cvd_24h']}, "
        f"OI={result['oi_absolute_usd_billions']}B"
    )
    return result


def fetch_mock_data() -> dict:
    return {
        "btc_price": 61708.0,
        "amt_adx": 41.1,
        "amt_mtf": "1D BEARISH | 4H NEUTRAL | 1H BEARISH",
        "cvd_per_tf": {"1D": 1752.83, "4H": 2874.45, "1H": -30.99},
        "oi_per_tf": {"1D": 0.0246, "4H": -0.0472, "1H": 0.0416},
        "session_cvd": 474.05,
        "oi_absolute_usd_billions": 6.63,
        "taker_ratio_24h": 1.107,
        "vp_poc": 61667,
        "vp_vah": 61718,
        "vp_val": 61612,
        "vp_shape": "P",
        "vp_state": "ACCEPTANCE",
        "balance_state": "DEVELOPING_BALANCE",
        "balance_width_pct": 3.83,
        "adx_regime": "TRENDING",
        "cvd_24h": -163.75,
        "funding_rate": 0.0001,
        "long_short_ratio": 1.7617,
        "perp_basis_pct": -0.0389,
        "liq_clusters": "Long: $61,700, $61,650 | Short: $61,700, $62,200",
        "coinbase_premium": -0.1167,
        "vix": 16.15,
        "us10y": 4.485,
        "fng_value": 21,
        "order_book_top5": {"bids": [], "asks": []},
        "structure_1d": "bearish",
        "structure_4h": "neutral",
        "sr_1h": "",
        "sr_1d": "",
    }


if __name__ == "__main__":
    data = fetch_live_data()
    print(json.dumps(data, indent=2, default=str))
