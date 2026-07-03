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

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.packet_source import fetch_packet

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_live_data() -> dict:
    """Fetch Layer 1 macro risk data.

    Returns dict with fields matching MacroTriggers dataclass.
    """
    p = fetch_packet()
    ctx = p.get("context", {}) if p else {}

    # VIX and US10Y from packet
    vix = ctx.get("vix", 16.0)
    us10y = ctx.get("us10y", 4.5)

    result = {
        "mstr_close": 100.0,
        "vix_current": vix,
        "us10y_current": us10y,
        "usdjpy_change_pct": 0.0,
        "boj_verbal_response": False,
        "mstr_sessions_below": 0,
        "vix_sessions_above": 0,
        "usdjpy_stable_hours": 72,
        "btc_above_structure_low": True,
        "btc_price": p.get("critical", {}).get("btc_price", 62000) if p else 62000,
    }

    # MSTR from Yahoo Finance
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/MSTR",
            headers=YAHOO_HEADERS, timeout=10
        )
        mstr = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        result["mstr_close"] = float(mstr)
    except Exception as e:
        logger.warning(f"MSTR fetch failed: {e}")

    # USD/JPY from Yahoo Finance
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X",
            headers=YAHOO_HEADERS, timeout=10
        )
        jpy = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        quotes = r.json()["chart"]["result"][0].get("indicators", {}).get("quote", [{}])
        if quotes and len(quotes[0].get("open", [])) > 0:
            opens = [o for o in quotes[0]["open"] if o is not None]
            if opens:
                result["usdjpy_change_pct"] = ((jpy - opens[0]) / opens[0]) * 100
        result["_usdjpy_price"] = jpy
    except Exception as e:
        logger.warning(f"USD/JPY fetch failed: {e}")

    btc = result["btc_price"]
    logger.info(
        f"Layer 1: MSTR=${result['mstr_close']:.2f}, "
        f"VIX={result['vix_current']:.1f}, "
        f"US10Y={result['us10y_current']:.3f}%, "
        f"BTC=${btc:.0f}"
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
