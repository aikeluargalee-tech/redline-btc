"""Unit tests for Layer 4 — Intraday Trading."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer4_intraday import (
    IntradayInputs,
    IntradayDirection,
    TradeType,
    assess_intraday_trade,
)
from redline.layer0_regime import Regime


def make_inputs(**overrides) -> IntradayInputs:
    defaults = dict(
        regime=Regime.BEAR,
        direction=IntradayDirection.LONG,
        trade_type=TradeType.TYPE_B,  # Mean reversion (allowed in bear)
        adx_direction=True,
        mtf_alignment=True,
        cvd_invalidation=True,
        price_vs_liq_cluster=True,
        vp_state=True,
        session_context=True,
        layer3_alignment=True,
    )
    defaults.update(overrides)
    return IntradayInputs(**defaults)


class TestIntradayBearRegime:
    def test_type_b_long_allowed(self):
        r = assess_intraday_trade(make_inputs())
        assert r.entry_allowed is True
        assert r.trade_type_allowed is True

    def test_type_c_long_allowed(self):
        r = assess_intraday_trade(make_inputs(trade_type=TradeType.TYPE_C))
        assert r.entry_allowed is True
        assert r.trade_type_allowed is True

    def test_type_a_long_blocked(self):
        r = assess_intraday_trade(make_inputs(trade_type=TradeType.TYPE_A))
        assert r.entry_allowed is False
        assert r.trade_type_allowed is False

    def test_short_all_types_allowed(self):
        for ttype in [TradeType.TYPE_A, TradeType.TYPE_B, TradeType.TYPE_C]:
            r = assess_intraday_trade(make_inputs(
                direction=IntradayDirection.SHORT,
                trade_type=ttype,
            ))
            assert r.trade_type_allowed is True, f"Short {ttype.value} should be allowed"

    def test_checklist_fails_block_entry(self):
        r = assess_intraday_trade(make_inputs(mtf_alignment=False, adx_direction=False))
        assert r.entry_allowed is False
        assert len(r.reasons) > 0

    def test_all_checklist_false(self):
        r = assess_intraday_trade(make_inputs(
            adx_direction=False, mtf_alignment=False, cvd_invalidation=True,
            price_vs_liq_cluster=False, vp_state=False,
            session_context=False, layer3_alignment=False,
        ))
        assert r.entry_allowed is False
        assert sum(r.checklist_results.values()) == 1  # Only CVD

    def test_checklist_passed_count(self):
        r = assess_intraday_trade(make_inputs())
        passed = sum(r.checklist_results.values())
        assert passed == 7  # All 7 pass


class TestIntradayAllocation:
    def test_allocation_from_config(self):
        r = assess_intraday_trade(make_inputs())
        assert r.allocation_pct == 0.10

    def test_direction_none_blocks_entry(self):
        """Regression: direction=NONE (no signal) must never allow an entry."""
        r = assess_intraday_trade(make_inputs(direction=IntradayDirection.NONE))
        assert r.entry_allowed is False
        assert any("NONE" in reason for reason in r.reasons)
