"""
Layer 1.5 — Macro Short Activation (Emergency Mode)

Emergency short mode that activates ONLY when Layer 1 = Risk OFF.
Does NOT run concurrently with normal trading operations.

Entry: Layer 1 triggered + BTC below key structure
TP: $58,872 → $55K → $48K (partial closes)
SL: Above trigger event level
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import yaml

from .layer1_macro_risk import RiskState

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


@dataclass
class MacroShortInput:
    """Inputs for macro short activation."""
    layer1_state: RiskState
    btc_price: float
    btc_key_structure_low: float
    trigger_event_level: float


@dataclass
class MacroShortOutput:
    """Output of macro short assessment."""
    activated: bool
    entry_price: Optional[float]
    tp1: float
    tp2: float
    tp3: float
    stop_loss: float
    details: str


def load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def assess_macro_short(
    inputs: MacroShortInput,
    config: Optional[dict] = None
) -> MacroShortOutput:
    """Assess whether macro short should be activated.

    Activation requires:
    1. Layer 1 must be Risk OFF
    2. BTC must be below key structure low

    Args:
        inputs: MacroShortInput with current state.
        config: Optional config dict.

    Returns:
        MacroShortOutput with activation decision and levels.
    """
    if config is None:
        config = load_config()

    l15 = config["layer1_5"]
    activation_cfg = l15["activation"]
    targets_cfg = l15["targets"]

    # Check activation conditions
    layer1_off = inputs.layer1_state == RiskState.OFF
    btc_below_structure = inputs.btc_price < inputs.btc_key_structure_low

    if not layer1_off:
        return MacroShortOutput(
            activated=False,
            entry_price=None,
            tp1=targets_cfg["tp1"],
            tp2=targets_cfg["tp2"],
            tp3=targets_cfg["tp3"],
            stop_loss=0.0,
            details="Layer 1 not in Risk OFF state. Macro short not activated.",
        )

    if not btc_below_structure:
        return MacroShortOutput(
            activated=False,
            entry_price=None,
            tp1=targets_cfg["tp1"],
            tp2=targets_cfg["tp2"],
            tp3=targets_cfg["tp3"],
            stop_loss=0.0,
            details="BTC not below key structure. Macro short not activated.",
        )

    # Activate macro short
    entry_price = inputs.btc_price
    stop_loss = inputs.trigger_event_level * 1.02  # 2% above trigger level

    return MacroShortOutput(
        activated=True,
        entry_price=entry_price,
        tp1=targets_cfg["tp1"],
        tp2=targets_cfg["tp2"],
        tp3=targets_cfg["tp3"],
        stop_loss=stop_loss,
        details=(
            f"MACRO SHORT ACTIVATED. Entry: {entry_price:.0f}, "
            f"TP1: {targets_cfg['tp1']}, TP2: {targets_cfg['tp2']}, "
            f"TP3: {targets_cfg['tp3']}, SL: {stop_loss:.0f}"
        ),
    )


def should_close_normal_ops(macro_short_activated: bool) -> bool:
    """Check if normal trading operations should be closed.

    Macro short does NOT run concurrently with normal ops.

    Args:
        macro_short_activated: Whether macro short is active.

    Returns:
        True if normal ops should be closed.
    """
    return macro_short_activated
