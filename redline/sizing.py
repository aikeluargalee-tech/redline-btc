"""
Position Sizing Calculator

Calculates position sizes based on:
- Base risk percentage
- Layer multipliers
- Regime adjustments
- Loss limits per layer
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
class SizingInput:
    """Inputs for position sizing."""
    layer_name: str  # "layer2", "layer3", "layer4"
    regime: Regime
    account_balance: float
    entry_price: float
    stop_loss_price: float
    conflict_size_multiplier: float = 1.0  # From conflict resolver


@dataclass
class SizingOutput:
    """Output of position sizing."""
    position_size_usd: float
    position_size_btc: float
    risk_amount_usd: float
    risk_pct: float
    leverage: float
    details: str


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def calculate_position_size(
    inputs: SizingInput,
    config: Optional[dict] = None
) -> SizingOutput:
    """Calculate position size based on risk parameters.

    Formula:
    1. Base risk = account_balance * base_risk_pct
    2. Layer adjustment = base_risk * layer_multiplier
    3. Regime adjustment = layer_adjustment * regime_multiplier
    4. Conflict adjustment = regime_adjustment * conflict_multiplier
    5. Position size = risk_amount / (entry - stop) * entry

    Args:
        inputs: SizingInput with parameters.
        config: Optional config dict.

    Returns:
        SizingOutput with calculated position size.
    """
    if config is None:
        config = load_config()

    sizing_cfg = config["sizing"]
    base_risk_pct = sizing_cfg["base_risk_pct"]
    max_position = sizing_cfg["max_position_size_usd"]
    layer_mult = sizing_cfg["layer_multipliers"].get(inputs.layer_name, 1.0)
    regime_adj = sizing_cfg["regime_adjustments"].get(inputs.regime.value.lower(), 1.0)

    # Calculate risk amount
    base_risk = inputs.account_balance * base_risk_pct
    layer_adjusted = base_risk * layer_mult
    regime_adjusted = layer_adjusted * regime_adj
    final_risk = regime_adjusted * inputs.conflict_size_multiplier

    # Calculate position size
    price_diff = abs(inputs.entry_price - inputs.stop_loss_price)
    if price_diff == 0:
        logger.error("Entry and stop loss are the same price")
        return SizingOutput(
            position_size_usd=0.0,
            position_size_btc=0.0,
            risk_amount_usd=0.0,
            risk_pct=0.0,
            leverage=1.0,
            details="ERROR: Entry and stop loss are the same price",
        )

    position_size_usd = (final_risk / price_diff) * inputs.entry_price
    position_size_usd = min(position_size_usd, max_position)
    actual_risk_usd = position_size_usd / inputs.entry_price * price_diff if inputs.entry_price > 0 else 0

    position_size_btc = position_size_usd / inputs.entry_price if inputs.entry_price > 0 else 0
    risk_pct = (actual_risk_usd / inputs.account_balance) * 100 if inputs.account_balance > 0 else 0
    leverage = position_size_usd / inputs.account_balance if inputs.account_balance > 0 else 1.0

    details = (
        f"Position: ${position_size_usd:.0f} ({position_size_btc:.6f} BTC). "
        f"Risk: ${final_risk:.0f} ({risk_pct:.2f}%). "
        f"Leverage: {leverage:.2f}x. "
        f"Layer mult: {layer_mult}, Regime adj: {regime_adj}, "
        f"Conflict adj: {inputs.conflict_size_multiplier}"
    )

    return SizingOutput(
        position_size_usd=position_size_usd,
        position_size_btc=position_size_btc,
        risk_amount_usd=actual_risk_usd,
        risk_pct=risk_pct,
        leverage=leverage,
        details=details,
    )


def check_loss_limit(
    layer_name: str,
    daily_loss_pct: float,
    config: Optional[dict] = None
) -> tuple[bool, float]:
    """Check if layer has exceeded daily loss limit.

    Args:
        layer_name: Layer name (e.g., "layer2", "layer3", "layer4").
        daily_loss_pct: Current daily loss percentage (negative).
        config: Optional config dict.

    Returns:
        Tuple of (can_trade, remaining_budget_pct).
    """
    if config is None:
        config = load_config()

    sizing_cfg = config["sizing"]
    loss_limits = sizing_cfg["loss_limits"]

    limit_key = f"{layer_name}_daily"
    if limit_key not in loss_limits:
        return True, 0.0

    daily_limit = loss_limits[limit_key]
    remaining = daily_limit + daily_loss_pct  # daily_loss_pct is negative

    can_trade = remaining > 0
    return can_trade, max(0.0, remaining)
