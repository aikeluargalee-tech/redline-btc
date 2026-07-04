"""Fetch swing trade signals (Layer 3) from the BTC Data Packet.

Reads the pipeline packet data.json to derive:
  - structure_4h, structure_1d from AMT MTF text
  - daily_sr_level from S/R strings
  - adx_value, cvd_trend from packet metrics
  - at_major_support from price vs zones
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.packet_source import fetch_packet
from scripts.fetch_data_packet import fetch_live_data as fetch_dp_live

logger = logging.getLogger(__name__)


def fetch_swing_signals() -> dict:
    """Fetch swing trade signals from the BTC Data Packet."""
    dp = fetch_dp_live()

    btc_price = dp.get("btc_price", 61708.0)
    structure_4h = dp.get("structure_4h", "neutral")
    structure_1d = dp.get("structure_1d", "neutral")
    adx_value = dp.get("amt_adx", 0)

    # CVD trend from the 1H timeframe
    cvd_per_tf = dp.get("cvd_per_tf", {})
    cvd_1h = cvd_per_tf.get("1H", 0)
    if isinstance(cvd_1h, (int, float)):
        if cvd_1h > 0:
            cvd_trend = "positive"
        elif cvd_1h < -20:
            cvd_trend = "negative"
        elif cvd_1h < 0:
            cvd_trend = "rolling"
        else:
            cvd_trend = "neutral"
    else:
        cvd_trend = "neutral"

    # Daily S/R level from amt_mtf text
    amt_mtf = dp.get("amt_mtf", "")
    daily_sr_level = "neutral"
    if "ZONE_MISS" in amt_mtf:
        daily_sr_level = "resistance"
    elif "ZONE_HIT" in amt_mtf or "BALANCE" in dp.get("balance_state", ""):
        daily_sr_level = "support"

    # Daily oversold from RSI-14 in packet context
    p = fetch_packet()
    daily_oversold = False
    daily_rsi_14 = None
    if p:
        daily_rsi_14 = p.get("context", {}).get("daily_rsi_14")
    if daily_rsi_14 is not None and isinstance(daily_rsi_14, (int, float)):
        daily_oversold = float(daily_rsi_14) < 30
        logger.debug("Daily RSI-14 from packet: %s (oversold=%s)", daily_rsi_14, daily_oversold)
    else:
        # Fallback heuristic
        bal_width = dp.get("balance_width_pct", 5)
        daily_oversold = bal_width > 3 if isinstance(bal_width, (int, float)) else False

    # MVRV-Z from packet (reuse p from above)
    mvrv_z_score = 0.25
    if p:
        mvrv_z_score = p.get("reference", {}).get("cycle", {}).get("mvrv_z", 0.25)

    # Major support check from liq clusters
    liq = dp.get("liq_clusters", "")
    at_major_support = False
    if liq and "Long" in liq:
        # Parse long liquidation clusters
        import re
        longs = re.findall(r'\$?([\d,]+)', liq.split("Short")[0] if "Short" in liq else liq)
        for l in longs:
            try:
                level = float(l.replace(",", ""))
                if abs(btc_price - level) / btc_price < 0.005:  # within 0.5%
                    at_major_support = True
                    break
            except ValueError:
                pass

    return {
        "btc_price": btc_price,
        "structure_4h": structure_4h,
        "structure_1d": structure_1d,
        "daily_sr_level": daily_sr_level,
        "adx_value": adx_value,
        "cvd_trend": cvd_trend,
        "daily_oversold": daily_oversold,
        "mvrv_z_score": mvrv_z_score,
        "at_major_support": at_major_support,
        "_amt_mtf": amt_mtf,
    }


def fetch_mock_data() -> dict:
    return {
        "btc_price": 61708.0,
        "structure_4h": "neutral",
        "structure_1d": "bearish",
        "daily_sr_level": "neutral",
        "adx_value": 41.1,
        "cvd_trend": "negative",
        "daily_oversold": False,
        "mvrv_z_score": 0.25,
        "at_major_support": False,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    data = fetch_swing_signals()
    print(json.dumps(data, indent=2, default=str))
