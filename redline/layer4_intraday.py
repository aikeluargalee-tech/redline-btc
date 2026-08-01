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


@dataclass
class HeatmapCluster:
    """A single liquidity cluster from the heatmap."""
    price: float
    distance_pct: float      # % from current price (positive=above, negative=below)
    distance_usd: float
    density: str             # "Dense 🔥" | "Moderate" | "Scattered" | "None"
    cluster_width_usd: float


@dataclass
class HeatmapGateInput:
    """Inputs for Layer 6 heatmap entry gate."""
    signal_direction: IntradayDirection
    current_price: float
    nearest_above: Optional[HeatmapCluster] = None
    nearest_below: Optional[HeatmapCluster] = None
    cluster_spread_usd: Optional[float] = None
    tightness: str = "Unknown"
    vice_grip: bool = False
    staleness_minutes: Optional[int] = None
    data_available: bool = False
    confidence: str = "Unknown"


@dataclass
class HeatmapGateOutput:
    """Output of Layer 6 heatmap entry gate assessment."""
    go: bool
    reason: str
    warning: str                # Non-blocking caveat
    requires_manual_review: bool


def _norm_density(d: str) -> str:
    """Normalize heatmap density strings — packet format may vary
    ('Dense 🔥', 'dense', 'DENSE', 'Moderate', 'scattered', etc.). (M3)"""
    if not d:
        return ""
    s = str(d).strip().lower().replace("🔥", "").replace("🔥", "").strip()
    if "dense" in s:
        return "dense"
    if "moderate" in s or "medium" in s:
        return "moderate"
    if "scatter" in s or "thin" in s:
        return "scattered"
    if "none" in s or not s:
        return "none"
    return s


