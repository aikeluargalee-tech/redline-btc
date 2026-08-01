"""Fetch Layer 1 Data — macro risk triggers from BTC Data Packet + Yahoo Finance.

Reads from:
  - Packet data.json: VIX, US10Y (primary)
  - Yahoo Finance (live): MSTR price, USD/JPY
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

STATE_PATH = Path(__file__).parent.parent / ".redline_state.json"


def _safe_float(val, default=0.0):
    """Coerce N/A strings and None to numeric defaults."""
    if val is None:
        return default
    if isinstance(val, str) and val.strip().upper() == "N/A":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f)
    except OSError:
        logger.warning("Layer 1: could not persist state")


def fetch_live_data() -> dict:
    """
    Fetch Layer 1 macro risk data from the pipeline packet.
    Returns dict with fields matching MacroTriggers dataclass.
    """
    p = fetch_packet()
    ctx = p.get("context", {}) if p else {}

    # VIX and US10Y from packet
    vix = _safe_float(ctx.get("vix"), 16.0)
    us10y = _safe_float(ctx.get("us10y"), 4.5)
    mstr_close = _safe_float(ctx.get("mstr_close"), 100.0)
    usdjpy = ctx.get("usdjpy")

    # Persisted session state (counters + USDJPY prior)
    state = _load_state()
    l1_state = state.get("l1_state", {})

    # USD/JPY delta vs prior run
    usdjpy_price = _safe_float(usdjpy, 150.0) if usdjpy is not None else None
    usdjpy_prev = l1_state.get("usdjpy_price")
    usdjpy_change_pct = 0.0
    if usdjpy_price is not None and usdjpy_prev:
        try:
            usdjpy_change_pct = (usdjpy_price - float(usdjpy_prev)) / float(usdjpy_prev) * 100
        except (ValueError, TypeError, ZeroDivisionError):
            usdjpy_change_pct = 0.0

    # Session counters — increment while condition holds, reset otherwise
    mstr_sessions_below = int(l1_state.get("mstr_sessions_below", 0))
    vix_sessions_above = int(l1_state.get("vix_sessions_above", 0))
    mstr_sessions_below = mstr_sessions_below + 1 if mstr_close < 75.0 else 0
    vix_sessions_above = vix_sessions_above + 1 if vix > 28.0 else 0

    # USDJPY stability hours — count consecutive runs within 0.5% delta
    stable_hours = int(l1_state.get("usdjpy_stable_hours", 0))
    stable_hours = min(stable_hours + 1, 72) if abs(usdjpy_change_pct) < 0.5 else 0

    result = {
        "mstr_close": mstr_close,
        "vix_current": vix,
        "us10y_current": us10y,
        "usdjpy_change_pct": usdjpy_change_pct,
        "boj_verbal_response": False,
        "mstr_sessions_below": mstr_sessions_below,
        "vix_sessions_above": vix_sessions_above,
        "usdjpy_stable_hours": stable_hours,
        "btc_above_structure_low": True,
        "btc_price": _safe_float(p.get("critical", {}).get("btc_price"), 62000) if p else 62000,
        "_usdjpy_price": usdjpy_price,
    }

    # Persist updated state
    state["l1_state"] = {
        "usdjpy_price": usdjpy_price if usdjpy_price is not None else l1_state.get("usdjpy_price"),
        "mstr_sessions_below": mstr_sessions_below,
        "vix_sessions_above": vix_sessions_above,
        "usdjpy_stable_hours": stable_hours,
    }
    _save_state(state)

    btc = result["btc_price"]
    logger.info(
        f"Layer 1: MSTR=${result['mstr_close']:.2f}, "
        f"VIX={result['vix_current']:.1f}, "
        f"US10Y={result['us10y_current']:.3f}%, "
        f"BTC=${btc:.0f}, USDJPYΔ={usdjpy_change_pct:.2f}%, "
        f"sessions MSTR↓={mstr_sessions_below} VIX↑={vix_sessions_above}"
    )
    return result


def fetch_mock_data() -> dict:
    return {
        "mstr_close": 100.77,
        "vix_current": 15.8,
        "us10y_current": 4.485,
        "usdjpy_change_pct": 0.0,
        "boj_verbal_response": False,
        "mstr_sessions_below": 0,
        "vix_sessions_above": 0,
        "usdjpy_stable_hours": 72,
        "btc_above_structure_low": True,
        "btc_price": 61708.0,
    }


if __name__ == "__main__":
    data = fetch_live_data()
    print(json.dumps(data, indent=2, default=str))
