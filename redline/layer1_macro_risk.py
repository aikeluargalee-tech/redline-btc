"""
Layer 1 — Macro Risk Switch

Binary ON/OFF risk management layer that monitors macro triggers.
When ANY trigger fires, risk turns OFF and all swing/intraday positions
are closed or reduced.

Triggers:
1. MSTR daily close below threshold
2. VIX sustained above threshold
3. US10Y above threshold
4. USD/JPY spike + BoJ response
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


class RiskState(str, Enum):
    """Macro risk state."""
    ON = "ON"
    OFF = "OFF"


@dataclass
class MacroTriggers:
    """Current macro trigger values."""
    mstr_close: float
    vix_current: float
    us10y_current: float
    usdjpy_change_pct: float
    boj_verbal_response: bool
    mstr_sessions_below: int
    vix_sessions_above: int
    usdjpy_stable_hours: int
    btc_above_structure_low: bool


@dataclass
class RiskOutput:
    """Output of risk assessment."""
    state: RiskState
    triggered_by: list[str]
    details: str
    can_reactivate: bool
    reactivation_criteria_met: dict[str, bool]


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def check_risk_off_triggers(
    triggers: MacroTriggers,
    config: Optional[dict] = None
) -> tuple[bool, list[str]]:
    """Check if any risk-off triggers have fired.

    Args:
        triggers: Current macro trigger values.
        config: Optional config dict.

    Returns:
        Tuple of (should_turn_off, list_of_triggered_reasons).
    """
    if config is None:
        config = load_config()

    l1 = config["layer1"]
    off_cfg = l1["risk_off_triggers"]
    triggered = []

    # Trigger 1: MSTR daily close below threshold
    if triggers.mstr_close < off_cfg["mstr_daily_close_below"]:
        triggered.append(f"MSTR close {triggers.mstr_close:.2f} < {off_cfg['mstr_daily_close_below']}")

    # Trigger 2: VIX sustained above threshold
    if triggers.vix_current > off_cfg["vix_sustained_above"] and triggers.vix_sessions_above >= off_cfg["vix_sustained_sessions"]:
        triggered.append(f"VIX {triggers.vix_current:.2f} > {off_cfg['vix_sustained_above']} for {triggers.vix_sessions_above} sessions")

    # Trigger 3: US10Y above threshold
    if triggers.us10y_current > off_cfg["us10y_above"]:
        triggered.append(f"US10Y {triggers.us10y_current:.2f}% > {off_cfg['us10y_above']}%")

    # Trigger 4: USD/JPY spike + BoJ response
    if triggers.usdjpy_change_pct > off_cfg["usdjpy_spike_pct"] and triggers.boj_verbal_response:
        triggered.append(
            f"USD/JPY +{triggers.usdjpy_change_pct:.2f}% spike + BoJ response"
        )

    return len(triggered) > 0, triggered


def check_risk_on_criteria(
    triggers: MacroTriggers,
    config: Optional[dict] = None
) -> tuple[bool, dict[str, bool]]:
    """Check if all risk-on criteria are met for reactivation.

    ALL criteria must be satisfied to turn risk back ON.

    Args:
        triggers: Current macro trigger values.
        config: Optional config dict.

    Returns:
        Tuple of (all_criteria_met, dict_of_individual_criteria).
    """
    if config is None:
        config = load_config()

    l1 = config["layer1"]
    on_cfg = l1["risk_on_criteria"]

    criteria = {
        "mstr_above_2_sessions": triggers.mstr_sessions_below == 0 and triggers.mstr_close > on_cfg["mstr_threshold"],
        "vix_below_2_sessions": triggers.vix_sessions_above == 0 and triggers.vix_current < on_cfg["vix_threshold"],
        "us10y_below_threshold": triggers.us10y_current < on_cfg["us10y_below"],
        "usdjpy_stable_48h": triggers.usdjpy_stable_hours >= on_cfg["usdjpy_stable_hours"],
        "btc_above_structure_low": triggers.btc_above_structure_low == on_cfg["btc_structure_low_required"],
    }

    all_met = all(criteria.values())
    return all_met, criteria


def assess_macro_risk(
    triggers: MacroTriggers,
    current_state: RiskState = RiskState.ON,
    config: Optional[dict] = None
) -> RiskOutput:
    """Assess macro risk and determine if state should change.

    Args:
        triggers: Current macro trigger values.
        current_state: Current risk state.
        config: Optional config dict.

    Returns:
        RiskOutput with assessment results.
    """
    if config is None:
        config = load_config()

    # Check if we should turn risk OFF
    should_turn_off, triggered_by = check_risk_off_triggers(triggers, config)

    if should_turn_off:
        return RiskOutput(
            state=RiskState.OFF,
            triggered_by=triggered_by,
            details=f"Risk OFF triggered by: {'; '.join(triggered_by)}",
            can_reactivate=False,
            reactivation_criteria_met={},
        )

    # Check if we can turn risk back ON
    can_reactivate, criteria_met = check_risk_on_criteria(triggers, config)

    if current_state == RiskState.OFF and can_reactivate:
        return RiskOutput(
            state=RiskState.ON,
            triggered_by=[],
            details="All risk-on criteria met. Risk reactivated.",
            can_reactivate=True,
            reactivation_criteria_met=criteria_met,
        )

    # No change
    if current_state == RiskState.ON:
        return RiskOutput(
            state=RiskState.ON,
            triggered_by=[],
            details="Risk ON. No triggers fired.",
            can_reactivate=False,
            reactivation_criteria_met=criteria_met if not can_reactivate else {},
        )
    else:
        return RiskOutput(
            state=RiskState.OFF,
            triggered_by=triggered_by,
            details="Risk OFF. Criteria for reactivation not yet met.",
            can_reactivate=False,
            reactivation_criteria_met=criteria_met,
        )
