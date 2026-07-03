"""Unit tests for Layer 3 — Swing Trading."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer3_swing import (
    SwingInputs,
    SwingDirection,
    assess_swing_trade,
)
from redline.layer0_regime import Regime


def make_inputs(**overrides) -> SwingInputs:
    defaults = dict(
        regime=Regime.BEAR,
        btc_price=61708.0,
        structure_4h="bullish",
        structure_1d="bullish",
        daily_sr_level="support",
        adx_value=30.0,
        cvd_trend="positive",
        daily_oversold=True,
        mvrv_z_score=0.15,
        at_major_support=True,
    )
    defaults.update(overrides)
    return SwingInputs(**defaults)


class TestSwingBearRegime:
    def test_long_allowed_when_all_conditions_met(self):
        sw = assess_swing_trade(make_inputs())
        assert sw.direction == SwingDirection.LONG
        assert sw.entry_allowed is True

    def test_short_allowed_bearish_structure(self):
        sw = assess_swing_trade(make_inputs(
            structure_4h="bearish",
            structure_1d="bearish",
            daily_sr_level="resistance",
            cvd_trend="negative",
        ))
        assert sw.direction == SwingDirection.SHORT
        assert sw.entry_allowed is True

    def test_long_blocked_no_major_support(self):
        sw = assess_swing_trade(make_inputs(at_major_support=False))
        assert sw.entry_allowed is False
        assert "Not at major support" in " ".join(sw.reasons)

    def test_long_blocked_cvd_not_positive(self):
        sw = assess_swing_trade(make_inputs(cvd_trend="negative"))
        assert sw.entry_allowed is False
        assert any("CVD" in r for r in sw.reasons)

    def test_long_blocked_mvrv_too_high(self):
        sw = assess_swing_trade(make_inputs(mvrv_z_score=0.5))
        assert sw.entry_allowed is False
        assert any("MVRV-Z" in r for r in sw.reasons)

    def test_long_blocked_not_oversold(self):
        sw = assess_swing_trade(make_inputs(daily_oversold=False))
        assert sw.entry_allowed is False
        assert any("oversold" in r.lower() for r in sw.reasons)

    def test_adx_too_high_blocks_entry(self):
        sw = assess_swing_trade(make_inputs(adx_value=40.0))
        assert sw.entry_allowed is False
        assert any("ADX" in r for r in sw.reasons)

    def test_no_clear_direction(self):
        sw = assess_swing_trade(make_inputs(
            structure_4h="neutral",
            structure_1d="neutral",
        ))
        assert sw.direction == SwingDirection.NONE
        assert sw.entry_allowed is False


class TestSwingTransitionalRegime:
    def test_long_allowed_bullish_structure(self):
        sw = assess_swing_trade(make_inputs(
            regime=Regime.TRANSITIONAL,
        ))
        assert sw.direction == SwingDirection.LONG
        assert sw.entry_allowed is True

    def test_short_allowed_bearish_structure(self):
        sw = assess_swing_trade(make_inputs(
            regime=Regime.TRANSITIONAL,
            structure_4h="bearish",
            structure_1d="bearish",
            daily_sr_level="resistance",
        ))
        assert sw.direction == SwingDirection.SHORT
        assert sw.entry_allowed is True


class TestSwingAllocation:
    def test_allocation_from_config(self):
        sw = assess_swing_trade(make_inputs())
        assert sw.allocation_pct == 0.20  # From config
