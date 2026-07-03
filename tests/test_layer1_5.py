"""Unit tests for Layer 1.5 — Macro Short Activation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer1_5_macro_short import (
    MacroShortInput,
    assess_macro_short,
    should_close_normal_ops,
)
from redline.layer1_macro_risk import RiskState


def test_macro_short_activates_on_bear_trigger():
    """Macro short activates when Layer 1 is OFF and BTC below structure."""
    inputs = MacroShortInput(
        layer1_state=RiskState.OFF,
        btc_price=58000.0,
        btc_key_structure_low=60000.0,
        trigger_event_level=62000.0,
    )
    result = assess_macro_short(inputs)
    assert result.activated is True
    assert result.entry_price == 58000.0
    assert result.stop_loss == 62000.0 * 1.02  # 2% above trigger level
    assert result.tp1 == 58872
    assert result.tp2 == 55000
    assert result.tp3 == 48000


def test_macro_short_no_activation_when_risk_on():
    """Macro short does NOT activate when Layer 1 is ON."""
    inputs = MacroShortInput(
        layer1_state=RiskState.ON,
        btc_price=58000.0,
        btc_key_structure_low=60000.0,
        trigger_event_level=62000.0,
    )
    result = assess_macro_short(inputs)
    assert result.activated is False
    assert result.entry_price is None
    assert "Layer 1 not in Risk OFF" in result.details


def test_macro_short_stop_loss_calculation():
    """Stop loss is calculated as 2% above trigger event level."""
    inputs = MacroShortInput(
        layer1_state=RiskState.OFF,
        btc_price=55000.0,
        btc_key_structure_low=57000.0,
        trigger_event_level=58000.0,
    )
    result = assess_macro_short(inputs)
    assert result.activated is True
    expected_sl = 58000.0 * 1.02
    assert result.stop_loss == expected_sl
    assert result.stop_loss > inputs.trigger_event_level


def test_should_close_normal_ops():
    """Normal ops should close when macro short is activated."""
    assert should_close_normal_ops(True) is True
    assert should_close_normal_ops(False) is False