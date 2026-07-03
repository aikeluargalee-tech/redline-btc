"""
Layer 4 — Intraday Trading (Hours Timeframe)

Shortest timeframe layer. Smallest allocation (10%).
Entry checklist (ALL must clear):
- ADX direction, MTF alignment, CVD invalidation
- Price vs liq cluster, VP state, session context
- Layer 3 alignment

Types: A (trend continuation), B (mean reversion), C (scalp)
Bear rules: Longs = Type B/C only. All short types permitted.
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


class TradeType(str, Enum):
    """Intraday trade type."""
    TYPE_A = "type_a"  # Trend continuation
    TYPE_B = "type_b"  # Mean reversion
    TYPE_C = "type_c"  # Scalp


class IntradayDirection(str, Enum):
    """Intraday trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass
class IntradayInputs:
    """Inputs for intraday trade assessment."""
    regime: Regime
    direction: IntradayDirection
    trade_type: TradeType
    adx_direction: bool
    mtf_alignment: bool
    cvd_invalidation: bool
    price_vs_liq_cluster: bool
    vp_state: bool
    session_context: bool
    layer3_alignment: bool


@dataclass
class IntradayOutput:
    """Output of intraday trade assessment."""
    entry_allowed: bool
    checklist_results: dict[str, bool]
    trade_type_allowed: bool
    reasons: list[str]
    details: str
    allocation_pct: float


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def check_entry_checklist(
    inputs: IntradayInputs,
    config: Optional[dict] = None
) -> tuple[bool, dict[str, bool], list[str]]:
    """Check if all intraday entry checklist items pass.

    ALL items must clear for entry to be allowed.

    Args:
        inputs: IntradayInputs with current state.
        config: Optional config dict.

    Returns:
        Tuple of (all_passed, checklist_results, failed_reasons).
    """
    checklist = {
        "adx_direction": inputs.adx_direction,
        "mtf_alignment": inputs.mtf_alignment,
        "cvd_invalidation": inputs.cvd_invalidation,
        "price_vs_liq_cluster": inputs.price_vs_liq_cluster,
        "vp_state": inputs.vp_state,
        "session_context": inputs.session_context,
        "layer3_alignment": inputs.layer3_alignment,
    }

    failed = [k for k, v in checklist.items() if not v]
    all_passed = len(failed) == 0

    return all_passed, checklist, failed


def is_trade_type_allowed(
    direction: IntradayDirection,
    trade_type: TradeType,
    regime: Regime,
    config: Optional[dict] = None
) -> bool:
    """Check if a specific trade type is allowed for the direction/regime.

    Bear regime rules:
    - Longs: Type B/C only (no Type A trend continuation longs)
    - Shorts: All types permitted

    Args:
        direction: Trade direction.
        trade_type: Trade type (A, B, or C).
        regime: Current market regime.
        config: Optional config dict.

    Returns:
        True if trade type is allowed, False otherwise.
    """
    if config is None:
        config = load_config()

    l4 = config["layer4"]
    bear_cfg = l4["bear_regime"]

    if regime == Regime.BEAR:
        if direction == IntradayDirection.LONG:
            allowed_types = bear_cfg["longs"]["allowed_types"]
            return trade_type.value in allowed_types
        elif direction == IntradayDirection.SHORT:
            allowed_types = bear_cfg["shorts"]["allowed_types"]
            return trade_type.value in allowed_types

    # Non-bear regimes: all types allowed
    return True


def assess_intraday_trade(
    inputs: IntradayInputs,
    config: Optional[dict] = None
) -> IntradayOutput:
    """Assess whether an intraday trade entry is allowed.

    Args:
        inputs: IntradayInputs with current state.
        config: Optional config dict.

    Returns:
        IntradayOutput with trade assessment.
    """
    if config is None:
        config = load_config()

    l4 = config["layer4"]
    allocation = l4["allocation_pct"]

    # Check entry checklist
    checklist_passed, checklist_results, failed_items = check_entry_checklist(inputs, config)

    # Check trade type allowance
    trade_type_allowed = is_trade_type_allowed(
        inputs.direction,
        inputs.trade_type,
        inputs.regime,
        config
    )

    reasons = []
    if not checklist_passed:
        reasons.append(f"Checklist failed: {', '.join(failed_items)}")
    if not trade_type_allowed:
        reasons.append(
            f"Trade type {inputs.trade_type.value} not allowed for "
            f"{inputs.direction.value} in {inputs.regime.value} regime"
        )

    entry_allowed = checklist_passed and trade_type_allowed

    details = (
        f"Intraday {inputs.direction.value} ({inputs.trade_type.value}): "
        f"{'ALLOWED' if entry_allowed else 'BLOCKED'}. "
        f"Checklist: {sum(checklist_results.values())}/{len(checklist_results)} passed"
    )

    if reasons:
        details += f". Reasons: {'; '.join(reasons)}"

    return IntradayOutput(
        entry_allowed=entry_allowed,
        checklist_results=checklist_results,
        trade_type_allowed=trade_type_allowed,
        reasons=reasons,
        details=details,
        allocation_pct=allocation,
    )
