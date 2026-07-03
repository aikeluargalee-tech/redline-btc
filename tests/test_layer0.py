"""Unit tests for Layer 0 — Market Regime Classifier."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer0_regime import (
    Regime,
    RegimeInputs,
    classify_regime,
    get_regime_bias,
    intraday_long_allowed,
    max_leverage_for_regime,
)


def test_bull_regime():
    """Cycle >= 50, MVRV-Z >= 1.0, ETF positive → BULL."""
    inputs = RegimeInputs(
        mvrv_z_score=1.5,
        cycle_composite=65.0,
        options_skew_30d=10.0,
        etf_flows_weekly=2.0,
        coinbase_premium_trend=1.0,
    )
    result = classify_regime(inputs)
    assert result.regime == Regime.BULL
    assert result.confidence >= 0.6


def test_bear_regime():
    """Cycle <= 35, MVRV-Z <= 0.5, ETF negative → BEAR."""
    inputs = RegimeInputs(
        mvrv_z_score=0.25,
        cycle_composite=25.0,
        options_skew_30d=-10.0,
        etf_flows_weekly=-1.0,
        coinbase_premium_trend=-1.0,
    )
    result = classify_regime(inputs)
    assert result.regime == Regime.BEAR
    assert result.confidence >= 0.6
    assert result.leverage_multiplier < 1.0


def test_transitional_regime():
    """Mixed signals → TRANSITIONAL."""
    inputs = RegimeInputs(
        mvrv_z_score=0.8,
        cycle_composite=45.0,
        options_skew_30d=2.0,
        etf_flows_weekly=0.0,
        coinbase_premium_trend=0.2,
    )
    result = classify_regime(inputs)
    assert result.regime == Regime.TRANSITIONAL
    assert result.size_reduction < 1.0


def test_bull_bias_long():
    """BULL regime → bias is 'long'."""
    assert get_regime_bias(Regime.BULL) == "long"


def test_bear_bias_short():
    """BEAR regime → bias is 'short'."""
    assert get_regime_bias(Regime.BEAR) == "short"


def test_bear_restricts_long():
    """BEAR regime should restrict intraday longs."""
    assert intraday_long_allowed(Regime.BEAR) is False


def test_bull_allows_long():
    """BULL regime allows intraday longs."""
    assert intraday_long_allowed(Regime.BULL) is True


def test_bear_leverage_cap():
    """BEAR regime should cap leverage (multiplier < 1.0)."""
    mult = max_leverage_for_regime(Regime.BEAR)
    assert mult < 1.0
