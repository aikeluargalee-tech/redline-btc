"""
Fetch BTC Data Packet

Fetches BTC market data for Layer 4/5 analysis:
- AMT (Average Mean Temperature)
- CVD (Cumulative Volume Delta)
- OI (Open Interest)
- Funding rates
- Liquidation clusters
- Volume profile state
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer5_engine import get_mock_data_packet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_mock_data() -> dict:
    """Fetch mock BTC data packet for testing.

    Returns:
        Dictionary with mock market data.
    """
    packet = get_mock_data_packet()
    return {
        "amt_value": packet.amt_value,
        "amt_trend": packet.amt_trend,
        "cvd_value": packet.cvd_value,
        "cvd_trend": packet.cvd_trend,
        "open_interest": packet.open_interest,
        "oi_change_24h": packet.oi_change_24h,
        "funding_rate": packet.funding_rate,
        "funding_rate_trend": packet.funding_rate_trend,
        "liquidation_clusters": packet.liquidation_clusters,
        "volume_profile_state": packet.volume_profile_state,
        "timestamp": "2024-01-15T12:00:00Z",
    }


def fetch_live_data() -> dict:
    """Fetch live BTC data packet from AMT feed.

    Note: This is a stub implementation. In production, this would read from:
    - /tmp/amt_feed.json for AMT data
    - Exchange APIs for OI, funding, CVD
    - Volume profile calculations

    Returns:
        Dictionary with market data.
    """
    # Stub: In production, replace with actual data fetching
    logger.warning("Live data fetch not implemented. Using mock data.")
    return fetch_mock_data()


def main():
    """Main entry point for BTC data packet fetcher."""
    parser = argparse.ArgumentParser(description="Fetch BTC data packet")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of live feeds")
    parser.add_argument("--output", type=str, default="/tmp/btc_data_packet.json", help="Output file path")
    args = parser.parse_args()

    logger.info("Fetching BTC data packet...")

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

    logger.info(f"BTC data packet saved to {output_path}")
    logger.info(f"AMT: {data['amt_value']:.2f} ({data['amt_trend']}), CVD: {data['cvd_value']:.1f}")

    return data


if __name__ == "__main__":
    main()
