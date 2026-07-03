"""Unit tests for Layer 1 — Macro Risk Switch."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer1_macro_risk import (
    MacroTriggers,
    RiskState,
    check_risk_off_triggers,
    check_risk_on_criteria,
    assess_macro_risk,
)


def make_triggers(**overrides) -> MacroTriggers:
    """Helper to create MacroTriggers with sensible defaults (no triggers firing)."""
    defaults = dict(
        mstr_close=100.0,
        vix_current=15.0,
        us10y_current=4.4,
        usdjpy_change_pct=0.5,
        boj_verbal_response=False,
        mstr_sessions_below=0,
        vix_sessions_above=0,
        usdjpy_stable_hours=72,
        btc_above_structure_low=True,
    )
    defaults.update(overrides)
    return MacroTriggers(**defaults)


def test_no_triggers_firing():
    """All triggers below threshold → no risk off signal."""
    triggers = make_triggers()
    should_off, reasons = check_risk_off_triggers(triggers)
    assert should_off is False
    assert len(reasons) == 0


def test_mstr_trigger():
    """MSTR close < 75 fires trigger 1."""
    triggers = make_triggers(mstr_close=70.0)
    should_off, reasons = check_risk_off_triggers(triggers)
    assert should_off is True
    assert any("MSTR" in r for r in reasons)


def test_vix_trigger():
    """VIX > 25 fires trigger 2."""
    triggers = make_triggers(vix_current=30.0)
    should_off, reasons = check_risk_off_triggers(triggers)
    assert should_off is True
    assert any("VIX" in r for r in reasons)


def test_us10y_trigger():
    """US10Y > 4.60% fires trigger 3."""
    triggers = make_triggers(us10y_current=4.7)
    should_off, reasons = check_risk_off_triggers(triggers)
    assert should_off is True
    assert any("US10Y" in r for r in reasons)


def test_usdjpy_trigger_requires_boj():
    """USD/JPY spike alone is not enough — needs BoJ response."""
    triggers = make_triggers(usdjpy_change_pct=3.0, boj_verbal_response=False)
    should_off, _ = check_risk_off_triggers(triggers)
    assert should_off is False


def test_usdjpy_with_boj():
    """USD/JPY spike + BoJ response fires trigger 4."""
    triggers = make_triggers(usdjpy_change_pct=3.0, boj_verbal_response=True)
    should_off, reasons = check_risk_off_triggers(triggers)
    assert should_off is True
    assert any("USD/JPY" in r for r in reasons)


def test_any_one_trigger_fires():
    """Any single trigger is enough to go Risk OFF."""
    triggers = make_triggers(mstr_close=70.0)  # Only MSTR fires
    result = assess_macro_risk(triggers)
    assert result.state == RiskState.OFF
    assert len(result.triggered_by) >= 1
