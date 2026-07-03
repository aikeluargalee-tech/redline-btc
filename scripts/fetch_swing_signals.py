"""Fetch swing trade signals (Layer 3) from live data sources.

Reads AMT feed and pipeline data to derive:
  - structure_4h, structure_1d (bullish/bearish/neutral)
  - daily_sr_level (support/resistance/neutral)
  - adx_value, cvd_trend, daily_oversold
  - mvrv_z_score, at_major_support
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AMT_FEED_PATH = "/tmp/amt_feed.json"
CYCLE_PATH = "/home/maswilee/projects/pipeline-dashboard-v3/data/cycle.json"
BTC_PRICE_PATH = "/home/maswilee/projects/pipeline-dashboard-v3/data/btc_price.json"


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Cannot read %s: %s", path, e)
        return None


def fetch_swing_signals() -> dict:
    """Fetch swing trade signals from live data.

    Returns dict with fields matching SwingInputs dataclass.
    """
    amt = _read_json(AMT_FEED_PATH)
    cycle = _read_json(CYCLE_PATH)
    btc_price_data = _read_json(BTC_PRICE_PATH)

    # --- Price ---
    btc_price = 61708.0  # fallback
    if btc_price_data and "price" in btc_price_data:
        btc_price = float(btc_price_data["price"])
    elif amt:
        amt_data = amt.get("data", amt)
        btc_price = float(amt_data.get("btc_spot", btc_price))

    # --- Structure from AMT alignment ---
    structure_4h = "neutral"
    structure_1d = "neutral"
    daily_sr_level = "neutral"
    adx_value = 0.0
    cvd_trend = "neutral"
    daily_oversold = False
    at_major_support = False
    fib_zone_valid = False
    bull_zone = []
    bear_zone = []
    alignment = {}

    if amt:
        amt_data = amt.get("data", amt)
        alignment = amt_data.get("alignment", {})
        regime_data = amt_data.get("regime", {})
        balance = amt_data.get("balance", {})

        # ADX
        adx_value = float(regime_data.get("adx", 0))

        # Multi-timeframe structure from alignment.detail
        detail = alignment.get("detail", [])
        for entry in detail:
            label = entry.get("label", "")
            direction = entry.get("dir", "NEUTRAL").lower()
            if label == "1D":
                structure_1d = direction
            elif label == "4H":
                structure_4h = direction

        # CVD trend from 1H timeframe
        tf_data = amt_data.get("timeframes", {})
        tf_1h = tf_data.get("1H", {})
        cvd_val = tf_1h.get("cvd_trend", 0)
        if isinstance(cvd_val, (int, float)):
            if cvd_val > 0:
                cvd_trend = "positive"
            elif cvd_val < -20:
                cvd_trend = "negative"
            elif cvd_val < 0:
                cvd_trend = "rolling"
            else:
                cvd_trend = "neutral"
        else:
            cvd_trend = "neutral"

        # S/R level from fib zones
        fib_zone = alignment.get("fib_zone", {})
        if fib_zone.get("valid"):
            fib_zone_valid = True
            bull_zone = [float(x) for x in fib_zone.get("bull_zone", [0, 0])]
            bear_zone = [float(x) for x in fib_zone.get("bear_zone", [0, 0])]

            if bull_zone and bull_zone[0] <= btc_price <= bull_zone[1]:
                daily_sr_level = "support"
                at_major_support = True
            elif bear_zone and bear_zone[0] <= btc_price <= bear_zone[1]:
                daily_sr_level = "resistance"
            else:
                daily_sr_level = "neutral"

        # Check HVN zones for major support
        hvn_zones = balance.get("hvn_zones", [])
        for zone in hvn_zones:
            if len(zone) == 2 and zone[0] <= btc_price <= zone[1]:
                at_major_support = True
                break

        # Daily oversold: if price near the low of the 24h range
        high_24h = float(amt_data.get("high_24h", 0))
        low_24h = float(amt_data.get("low_24h", 0))
        if high_24h > low_24h:
            pct_from_low = (btc_price - low_24h) / (high_24h - low_24h) * 100
            if pct_from_low < 20:
                daily_oversold = True

        # Also assign SR level from balance floor/ceiling
        if daily_sr_level == "neutral":
            floor = balance.get("tf_48h", {}).get("floor", 0)
            ceiling = balance.get("tf_48h", {}).get("ceiling", 0)
            if floor and btc_price <= floor * 1.02:
                daily_sr_level = "support"
                at_major_support = True
            elif ceiling and btc_price >= ceiling * 0.98:
                daily_sr_level = "resistance"

    # --- MVRV-Z ---
    mvrv_z_score = 0.25  # fallback
    if cycle:
        mvrv_z_score = float(cycle.get("mvrv_z", mvrv_z_score))
        if isinstance(cycle.get("composite_score"), (int, float)):
            pass  # not used here but available

    amt_verdict = alignment.get("verdict", "N/A") if amt else "N/A"

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
        "_amt_adx": adx_value,
        "_amt_verdict": amt_verdict,
    }


def fetch_mock_data() -> dict:
    """Return mock swing signals for testing."""
    return {
        "btc_price": 61708.0,
        "structure_4h": "neutral",
        "structure_1d": "bearish",
        "daily_sr_level": "resistance",
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
