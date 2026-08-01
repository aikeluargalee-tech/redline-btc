"""
Trading Checklists

Pre-session, intraday, and end-of-day checklists for systematic trading.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ChecklistResult:
    """Result of checklist evaluation."""
    passed: bool
    items_checked: int
    items_passed: int
    failed_items: list[str]
    details: str


def pre_session_checklist(
    regime: str,
    macro_risk_state: str,
    macro_short_active: bool,
    layer2_position_checked: bool = True,
    key_levels_identified: bool = True,
    session_context_known: bool = True,
) -> ChecklistResult:
    """Pre-session checklist before starting trading.

    Args:
        regime: Current regime (BULL/BEAR/TRANSITIONAL).
        macro_risk_state: Macro risk state (ON/OFF).
        macro_short_active: Whether macro short is active.
        layer2_position_checked: Whether L2 positions are reviewed.
        key_levels_identified: Whether key S/R levels are identified.
        session_context_known: Whether session context is understood.

    Returns:
        ChecklistResult with pass/fail status.
    """
    items = {
        "regime_identified": regime in ["BULL", "BEAR", "TRANSITIONAL"],
        "macro_risk_assessed": macro_risk_state in ["ON", "OFF"],
        "macro_short_status": True,  # Always passes, just informational
        "layer2_reviewed": layer2_position_checked,
        "key_levels_set": key_levels_identified,
        "session_context": session_context_known,
    }

    failed = [k for k, v in items.items() if not v]
    passed = len(failed) == 0

    details = (
        f"Pre-session: {'PASS' if passed else 'FAIL'}. "
        f"Regime={regime}, Risk={macro_risk_state}, "
        f"MacroShort={'Active' if macro_short_active else 'Inactive'}"
    )

    if failed:
        details += f". Failed: {', '.join(failed)}"

    return ChecklistResult(
        passed=passed,
        items_checked=len(items),
        items_passed=len(items) - len(failed),
        failed_items=failed,
        details=details,
    )


def intraday_checklist(
    entry_price: float,
    stop_loss: float,
    target: float,
    risk_reward_ratio: float,
    position_size_valid: bool = True,
    conflict_resolved: bool = True,
    layer_alignment: bool = True,
) -> ChecklistResult:
    """Intraday entry checklist before taking a trade.

    Args:
        entry_price: Entry price.
        stop_loss: Stop loss price.
        target: Target price.
        risk_reward_ratio: Risk/reward ratio.
        position_size_valid: Whether position size is within limits.
        conflict_resolved: Whether conflicts are resolved.
        layer_alignment: Whether layers are aligned.

    Returns:
        ChecklistResult with pass/fail status.
    """
    items = {
        "entry_set": entry_price > 0,
        "stop_set": stop_loss > 0,
        "target_set": target > 0,
        "risk_reward_acceptable": risk_reward_ratio >= 1.5,
        "size_valid": position_size_valid,
        "conflicts_resolved": conflict_resolved,
        "layers_aligned": layer_alignment,
    }

    failed = [k for k, v in items.items() if not v]
    passed = len(failed) == 0

    details = (
        f"Intraday entry: {'PASS' if passed else 'FAIL'}. "
        f"Entry={entry_price:.0f}, SL={stop_loss:.0f}, TP={target:.0f}, "
        f"R:R={risk_reward_ratio:.2f}"
    )

    if failed:
        details += f". Failed: {', '.join(failed)}"

    return ChecklistResult(
        passed=passed,
        items_checked=len(items),
        items_passed=len(items) - len(failed),
        failed_items=failed,
        details=details,
    )


def layer6_heatmap_checklist(
    signal_direction: str,
    heatmap_go: bool,
    heatmap_reason: str,
    heatmap_warning: str,
    requires_manual_review: bool = False,
    data_available: bool = False,
    staleness_minutes: Optional[int] = None,
) -> ChecklistResult:
    """Layer 6: Heatmap entry gate checklist.

    Final validation before pulling the trigger. Runs after L4 signal
    generation, before execution routing.

    Args:
        signal_direction: Trade direction (LONG/SHORT/NONE).
        heatmap_go: Whether heatmap gate allows entry.
        heatmap_reason: Reason for go/no-go verdict.
        heatmap_warning: Non-blocking warnings.
        requires_manual_review: Whether visual verification is needed.
        data_available: Whether heatmap data was available.
        staleness_minutes: Minutes since last capture.

    Returns:
        ChecklistResult with pass/fail status.
    """
    items = {
        "heatmap_data_available": data_available,
        "heatmap_aligned": heatmap_go,
        "manual_review_needed": not requires_manual_review,
        "signal_direction_set": signal_direction in ("LONG", "SHORT"),
    }

    failed = [k for k, v in items.items() if not v]

    # Manual review needed is a warning, not a hard fail — remove first so the
    # no-data combo (data_available=False + requires_manual_review=True) is
    # correctly treated as a warning, not a fail (M8).
    if "manual_review_needed" in failed:
        failed.remove("manual_review_needed")
    # Heatmap unavailable is NOT a fail — it's a warning
    if "heatmap_data_available" in failed and len(failed) == 1:
        failed = []

    passed = len(failed) == 0

    stale_str = f" | staleness: {staleness_minutes}m" if staleness_minutes else ""
    details = (
        f"L6 Heatmap: {'PASS' if passed else 'FAIL'}. "
        f"Go={heatmap_go}, Dir={signal_direction}{stale_str}. "
        f"{heatmap_reason}"
    )

    if heatmap_warning:
        details += f" ⚠️ {heatmap_warning}"

    if failed:
        details += f". Failed: {', '.join(failed)}"

    return ChecklistResult(
        passed=passed,
        items_checked=len(items),
        items_passed=len(items) - len(failed),
        failed_items=failed,
        details=details,
    )


def end_of_day_checklist(
    positions_reviewed: bool = True,
    pnl_recorded: bool = True,
    journal_updated: bool = True,
    lessons_noted: bool = True,
    tomorrow_prep: bool = True,
) -> ChecklistResult:
    """End-of-day checklist after trading session.

    Args:
        positions_reviewed: Whether all positions are reviewed.
        pnl_recorded: Whether P&L is recorded.
        journal_updated: Whether trading journal is updated.
        lessons_noted: Whether lessons are noted.
        tomorrow_prep: Whether tomorrow's plan is prepared.

    Returns:
        ChecklistResult with pass/fail status.
    """
    items = {
        "positions_reviewed": positions_reviewed,
        "pnl_recorded": pnl_recorded,
        "journal_updated": journal_updated,
        "lessons_noted": lessons_noted,
        "tomorrow_prepared": tomorrow_prep,
    }

    failed = [k for k, v in items.items() if not v]
    passed = len(failed) == 0

    details = f"End-of-day: {'PASS' if passed else 'FAIL'}. {len(items) - len(failed)}/{len(items)} items completed"

    if failed:
        details += f". Pending: {', '.join(failed)}"

    return ChecklistResult(
        passed=passed,
        items_checked=len(items),
        items_passed=len(items) - len(failed),
        failed_items=failed,
        details=details,
    )
