"""
Layer 2 — Weekly Positioning (Spot Accumulation)

Longest timeframe layer (weeks to months). Largest allocation (40%).
In bear regime: accumulate spot BTC in tranches.
1x spot only in bear. No leveraged longs.
No stops on accumulation tranches (cycle positions).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import yaml

from .layer0_regime import Regime

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


@dataclass
class TrancheLevel:
    """Definition of a single accumulation tranche."""
    name: str
    range_low: float
    range_high: float
    allocation_pct: float
    filled: bool = False


@dataclass
class PositioningInput:
    """Inputs for positioning assessment."""
    regime: Regime
    btc_price: float
    total_capital: float
    current_position: float  # Current BTC held
    tranches_filled: list[str]  # Names of already-filled tranches


@dataclass
class PositioningOutput:
    """Output of positioning assessment."""
    action: str  # "accumulate", "hold", "none"
    tranche: Optional[TrancheLevel]
    amount_usd: float
    btc_amount: float
    details: str
    total_allocation_pct: float


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_tranches(config: dict) -> list[TrancheLevel]:
    """Get tranche definitions from config.

    Args:
        config: Configuration dictionary.

    Returns:
        List of TrancheLevel objects.
    """
    l2 = config["layer2"]
    tranches_cfg = l2["bear_regime"]["accumulation_tranches"]

    tranches = []
    for name, cfg in tranches_cfg.items():
        tranches.append(TrancheLevel(
            name=name.upper(),
            range_low=cfg["range"][0],
            range_high=cfg["range"][1],
            allocation_pct=cfg["allocation_pct"],
        ))

    return tranches


def assess_positioning(
    inputs: PositioningInput,
    config: Optional[dict] = None
) -> PositioningOutput:
    """Assess current positioning and determine next action.

    In bear regime:
    - Only spot accumulation (1x, no leverage)
    - Accumulate in tranches at predefined price levels
    - No stops on cycle positions

    Args:
        inputs: PositioningInput with current state.
        config: Optional config dict.

    Returns:
        PositioningOutput with recommended action.
    """
    if config is None:
        config = load_config()

    l2 = config["layer2"]

    # Only accumulate in bear regime
    if inputs.regime != Regime.BEAR:
        return PositioningOutput(
            action="none",
            tranche=None,
            amount_usd=0.0,
            btc_amount=0.0,
            details=f"Regime is {inputs.regime.value}. No accumulation in non-bear regimes.",
            total_allocation_pct=0.0,
        )

    # Get tranche definitions
    tranches = get_tranches(config)

    # Find which tranche (if any) should be filled
    for tranche in tranches:
        if tranche.name in inputs.tranches_filled:
            continue  # Already filled

        if inputs.btc_price <= tranche.range_high and inputs.btc_price >= tranche.range_low:
            # Price is in this tranche's range
            # Tranche allocation is a fraction OF the L2 bucket, not of total capital.
            # L2 bucket = total_capital * l2.allocation_pct (e.g. 40%); each tranche
            # (0.33) applies within that bucket → ~13% of total capital per tranche.
            bucket = inputs.total_capital * l2["allocation_pct"]
            amount_usd = bucket * tranche.allocation_pct
            btc_amount = amount_usd / inputs.btc_price if inputs.btc_price > 0 else 0.0

            return PositioningOutput(
                action="accumulate",
                tranche=tranche,
                amount_usd=amount_usd,
                btc_amount=btc_amount,
                details=(
                    f"ACCUMULATE {tranche.name}: Price {inputs.btc_price:.0f} "
                    f"in range [{tranche.range_low:.0f}, {tranche.range_high:.0f}]. "
                    f"Allocate ${amount_usd:.0f} "
                    f"({tranche.allocation_pct*100:.0f}% of {l2['allocation_pct']*100:.0f}% L2 bucket = "
                    f"{tranche.allocation_pct*l2['allocation_pct']*100:.1f}% of capital)."
                ),
                total_allocation_pct=l2["allocation_pct"],
            )

    # No tranche triggered
    return PositioningOutput(
        action="hold",
        tranche=None,
        amount_usd=0.0,
        btc_amount=0.0,
        details=(
            f"HOLD: Price {inputs.btc_price:.0f} not in any unfilled tranche range. "
            f"Current position: {inputs.current_position:.8f} BTC."
        ),
        total_allocation_pct=l2["allocation_pct"],
    )


def check_leverage_allowed(regime: Regime, config: Optional[dict] = None) -> bool:
    """Check if leverage is allowed for Layer 2 positions.

    In bear regime: spot only (1x), no leveraged longs.
    In bull regime: leverage up to 2x allowed.
    In transitional regime: leverage up to 1.5x allowed.

    Args:
        regime: Current market regime.
        config: Optional config dict.

    Returns:
        True if leverage is allowed, False otherwise.
    """
    if config is None:
        config = load_config()

    l2 = config["layer2"]
    regime_key = f"{regime.value.lower()}_regime"
    return l2[regime_key]["leverage_max"] > 1.0


def stops_enabled(config: Optional[dict] = None) -> bool:
    """Check if stops are enabled for Layer 2 positions.

    Cycle positions typically have no stops.

    Args:
        config: Optional config dict.

    Returns:
        True if stops are enabled, False otherwise.
    """
    if config is None:
        config = load_config()

    l2 = config["layer2"]
    return l2["bear_regime"]["stops_enabled"]
