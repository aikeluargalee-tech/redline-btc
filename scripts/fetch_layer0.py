"""
Fetch Layer 0 Data

Fetches on-chain data for regime classification:
- MVRV-Z score
- Cycle Composite
- Options Skew (30d)
- ETF Flows (weekly)
- Coinbase Premium trend
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer0_regime import RegimeInputs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_mock_data() -> dict:
    """Fetch mock Layer 0 data for testing.

    Returns:
        Dictionary with mock on-chain metrics.
    """
    return {
        "mvrv_z_score": 0.25,
        "cycle_composite": 25.2,
        "options_skew_30d": -8.5,
        "etf_flows_weekly": -1.5,
        "coinbase_premium_trend": -0.8,
        "timestamp": "2024-01-15T12:00:00Z",
    }


def fetch_live_data() -> dict:
    """Fetch live Layer 0 data from APIs.

    Note: This is a stub implementation. In production, this would call:
    - CoinGecko API for price data
    - Glassnode-style API for MVRV-Z
    - Options data provider for skew
    - ETF flow data provider

    Returns:
        Dictionary with on-chain metrics.
    """
    # Stub: In production, replace with actual API calls
    logger.warning("Live data fetch not implemented. Using mock data.")
    return fetch_mock_data()


def main():
    """Main entry point for Layer 0 data fetcher."""
    parser = argparse.ArgumentParser(description="Fetch Layer 0 on-chain data")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of live APIs")
    parser.add_argument("--output", type=str, default="data/layer0_data.json", help="Output file path")
    args = parser.parse_args()

    logger.info("Fetching Layer 0 data...")

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

    logger.info(f"Layer 0 data saved to {output_path}")
    logger.info(f"MVRV-Z: {data['mvrv_z_score']:.2f}, Cycle: {data['cycle_composite']:.1f}")

    return data


if __name__ == "__main__":
    main()
