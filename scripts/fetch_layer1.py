"""
Fetch Layer 1 Data

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

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_mock_data() -> dict:
    """Fetch mock Layer 1 data for testing.

    Returns:
        Dictionary with mock macro trigger values.
    """
    return {
        "mstr_close": 4.2,
        "mstr_sessions_below": 1,
        "vix_current": 28.5,
        "vix_sessions_above": 3,
        "us10y_current": 4.72,
        "usdjpy_change_pct": 2.8,
        "boj_verbal_response": True,
        "usdjpy_stable_hours": 12,
        "btc_above_structure_low": False,
        "btc_structure_low": 38500.0,
        "timestamp": "2024-01-15T12:00:00Z",
    }


def fetch_live_data() -> dict:
    """Fetch live Layer 1 data from APIs.

    Note: This is a stub implementation. In production, this would call:
    - Yahoo Finance API for MSTR and VIX
    - FRED API for US10Y
    - Exchange rates API for USD/JPY

    Returns:
        Dictionary with macro trigger values.
    """
    # Stub: In production, replace with actual API calls
    logger.warning("Live data fetch not implemented. Using mock data.")
    return fetch_mock_data()


def main():
    """Main entry point for Layer 1 data fetcher."""
    parser = argparse.ArgumentParser(description="Fetch Layer 1 macro triggers")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of live APIs")
    parser.add_argument("--output", type=str, default="data/layer1_data.json", help="Output file path")
    args = parser.parse_args()

    logger.info("Fetching Layer 1 data...")

    if args.mock:
        data = fetch_mock_data()
        logger.info("Using mock data")
    else:
        data = fetch_live_data()

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Layer 1 data saved to {output_path}")
    logger.info(f"MSTR: {data['mstr_close']:.2f}, VIX: {data['vix_current']:.2f}, US10Y: {data['us10y_current']:.2f}%")

    return data


if __name__ == "__main__":
    main()
