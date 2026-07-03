"""Fetch Layer 1 Data

Fetches macro risk triggers:
- MSTR (MicroStrategy) price
- VIX (Volatility Index)
- US10Y (10-Year Treasury Yield)
- USD/JPY (Dollar/Yen exchange rate)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}
PIPELINE_DATA = "/home/maswilee/projects/pipeline-dashboard-v3/data"


def fetch_mock_data() -> dict:
    """Fetch mock Layer 1 data for testing."""
    return {
        "mstr_close": 100.77,
        "vix_current": 15.81,
        "us10y_current": 4.485,
        "usdjpy_change_pct": 0.0,
        "boj_verbal_response": False,
        "mstr_sessions_below": 0,
        "vix_sessions_above": 0,
        "usdjpy_stable_hours": 72,
        "btc_above_structure_low": True,
        "btc_price": 62122,
    }


def fetch_live_data() -> dict:
    """Fetch live Layer 1 macro trigger data from Yahoo Finance + pipeline data.

    Sources:
    - Pipeline macro.json → VIX, US10Y
    - Yahoo Finance → MSTR price, USD/JPY
    - Pipeline btc_price.json → BTC price
    """
    result = fetch_mock_data()

    # VIX and US10Y from pipeline data
    try:
        macro = json.load(open(f"{PIPELINE_DATA}/macro.json"))
        result["vix_current"] = macro.get("vix", 15.0)
        result["us10y_current"] = macro.get("us_10y_yield", 4.4)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Pipeline macro.json not available: {e}")

    # BTC price from pipeline
    try:
        btc = json.load(open(f"{PIPELINE_DATA}/btc_price.json"))
        result["btc_price"] = btc.get("price", 62000)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # MSTR from Yahoo Finance
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/MSTR",
            headers=YAHOO_HEADERS, timeout=10
        )
        result["mstr_close"] = r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as e:
        logger.warning(f"MSTR fetch failed: {e}")

    # USD/JPY from Yahoo Finance
    try:
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X",
            headers=YAHOO_HEADERS, timeout=10
        )
        r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as e:
        logger.warning(f"USD/JPY fetch failed: {e}")

    logger.info(
        f"Layer 1: MSTR=${result['mstr_close']:.2f}, "
        f"VIX={result['vix_current']:.1f}, "
        f"US10Y={result['us10y_current']:.3f}%, "
        f"BTC=${result['btc_price']:.0f}"
    )
    return result


def main():
    """Main entry point for Layer 1 data fetcher."""
    parser = argparse.ArgumentParser(description="Fetch Layer 1 macro triggers")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of live APIs")
    parser.add_argument("--output", type=str, default="data/layer1_data.json", help="Output file path")
    args = parser.parse_args()

    logger.info("Fetching Layer 1 data...")
    data = fetch_mock_data() if args.mock else fetch_live_data()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Layer 1 data saved to {output_path}")
    logger.info(f"MSTR: {data['mstr_close']:.2f}, VIX: {data['vix_current']:.2f}, US10Y: {data['us10y_current']:.2f}%")
    return data


if __name__ == "__main__":
    main()
