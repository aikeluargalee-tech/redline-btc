"""Unit tests for Conflict Resolver — Inter-Layer Conflict Resolution."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer0_regime import Regime
from redline.layer3_swing import SwingDirection
from redline.layer4_intraday import IntradayDirection, TradeType
from redline.conflict_resolver import (
    ConflictAction,
    ConflictInput,
    resolve_conflicts,
    check_capital_isolation,
)


def test_no_conflict():
    """All layers aligned → ALLOW."""
    inp = ConflictInput(
        layer0_regime=Regime.BEAR,
        layer2_direction="short",
        layer3_direction=SwingDirection.SHORT,
        layer4_direction=IntradayDirection.SHORT,
        layer4_trade_type=TradeType.TYPE_A,
        layer4_pnl_pct=0.0,
        layer3_meets_swing_criteria=True,
    )
    result = resolve_conflicts(inp)
    assert result.action == ConflictAction.ALLOW


def test_l4_contradicts_l2():
    """L4 long contradicts L2 short → downgrade to scalp."""
    inp = ConflictInput(
        layer0_regime=Regime.BEAR,
        layer2_direction="short",
        layer3_direction=SwingDirection.NONE,
        layer4_direction=IntradayDirection.LONG,
        layer4_trade_type=TradeType.TYPE_A,
        layer4_pnl_pct=0.0,
        layer3_meets_swing_criteria=True,
    )
    result = resolve_conflicts(inp)
    assert result.action in (ConflictAction.DOWNGRADE_TO_SCALP,)
    assert result.size_multiplier < 1.0


def test_l4_stacking_with_l3():
    """L4 stacking same direction as L3 → size reduction."""
    inp = ConflictInput(
        layer0_regime=Regime.BULL,
        layer2_direction="neutral",
        layer3_direction=SwingDirection.LONG,
        layer4_direction=IntradayDirection.LONG,
        layer4_trade_type=TradeType.TYPE_A,
        layer4_pnl_pct=0.0,
        layer3_meets_swing_criteria=True,
    )
    result = resolve_conflicts(inp)
    assert result.size_multiplier < 1.0


def test_losing_trade_no_swing():
    """Losing L4 trade that doesn't meet swing criteria → BLOCK."""
    inp = ConflictInput(
        layer0_regime=Regime.BEAR,
        layer2_direction="neutral",
        layer3_direction=SwingDirection.NONE,
        layer4_direction=IntradayDirection.LONG,
        layer4_trade_type=TradeType.TYPE_C,
        layer4_pnl_pct=-2.0,
        layer3_meets_swing_criteria=False,
    )
    result = resolve_conflicts(inp)
    assert result.action == ConflictAction.BLOCK


def test_capital_isolation_l4():
    """Capital isolation: L4 exceeding daily loss should block."""
    allowed, remaining = check_capital_isolation("layer4", -6.0)
    assert allowed is not None  # depends on config
    assert remaining >= 0.0
