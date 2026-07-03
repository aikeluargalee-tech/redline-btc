"""
Layer 3 — Swing Trading (2-10 Day Trades)

Medium timeframe layer. Medium allocation (20%).
Entry: 4H structure break/reclaim + Daily S/R level + ADX<35
Bear rules: Longs only at major support (daily oversold + CVD positive + MVRV-Z<0.2)
Shorts on structure failures (4H+1D bearish + CVD rolling)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import yaml

from .layer0_regime import Regime

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


class SwingDirection(str, Enum):
    """Swing trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass
class SwingInputs:
    """Inputs for swing trade assessment."""
    regime: Regime
    btc_price: float
    structure_4h: str  # "bullish", "bearish", "neutral"
    structure_1d: str  # "bullish", "bearish", "neutral"
    daily_sr_level: str  # "support", "resistance", "neutral"
    adx_value: float
    cvd_trend: str  # "positive", "negative", "rolling", "neutral"
    daily_oversold: bool
    mvrv_z_score: float
    at_major_support: bool


@dataclass
class SwingOutput:
    """Output of swing trade assessment."""
    direction: SwingDirection
    entry_allowed: bool
    reasons: list[str]
    details: str
    allocation_pct: float


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def assess_swing_trade(
    inputs: SwingInputs,
    config: Optional[dict] = None
) -> SwingOutput:
    """Assess whether a swing trade entry is allowed.

    Entry requirements:
    - 4H structure break/reclaim
    - Daily S/R level alignment
    - ADX < 35 (not overextended)

    Bear regime additional rules:
    - Longs: only at major support + daily oversold + CVD positive + MVRV-Z < 0.2
    - Shorts: 4H+1D bearish + CVD rolling

    Args:
        inputs: SwingInputs with current market state.
        config: Optional config dict.

    Returns:
        SwingOutput with trade assessment.
    """
    if config is None:
        config = load_config()

    l3 = config["layer3"]
    entry_req = l3["entry_requirements"]
    bear_cfg = l3["bear_regime"]

    reasons = []
    allocation = l3["allocation_pct"]

    # Base entry requirements
    structure_valid = inputs.structure_4h in ["bullish", "bearish"]
    sr_valid = inputs.daily_sr_level in ["support", "resistance"]
    adx_valid = inputs.adx_value < entry_req["adx_below"]

    if not structure_valid:
        reasons.append("4H structure not in clear trend")
    if not sr_valid:
        reasons.append("Not at daily S/R level")
    if not adx_valid:
        reasons.append(f"ADX {inputs.adx_value:.1f} >= {entry_req['adx_below']} (overextended)")

    # Determine direction based on structure
    if inputs.structure_4h == "bullish" and inputs.structure_1d == "bullish":
        direction = SwingDirection.LONG
    elif inputs.structure_4h == "bearish" and inputs.structure_1d == "bearish":
        direction = SwingDirection.SHORT
    else:
        direction = SwingDirection.NONE
        reasons.append("No clear directional alignment on 4H+1D")

    # Apply regime-specific rules
    if inputs.regime == Regime.BEAR:
        if direction == SwingDirection.LONG:
            # Bear longs require all conditions
            bear_long_cfg = bear_cfg["longs"]
            if not inputs.at_major_support:
                reasons.append("BEAR: Not at major support")
            if not inputs.daily_oversold:
                reasons.append("BEAR: Daily not oversold")
            if inputs.cvd_trend != "positive":
                reasons.append(f"BEAR: CVD is {inputs.cvd_trend}, not positive")
            if inputs.mvrv_z_score >= bear_long_cfg["mvrv_z_below"]:
                reasons.append(f"BEAR: MVRV-Z {inputs.mvrv_z_score:.2f} >= {bear_long_cfg['mvrv_z_below']}")

        elif direction == SwingDirection.SHORT:
            # Bear shorts require bearish structure + CVD rolling
            bear_short_cfg = bear_cfg["shorts"]
            if inputs.cvd_trend not in ["negative", "rolling"]:
                reasons.append(f"BEAR: CVD is {inputs.cvd_trend}, need negative/rolling for shorts")

    # Check if entry is allowed
    entry_allowed = (
        structure_valid and
        sr_valid and
        adx_valid and
        direction != SwingDirection.NONE and
        len(reasons) == 0
    )

    details = (
        f"Swing {direction.value}: {'ALLOWED' if entry_allowed else 'BLOCKED'}. "
        f"4H={inputs.structure_4h}, 1D={inputs.structure_1d}, "
        f"ADX={inputs.adx_value:.1f}, CVD={inputs.cvd_trend}"
    )

    if reasons:
        details += f". Reasons: {'; '.join(reasons)}"

    return SwingOutput(
        direction=direction,
        entry_allowed=entry_allowed,
        reasons=reasons,
        details=details,
        allocation_pct=allocation,
    )
