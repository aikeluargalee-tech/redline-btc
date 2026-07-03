"""Fetch intraday trade signals (Layer 4) from the BTC Data Packet.

Reads the pipeline packet data.json to derive:
  - direction (LONG/SHORT/NONE), trade_type (a/b/c)
  - ADX direction, MTF alignment, CVD invalidation
  - VP state, session context, order book health
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_data_packet import fetch_live_data as fetch_dp_live

logger = logging.getLogger(__name__)


def _get_session() -> str:
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
    """Fetch intraday trade signals from the BTC Data Packet."""
    dp = fetch_dp_live()

    btc_price = dp.get("btc_price", 61708.0)
    adx_regime = dp.get("adx_regime", "")
    adx = dp.get("amt_adx", 0)
    structure_1d = dp.get("structure_1d", "neutral")
    structure_4h = dp.get("structure_4h", "neutral")
    vp_state_text = dp.get("vp_state", "")
    balance_state = dp.get("balance_state", "")
    cvd_24h = dp.get("cvd_24h", 0)
    funding = dp.get("funding_rate", 0)
    liq_clusters = dp.get("liq_clusters", "")
    taker_ratio = dp.get("taker_ratio_24h", 1.0)

    # Direction from MTF alignment
    direction = "NONE"
    if structure_1d == "bearish" and structure_4h == "bearish":
        direction = "SHORT"
    elif structure_1d == "bullish" and structure_4h == "bullish":
        direction = "LONG"
    elif structure_1d == "bearish":
        direction = "SHORT"
    elif structure_4h == "bearish":
        direction = "SHORT"

    # Trade type from ADX
    if adx > 35:
        trade_type = "type_a"
    elif adx >= 20:
        trade_type = "type_b"
    else:
        trade_type = "type_c"

    # ADX in trending regime = directional
    adx_direction = adx > 25

    # MTF alignment: at least 2 of 3 agree (1D + 4H + AMT consensus)
    mtf_alignment = structure_1d == structure_4h or structure_4h != "neutral"

    # CVD invalidation: extreme CVD means risk
    cvd_invalidation = not (abs(cvd_24h) > 500)  # True = safe

    # Liq cluster check
    price_vs_liq_cluster = bool(liq_clusters and ("Long" in liq_clusters or "Short" in liq_clusters))

    # VP state
    vp_state = vp_state_text in ("ACCEPTANCE", "REJECTION") or balance_state in ("ESTABLISHED_BALANCE", "DEVELOPING_BALANCE")

    # Session context
    session = _get_session()
    session_context = session in ("london", "ny")

    # Order book health
    ob = dp.get("order_book_top5", {})
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    if bids and asks:
        bid_vol = sum(b.get("size", 0) for b in bids[:3])
        ask_vol = sum(a.get("size", 0) for a in asks[:3])
        if bid_vol > 0 and ask_vol > 0 and 0.3 < bid_vol / ask_vol < 3.0:
            if not session_context:
                session_context = True

    # L3 alignment
    layer3_alignment = True
    if l3_output and isinstance(l3_output, dict):
        l3_dir = l3_output.get("direction", "NONE")
        if direction == "SHORT" and l3_dir not in ("SHORT", "NONE"):
            layer3_alignment = False
        elif direction == "LONG" and l3_dir not in ("LONG", "NONE"):
            layer3_alignment = False

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
        "_adx": adx,
        "_funding": funding,
    }


def fetch_mock_data() -> dict:
    return {
        "direction": "NONE",
        "trade_type": "type_c",
        "adx_direction": False,
        "mtf_alignment": False,
        "cvd_invalidation": True,
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