def assess_heatmap_gate(inputs: HeatmapGateInput) -> HeatmapGateOutput:
    """Layer 6: Validate L4 signal against live heatmap liquidity clusters.

    GetClaw's rules:
    1. Thick brick wall at entry level → respect it, don't trade through it
    2. Thin cluster near entry → likely already swept, OK to enter
    3. Staleness > 15 min on thin clusters → flag warning
    4. Direction mismatch (long into overhead resistance cluster) → no-go
    5. Vice Grip (< $500 spread) → breakout imminent, adjust entry accordingly
    6. Dense clusters block, scattered clusters allow

    Args:
        inputs: HeatmapGateInput with current heatmap state.

    Returns:
        HeatmapGateOutput with go/no-go verdict.
    """
    # No heatmap data available — allow entry (can't gate what you can't see)
    if not inputs.data_available:
        return HeatmapGateOutput(
            go=True,
            reason="No heatmap data available — cannot validate, proceed with caution",
            warning="Run V7 heatmap capture for Layer 6 validation",
            requires_manual_review=True,
        )

    # Stale data — allow but warn
    if inputs.staleness_minutes and inputs.staleness_minutes > 60:
        return HeatmapGateOutput(
            go=True,
            reason=f"Heatmap data {inputs.staleness_minutes}m stale — treating as unavailable",
            warning="Capture fresh heatmap before sizing up",
            requires_manual_review=True,
        )

    warnings = []
    blocks = []

    direction = inputs.signal_direction

    # Rule 1&2: Check cluster density at the entry direction
    if direction == IntradayDirection.LONG:
        # For longs: look at overhead cluster (nearest_above)
        above = inputs.nearest_above
        if above:
            density = above.density
            dist_pct = abs(above.distance_pct) if above.distance_pct else 0

            # Thick brick wall near entry → block
            if _norm_density(density) == "dense" and dist_pct <= 2.0:
                blocks.append(
                    f"Dense overhead cluster at ${above.price:,.0f} "
                    f"(+{dist_pct:.1f}%) — wall unbroken, long entry blocked"
                )
            elif _norm_density(density) == "moderate" and dist_pct <= 1.0:
                blocks.append(
                    f"Moderate overhead cluster at ${above.price:,.0f} "
                    f"(+{dist_pct:.1f}%) — tight proximity, wait for clearance"
                )
            elif _norm_density(density) == "scattered" and dist_pct <= 0.5:
                warnings.append(
                    f"Thin overhead cluster at ${above.price:,.0f} "
                    f"(+{dist_pct:.1f}%) — likely already swept, monitor"
                )

        # Below cluster: check if support is thin
        below = inputs.nearest_below
        if below and below._norm_density(density) == "scattered":
            warnings.append(
                f"Thin support at ${below.price:,.0f} "
                f"({below.distance_pct:.1f}%) — may not hold on retest"
            )

    elif direction == IntradayDirection.SHORT:
        # For shorts: look at support cluster (nearest_below)
        below = inputs.nearest_below
        if below:
            density = below.density
            dist_pct = abs(below.distance_pct) if below.distance_pct else 0

            # Thick brick wall below → block
            if _norm_density(density) == "dense" and dist_pct <= 2.0:
                blocks.append(
                    f"Dense support cluster at ${below.price:,.0f} "
                    f"({below.distance_pct:.1f}%) — thick floor, short entry blocked"
                )
            elif _norm_density(density) == "moderate" and dist_pct <= 1.0:
                blocks.append(
                    f"Moderate support cluster at ${below.price:,.0f} "
                    f"({below.distance_pct:.1f}%) — tight, wait for breakdown"
                )
            elif _norm_density(density) == "scattered" and dist_pct <= 0.5:
                warnings.append(
                    f"Thin support at ${below.price:,.0f} "
                    f"({below.distance_pct:.1f}%) — likely breakable"
                )

        # Above cluster: check if resistance is thin
        above = inputs.nearest_above
        if above and above._norm_density(density) == "scattered":
            warnings.append(
                f"Thin resistance at ${above.price:,.0f} "
                f"(+{above.distance_pct:.1f}%) — not a reliable cap"
            )

    # Rule 5: Vice Grip check
    if inputs.vice_grip:
        warnings.append(
            f"Vice Grip: cluster spread ≤ $500 — breakout imminent, "
            f"use tight stops and expect volatility"
        )

    # Staleness warning on thin clusters
    if inputs.staleness_minutes and inputs.staleness_minutes > 15:
        has_thin = (
            (inputs.nearest_above and inputs.nearest_above._norm_density(density) == "scattered")
            or (inputs.nearest_below and inputs.nearest_below._norm_density(density) == "scattered")
        )
        if has_thin:
            warnings.append(
                f"Heatmap {inputs.staleness_minutes}m stale — "
                f"thin clusters may have shifted"
            )

    # Confidence check
    if inputs.confidence in ("vision_misread", "Low"):
        warnings.append(
            f"Low heatmap confidence ({inputs.confidence}) — "
            f"verify visually before entry"
        )

    go = len(blocks) == 0
    if blocks:
        reason = "; ".join(blocks)
    elif inputs.nearest_above is None and inputs.nearest_below is None:
        reason = "No clusters near current price — no blocking liquidity"
    else:
        reason = "Heatmap alignment OK — no blocking clusters"
    warning = "; ".join(warnings) if warnings else ""
    requires_manual_review = bool(inputs.staleness_minutes and inputs.staleness_minutes > 15)

    return HeatmapGateOutput(
        go=go,
        reason=reason,
        warning=warning,
        requires_manual_review=requires_manual_review,
    )


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
    # A NONE direction is a no-signal state — never a valid entry
    if inputs.direction == IntradayDirection.NONE:
        reasons.append("No directional signal (direction=NONE)")
    if not checklist_passed:
        reasons.append(f"Checklist failed: {', '.join(failed_items)}")
    if not trade_type_allowed:
        reasons.append(
            f"Trade type {inputs.trade_type.value} not allowed for "
            f"{inputs.direction.value} in {inputs.regime.value} regime"
        )

    entry_allowed = (
        inputs.direction != IntradayDirection.NONE
        and checklist_passed
        and trade_type_allowed
    )

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
