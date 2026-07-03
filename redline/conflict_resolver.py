"""
Conflict Resolver — Inter-Layer Conflict Resolution

Resolves conflicts between layers using 5 rules:
1. Higher layer wins direction
2. Lower layers use smaller size (don't stack)
3. Contradiction → Type C scalp only, no Type A against higher layer
4. Escalation: losing intraday must meet swing criteria to hold
5. Capital isolation: each layer has own loss limit
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import yaml

from .layer0_regime import Regime
from .layer3_swing import SwingDirection
from .layer4_intraday import IntradayDirection, TradeType

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


class ConflictAction(str, Enum):
    """Action to take when conflict is detected."""
    ALLOW = "allow"
    REDUCE_SIZE = "reduce_size"
    DOWNGRADE_TO_SCALP = "downgrade_to_scalp"
    BLOCK = "block"
    ESCALATE_TO_SWING = "escalate_to_swing"


@dataclass
class ConflictInput:
    """Input for conflict resolution."""
    layer0_regime: Regime
    layer2_direction: Optional[str]  # "long", "short", "neutral"
    layer3_direction: SwingDirection
    layer4_direction: IntradayDirection
    layer4_trade_type: TradeType
    layer4_pnl_pct: float  # Current P&L percentage
    layer3_meets_swing_criteria: bool


@dataclass
class ConflictOutput:
    """Output of conflict resolution."""
    action: ConflictAction
    size_multiplier: float
    allowed_trade_type: TradeType
    reasons: list[str]
    details: str


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def resolve_conflicts(
    inputs: ConflictInput,
    config: Optional[dict] = None
) -> ConflictOutput:
    """Resolve conflicts between layers.

    Rules (in order):
    1. Higher layer wins direction
    2. Lower layers use smaller size (don't stack)
    3. Contradiction → Type C scalp only
    4. Escalation: losing intraday must meet swing criteria to hold
    5. Capital isolation: each layer has own loss limit

    Args:
        inputs: ConflictInput with current state.
        config: Optional config dict.

    Returns:
        ConflictOutput with resolution.
    """
    if config is None:
        config = load_config()

    reasons = []
    size_multiplier = 1.0
    allowed_type = inputs.layer4_trade_type
    action = ConflictAction.ALLOW

    # Rule 1: Higher layer wins direction
    # Layer 2 > Layer 3 > Layer 4
    if inputs.layer2_direction and inputs.layer2_direction != "neutral":
        if inputs.layer4_direction == IntradayDirection.LONG and inputs.layer2_direction == "short":
            reasons.append("Rule 1: L4 long contradicts L2 short direction")
            action = ConflictAction.DOWNGRADE_TO_SCALP
            allowed_type = TradeType.TYPE_C
            size_multiplier *= 0.5
        elif inputs.layer4_direction == IntradayDirection.SHORT and inputs.layer2_direction == "long":
            reasons.append("Rule 1: L4 short contradicts L2 long direction")
            action = ConflictAction.DOWNGRADE_TO_SCALP
            allowed_type = TradeType.TYPE_C
            size_multiplier *= 0.5

    # Rule 1b: Layer 3 > Layer 4 contradiction
    if inputs.layer3_direction != SwingDirection.NONE:
        if (inputs.layer3_direction == SwingDirection.LONG and inputs.layer4_direction == IntradayDirection.SHORT) or \
           (inputs.layer3_direction == SwingDirection.SHORT and inputs.layer4_direction == IntradayDirection.LONG):
            reasons.append("Rule 1b: L4 contradicts L3 direction — downgrade to scalp")
            if action != ConflictAction.BLOCK:
                action = ConflictAction.DOWNGRADE_TO_SCALP
                allowed_type = TradeType.TYPE_C
                size_multiplier *= 0.5

    # Rule 2: Lower layers use smaller size (don't stack)
    if inputs.layer3_direction != SwingDirection.NONE:
        if (inputs.layer3_direction == SwingDirection.LONG and inputs.layer4_direction == IntradayDirection.LONG) or \
           (inputs.layer3_direction == SwingDirection.SHORT and inputs.layer4_direction == IntradayDirection.SHORT):
            reasons.append("Rule 2: L4 stacking with L3 direction - reducing size")
            size_multiplier *= 0.7

    # Rule 3: Contradiction → Type C scalp only
    if action == ConflictAction.DOWNGRADE_TO_SCALP:
        if inputs.layer4_trade_type != TradeType.TYPE_C:
            reasons.append(f"Rule 3: Downgrading from {inputs.layer4_trade_type.value} to Type C scalp")

    # Rule 4: Escalation - losing intraday must meet swing criteria
    if inputs.layer4_pnl_pct < -1.0:  # Losing more than 1%
        if not inputs.layer3_meets_swing_criteria:
            reasons.append("Rule 4: L4 losing trade doesn't meet swing criteria - should close")
            action = ConflictAction.BLOCK

    # Rule 5: Capital isolation (checked in sizing layer)
    # This is enforced by the sizing module, not here

    # Apply floor to prevent excessive reduction
    size_multiplier = max(size_multiplier, 0.3)

    # Determine final action
    if action == ConflictAction.BLOCK:
        details = f"BLOCKED: {'; '.join(reasons)}"
    elif action == ConflictAction.DOWNGRADE_TO_SCALP:
        details = f"DOWNGRADED to Type C scalp: {'; '.join(reasons)}"
    elif size_multiplier < 1.0:
        details = f"SIZE REDUCED to {size_multiplier*100:.0f}%: {'; '.join(reasons)}"
    else:
        details = "ALLOWED: No conflicts detected"

    return ConflictOutput(
        action=action,
        size_multiplier=size_multiplier,
        allowed_trade_type=allowed_type,
        reasons=reasons,
        details=details,
    )


def check_capital_isolation(
    layer_name: str,
    current_loss_pct: float,
    config: Optional[dict] = None
) -> tuple[bool, float]:
    """Check if a layer has exceeded its daily loss limit.

    Args:
        layer_name: Name of the layer (e.g., "layer2", "layer3", "layer4").
        current_loss_pct: Current loss percentage (negative number).
        config: Optional config dict.

    Returns:
        Tuple of (is_allowed, remaining_loss_budget).
    """
    if config is None:
        config = load_config()

    sizing_cfg = config["sizing"]
    loss_limits = sizing_cfg["loss_limits"]

    limit_key = f"{layer_name}_daily"
    if limit_key not in loss_limits:
        logger.warning(f"No loss limit configured for {layer_name}")
        return True, 0.0

    daily_limit = loss_limits[limit_key]
    remaining = daily_limit + current_loss_pct  # current_loss_pct is negative

    is_allowed = remaining > 0
    return is_allowed, max(0.0, remaining)
