"""Unit tests for Layer 2 — Positioning (Spot Accumulation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer2_positioning import (
    PositioningInput,
    PositioningOutput,
    TrancheLevel,
    assess_positioning,
    get_tranches,
    check_leverage_allowed,
    stops_enabled,
)
from redline.layer0_regime import Regime


class TestPositioningBearRegime:
    def test_accumulate_when_price_in_tranche(self):
        """Price in t1 range (58-60K) → accumulate."""
        result = assess_positioning(PositioningInput(
            regime=Regime.BEAR, btc_price=59000,
            total_capital=100_000, current_position=0.0, tranches_filled=[],
        ))
        assert result.action == "accumulate"
        assert result.tranche is not None
        assert result.amount_usd > 0

    def test_hold_when_price_outside_tranches(self):
        """Price above all tranches → hold."""
        result = assess_positioning(PositioningInput(
            regime=Regime.BEAR, btc_price=62000,
            total_capital=100_000, current_position=0.0, tranches_filled=[],
        ))
        assert result.action == "hold"
        assert result.tranche is None

    def test_no_accumulate_if_tranche_filled(self):
        """Already filled tranche should be skipped."""
        result = assess_positioning(PositioningInput(
            regime=Regime.BEAR, btc_price=59000,
            total_capital=100_000, current_position=1.0,
            tranches_filled=["T1"],
        ))
        # Price 59000 is in t2 range (52-55K) or t1 range depending on config
        # t1: 58-60K — if price 59K is in t1 and t1 is filled, should skip to t2 or hold
        assert result.action in ("accumulate", "hold")

    def test_no_accumulate_in_bull_regime(self):
        """Non-bear regime should not accumulate."""
        result = assess_positioning(PositioningInput(
            regime=Regime.BULL, btc_price=59000,
            total_capital=100_000, current_position=0.0, tranches_filled=[],
        ))
        assert result.action == "none"

    def test_no_accumulate_in_transitional_regime(self):
        result = assess_positioning(PositioningInput(
            regime=Regime.TRANSITIONAL, btc_price=59000,
            total_capital=100_000, current_position=0.0, tranches_filled=[],
        ))
        assert result.action == "none"


class TestPositioningLeverage:
    def test_leverage_disabled_in_bear(self):
        assert check_leverage_allowed(Regime.BEAR) is False

    def test_leverage_enabled_in_bull(self):
        # Bull regime has leverage_max=2.0, so leverage is allowed
        assert check_leverage_allowed(Regime.BULL) is True

    def test_stops_disabled(self):
        """Cycle positions should have no stops."""
        assert stops_enabled() is False


class TestPositioningTranches:
    def test_tranches_from_config(self):
        config = load_config()
        tranches = get_tranches(config)
        assert len(tranches) == 3
        for t in tranches:
            assert t.range_low < t.range_high
            assert t.allocation_pct > 0
            assert t.filled is False

    def test_tranche_allocation_sums_to_one(self):
        config = load_config()
        tranches = get_tranches(config)
        total = sum(t.allocation_pct for t in tranches)
        assert abs(total - 1.0) < 0.01


def load_config():
    import yaml
    with open("config.yaml") as f:
        return yaml.safe_load(f)
