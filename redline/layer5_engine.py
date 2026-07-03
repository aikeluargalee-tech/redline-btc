"""
Layer 5 — Analysis Engine

Feeds all layers with market analysis data.
Provides AMT (Average Mean Temperature), CVD (Cumulative Volume Delta),
OI (Open Interest), and funding rate data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DataPacket:
    """BTC data packet from analysis engine."""
    amt_value: float
    amt_trend: str  # "rising", "falling", "neutral"
    cvd_value: float
    cvd_trend: str  # "positive", "negative", "rolling", "neutral"
    open_interest: float
    oi_change_24h: float  # Percentage
    funding_rate: float
    funding_rate_trend: str  # "rising", "falling", "neutral"
    liquidation_clusters: list[float]
    volume_profile_state: str  # "high_volume_node", "low_volume_node", "transitioning"


def load_data_packet(filepath: str = "/tmp/btc_data_packet.json") -> Optional[DataPacket]:
    """Load BTC data packet from JSON file.

    Args:
        filepath: Path to the data packet JSON file.

    Returns:
        DataPacket if file exists and is valid, None otherwise.
    """
    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        return DataPacket(
            amt_value=data.get("amt_value", 0.0),
            amt_trend=data.get("amt_trend", "neutral"),
            cvd_value=data.get("cvd_value", 0.0),
            cvd_trend=data.get("cvd_trend", "neutral"),
            open_interest=data.get("open_interest", 0.0),
            oi_change_24h=data.get("oi_change_24h", 0.0),
            funding_rate=data.get("funding_rate", 0.0),
            funding_rate_trend=data.get("funding_rate_trend", "neutral"),
            liquidation_clusters=data.get("liquidation_clusters", []),
            volume_profile_state=data.get("volume_profile_state", "neutral"),
        )
    except FileNotFoundError:
        logger.warning(f"Data packet file not found: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse data packet: {e}")
        return None


def get_mock_data_packet() -> DataPacket:
    """Get mock data packet for testing.

    Returns:
        Mock DataPacket with sample values.
    """
    return DataPacket(
        amt_value=0.45,
        amt_trend="falling",
        cvd_value=-125.5,
        cvd_trend="negative",
        open_interest=15_500_000_000,
        oi_change_24h=-2.3,
        funding_rate=-0.0012,
        funding_rate_trend="falling",
        liquidation_clusters=[41500.0, 42800.0, 43200.0],
        volume_profile_state="low_volume_node",
    )


def analyze_market_structure(data: DataPacket) -> dict:
    """Analyze market structure from data packet.

    Args:
        data: DataPacket with current market data.

    Returns:
        Dictionary with analysis results.
    """
    analysis = {
        "momentum": "bearish" if data.cvd_trend == "negative" else "bullish" if data.cvd_trend == "positive" else "neutral",
        "leverage": "high" if abs(data.oi_change_24h) > 5.0 else "normal",
        "funding_bias": "short" if data.funding_rate < 0 else "long" if data.funding_rate > 0 else "neutral",
        "liquidation_risk": len(data.liquidation_clusters) > 0,
        "volume_profile": data.volume_profile_state,
    }

    return analysis
