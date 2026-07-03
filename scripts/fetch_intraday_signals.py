"""Fetch intraday trade signals (Layer 4) from live data sources.

Reads AMT feed and pipeline data to derive:
  - direction (LONG/SHORT/NONE), trade_type (type_a/b/c)
  - ADX direction check, MTF alignment, CVD invalidation
  - Price vs liq cluster, VP state, session context, L3 alignment
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

AMT_FEED_PATH = "/tmp/amt_feed.json"


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Cannot read %s: %s", path, e)
        return None


def _get_session() -> str:
    """Determine current trading session based on UTC hour."""
    h = datetime.now(timezone.utc).hour
    if 0 <= h < 8:
        return "asia"
    elif 8 <= h < 13:
        return "london"
    elif 13 <= h < 22:
        return "ny"
    else:
        return "asia"


def fetch_intraday_signals(l3_output: Optional[dict] = None) -> dict:
    """Fetch intraday trade signals from live data.

    Args:
        l3_output: Optional result from Layer 3 swing assessment
            (for L3 alignment check).

    Returns dict with fields matching IntradayInputs dataclass.
    """
    amt = _read_json(AMT_FEED_PATH)
    btc_price = 61708.0

    # Defaults
    direction = "NONE"
    trade_type = "type_c"
    adx_direction = False
    mtf_alignment = False
    cvd_invalidation = False
    price_vs_liq_cluster = False
    vp_state = False
    session_context = True  # Default to True
    layer3_alignment = False
    regime_data = {}
    alignment_data = {}

    if amt:
        amt_data = amt.get("data", amt)
        alignment_data = amt_data.get("alignment", {})
        regime_data = amt_data.get("regime", {})
        balance = amt_data.get("balance", {})
        heatmap = amt_data.get("heatmap", {})
        order_book = amt_data.get("order_book", {})

        btc_price = float(amt_data.get("btc_spot", btc_price))
        adx = float(regime_data.get("adx", 0))
        consensus = alignment_data.get("consensus", "NEUTRAL")

        # --- Direction ---
        if consensus.upper() == "BULLISH":
            direction = "LONG"
        elif consensus.upper() == "BEARISH":
            direction = "SHORT"
        else:
            direction = "NONE"

        # --- Trade type based on ADX ---
        # ADX > 35: trending → Type A (trend continuation)
        # ADX 20-35: moderate → Type B (mean reversion)
        # ADX < 20: weak → Type C (scalp)
        if adx > 35:
            trade_type = "type_a"
        elif adx >= 20:
            trade_type = "type_b"
        else:
            trade_type = "type_c"

        # --- ADX direction ---
        # Check if ADX is rising (from regime detail - trending signals direction)
        adx_direction = adx > 25  # ADX above 25 = directional

        # --- MTF alignment ---
        # Check if at least 2 of 3 timeframes agree
        detail = alignment_data.get("detail", [])
        non_neutral = [e for e in detail if e.get("dir", "NEUTRAL") != "NEUTRAL"]
        mtf_alignment = len(non_neutral) >= 2

        # --- CVD invalidation ---
        # Check if CVD is extreme (divergence from price direction)
        tf_data = amt_data.get("timeframes", {})
        tf_1h = tf_data.get("1H", {})
        cvd_val = tf_1h.get("cvd_trend", 0)
        if isinstance(cvd_val, (int, float)):
            # CVD > 50 or < -50 indicates extreme flow → invalidation risk
            cvd_invalidation = abs(cvd_val) > 30
        else:
            cvd_invalidation = False

        # --- Price vs liquidation cluster ---
        liq_above = heatmap.get("above_cluster")
        liq_below = heatmap.get("below_cluster")
        if liq_above or liq_below:
            price_vs_liq_cluster = True

        # --- VP (Volume Profile) state ---
        state = balance.get("state", "")
        if state in ("ESTABLISHED_BALANCE", "DEVELOPING_BALANCE"):
            vp_state = True
        # Also check if price is in an HVN zone
        hvn_zones = balance.get("hvn_zones", [])
        for zone in hvn_zones:
            if len(zone) == 2 and zone[0] <= btc_price <= zone[1]:
                vp_state = True
                break

        # --- Session context ---
        session = _get_session()
        # Better to trade in London/NY sessions for liquidity
        if session in ("london", "ny"):
            session_context = True
        else:
            session_context = False

        # --- Order book health check ---
        bid_ask = order_book.get("bid_ask_ratio", 1.0)
        if isinstance(bid_ask, (int, float)) and bid_ask > 0.5 and bid_ask < 3.0:
            if not session_context:  # Only flip if ASIA and healthy
                session_context = True

    # --- L3 alignment ---
    if l3_output and isinstance(l3_output, dict):
        l3_direction = l3_output.get("direction", "NONE")
        l3_allowed = l3_output.get("entry_allowed", False)
        if direction == l3_direction and l3_allowed:
            layer3_alignment = True
        elif direction != "NONE" and l3_direction == "NONE":
            layer3_alignment = True  # L4 has conviction even if L3 doesn't
    else:
        layer3_alignment = True  # Default to True if no L3 data

    return {
        "direction": direction,
        "trade_type": trade_type,
        "adx_direction": adx_direction,
        "mtf_alignment": mtf_alignment,
        "cvd_invalidation": cvd_invalidation,
        "price_vs_liq_cluster": price_vs_liq_cluster,
        "vp_state": vp_state,
        "session_context": session_context,
        "layer3_alignment": layer3_alignment,
        "btc_price": btc_price,
        "_adx_used": float(regime_data.get("adx", 0)) if amt else 0,
        "_amt_consensus": alignment_data.get("verdict", "N/A") if amt else "N/A",
    }


def fetch_mock_data() -> dict:
    """Return mock intraday signals for testing."""
    return {
        "direction": "NONE",
        "trade_type": "type_c",
        "adx_direction": False,
        "mtf_alignment": False,
        "cvd_invalidation": False,
        "price_vs_liq_cluster": False,
        "vp_state": False,
        "session_context": True,
        "layer3_alignment": True,
        "btc_price": 61708.0,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    data = fetch_intraday_signals()
    print(json.dumps(data, indent=2, default=str))
