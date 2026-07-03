"""Unit tests for Sizing — Position Size Calculator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer0_regime import Regime
from redline.sizing import (
    SizingInput,
    calculate_position_size,
    check_loss_limit,
    load_config,
)


def test_position_size_bear_regime():
    """In bear regime, position size should use reduced leverage."""
    inp = SizingInput(
        layer_name="layer3",
        regime=Regime.BEAR,
        account_balance=100_000,
        entry_price=60_000,
        stop_loss_price=58_000,
    )
    result = calculate_position_size(inp)
    assert result.position_size_usd > 0
    assert result.risk_amount_usd > 0
    assert result.details is not None


def test_position_size_bull_regime():
    """In bull regime, position size should be larger than bear."""
    bear = calculate_position_size(SizingInput(
        layer_name="layer3", regime=Regime.BEAR,
        account_balance=100_000, entry_price=60_000, stop_loss_price=58_000,
    ))
    bull = calculate_position_size(SizingInput(
        layer_name="layer3", regime=Regime.BULL,
        account_balance=100_000, entry_price=60_000, stop_loss_price=58_000,
    ))
    assert bull.position_size_usd >= bear.position_size_usd


def test_edge_case_zero_price_diff():
    """Entry == stop loss should return zero position."""
    inp = SizingInput(
        layer_name="layer4",
        regime=Regime.BEAR,
        account_balance=100_000,
        entry_price=60_000,
        stop_loss_price=60_000,
    )
    result = calculate_position_size(inp)
    assert result.position_size_usd == 0.0


def test_loss_limit_l4():
    """Loss limit > daily_max should block (config: 0.01 = 1%)."""
    can_trade, remaining = check_loss_limit("layer4", -0.05)
    assert can_trade is False
    assert remaining == 0.0


def test_loss_limit_at_boundary():
    """Loss at exact boundary should block if at limit."""
    can_trade, remaining = check_loss_limit("layer4", -0.01)
    assert can_trade is False
    assert remaining == 0.0


def test_loss_limit_exceeded():
    """Large daily loss should block further trading."""
    can_trade, _ = check_loss_limit("layer4", -0.15)
    assert can_trade is False


def test_conflict_multiplier_reduces_size():
    """Conflict multiplier should reduce position size."""
    normal = calculate_position_size(SizingInput(
        layer_name="layer4", regime=Regime.BEAR,
        account_balance=100_000, entry_price=60_000, stop_loss_price=59_500,
    ))
    reduced = calculate_position_size(SizingInput(
        layer_name="layer4", regime=Regime.BEAR,
        account_balance=100_000, entry_price=60_000, stop_loss_price=59_500,
        conflict_size_multiplier=0.5,
    ))
    assert reduced.position_size_usd < normal.position_size_usd
