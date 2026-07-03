"""Fetch BTC Data Packet

Reads live BTC market data for Layer 4/5 analysis from existing pipeline sources:
- /tmp/amt_feed.json → AMT, CVD, OI, funding, footprint
- Pipeline data → volume profile, derivatives, liq clusters
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AMT_FEED = "/tmp/amt_feed.json"
PIPELINE_DATA = "/home/maswilee/projects/pipeline-dashboard-v3/data"


def fetch_live_data() -> dict:
    """Fetch live BTC data packet from /tmp/amt_feed.json + pipeline data.

    Returns:
        Dictionary with market data for Layer 4/5.
    """
    result = fetch_mock_data()

    # Read AMT feed
    try:
        amt = json.load(open(AMT_FEED))
        result["btc_price"] = amt.get("btc_spot", result["btc_price"])

        # 4layer data
        l4 = amt.get("4layer", {})
        result["amt_adx"] = l4.get("regime", {}).get("adx", result["amt_adx"])
        result["amt_regime"] = l4.get("regime", {}).get("mode", result["amt_regime"])

        # Footprint / CVD
        fp = amt.get("footprint", {})
        full_candle = fp.get("full_candle")
        if isinstance(full_candle, dict):
            cvd = full_candle.get("cvd")
            if cvd is not None:
                result["cvd_value"] = cvd

        # Funding + OI
        funding = amt.get("funding", {})
        rate = funding.get("rate")
        if rate is not None:
            result["funding_rate"] = rate
        oi = funding.get("oi_current")
        if oi is not None:
            result["open_interest"] = oi
        oi_chg = funding.get("oi_change_24h")
        if oi_chg is not None:
            result["oi_change_24h"] = oi_chg

        # Taker volume
        tv = amt.get("taker_volume", {})
        result["taker_buy_ratio"] = tv.get("buy_ratio", result["taker_buy_ratio"])

        # Order book
        ob = amt.get("order_book", {})
        result["bid_ask_ratio"] = ob.get("bid_ask_ratio", result["bid_ask_ratio"])

    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"AMT feed not available: {e}")

    # Volume profile from pipeline
    try:
        vp = json.load(open(f"{PIPELINE_DATA}/playbook_mean_reversion.json"))
        result["volume_profile_state"] = vp.get("setup", {}).get("context", "neutral")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Derivatives from pipeline
    try:
        deriv = json.load(open(f"{PIPELINE_DATA}/derivatives.json"))
        if not result.get("funding_rate") and deriv.get("funding_rate"):
            result["funding_rate"] = deriv["funding_rate"]
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    logger.info(
        f"Data packet: BTC=${result['btc_price']:.0f}, "
        f"ADX={result['amt_adx']:.1f}, "
        f"CVD={result['cvd_value']:.1f}, "
        f"OI={result['open_interest']:.0f} BTC"
    )
    return result


def fetch_mock_data() -> dict:
    """Return default/mock data packet."""
    return {
        "btc_price": 61708,
        "amt_adx": 22.0,
        "amt_regime": "transitional",
        "cvd_value": 0.0,
        "cvd_trend": "neutral",
        "open_interest": 108454,
        "oi_change_24h": 1753,
        "funding_rate": 0.00005,
        "funding_rate_trend": "neutral",
        "taker_buy_ratio": 0.52,
        "bid_ask_ratio": 1.02,
        "volume_profile_state": "acceptance",
        "liquidation_clusters": [],
        "timestamp": "",
    }


def main():
    """Main entry point for BTC data packet fetcher."""
    parser = argparse.ArgumentParser(description="Fetch BTC data packet")
    parser.add_argument("--mock", action="store_true", help="Use mock data instead of live feeds")
    parser.add_argument("--output", type=str, default="/tmp/btc_data_packet.json", help="Output file path")
    args = parser.parse_args()

    logger.info("Fetching BTC data packet...")
    data = fetch_mock_data() if args.mock else fetch_live_data()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info(f"BTC data packet saved to {output_path}")
    return data


if __name__ == "__main__":
    main()
