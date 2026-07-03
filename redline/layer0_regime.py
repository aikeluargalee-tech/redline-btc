"""
Layer 0 — Market Regime Classifier

Classifies the market into BULL, BEAR, or TRANSITIONAL regimes based on
on-chain metrics, options data, and ETF flow data.

This is the foundational layer that biases all subsequent layers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"


class Regime(str, Enum):
    """Market regime classification."""
    BULL = "BULL"
    BEAR = "BEAR"
    TRANSITIONAL = "TRANSITIONAL"


@dataclass
class RegimeInputs:
    """Inputs required for regime classification."""
    mvrv_z_score: float
    cycle_composite: float  # 0-100
    options_skew_30d: float
    etf_flows_weekly: float  # Billions USD
    coinbase_premium_trend: float  # Percentage change


@dataclass
class RegimeOutput:
    """Output of regime classification."""
    regime: Regime
    confidence: float  # 0.0 - 1.0
    leverage_multiplier: float
    size_reduction: float
    conviction_threshold: float
    details: str


def classify_regime(inputs: RegimeInputs, config: Optional[dict] = None) -> RegimeOutput:
    """Classify the current market regime based on on-chain and flow data.

    Classification logic:
    - BULL: Cycle composite >= bull_min AND MVRV-Z >= bull_min AND ETF flows positive
    - BEAR: Cycle composite <= bear_max AND MVRV-Z <= bear_max AND ETF flows negative
    - TRANSITIONAL: Everything else

    Args:
        inputs: RegimeInputs dataclass with all required metrics.
        config: Optional config dict. If None, loads from config.yaml.

    Returns:
        RegimeOutput with classification result and derived parameters.
    """
    if config is None:
        config = load_config()

    l0 = config["layer0"]
    bear_cfg = l0["regime"]["bear"]
    bull_cfg = l0["regime"]["bull"]
    lev_cfg = l0["leverage"]

    # Score-based classification
    bull_signals = 0
    bear_signals = 0
    total_signals = 5

    # Signal 1: Cycle Composite
    if inputs.cycle_composite >= bull_cfg["cycle_score_min"]:
        bull_signals += 1
    elif inputs.cycle_composite <= bear_cfg["cycle_score_max"]:
        bear_signals += 1

    # Signal 2: MVRV-Z Score
    if inputs.mvrv_z_score >= bull_cfg["mvrv_z_min"]:
        bull_signals += 1
    elif inputs.mvrv_z_score <= bear_cfg["mvrv_z_max"]:
        bear_signals += 1

    # Signal 3: ETF Flows
    if inputs.etf_flows_weekly >= bull_cfg["etf_flow_weekly_min"]:
        bull_signals += 1
    elif inputs.etf_flows_weekly < bear_cfg["etf_flow_weekly_min"]:
        bear_signals += 1

    # Signal 4: Options Skew (positive = bullish put buying)
    if inputs.options_skew_30d > 5.0:
        bull_signals += 1
    elif inputs.options_skew_30d < -5.0:
        bear_signals += 1

    # Signal 5: Coinbase Premium (positive = US buying)
    if inputs.coinbase_premium_trend > 0.5:
        bull_signals += 1
    elif inputs.coinbase_premium_trend < -0.5:
        bear_signals += 1

    # Classification
    if bull_signals >= 3:
        regime = Regime.BULL
        confidence = bull_signals / total_signals
        leverage_mult = lev_cfg["bull_multiplier"]
        size_reduction = 1.0
        conviction_thresh = 0.5
        details = (
            f"BULL regime: {bull_signals}/{total_signals} bullish signals. "
            f"Cycle={inputs.cycle_composite:.1f}, MVRV-Z={inputs.mvrv_z_score:.2f}, "
            f"ETF={inputs.etf_flows_weekly:+.1f}B"
        )
    elif bear_signals >= 3:
        regime = Regime.BEAR
        confidence = bear_signals / total_signals
        leverage_mult = lev_cfg["bear_multiplier"]
        size_reduction = 1.0
        conviction_thresh = 0.5
        details = (
            f"BEAR regime: {bear_signals}/{total_signals} bearish signals. "
            f"Cycle={inputs.cycle_composite:.1f}, MVRV-Z={inputs.mvrv_z_score:.2f}, "
            f"ETF={inputs.etf_flows_weekly:+.1f}B"
        )
    else:
        regime = Regime.TRANSITIONAL
        confidence = 1.0 - (abs(bull_signals - bear_signals) / total_signals)
        leverage_mult = 1.0
        size_reduction = lev_cfg["transitional_size_reduction"]
        conviction_thresh = lev_cfg["transitional_conviction_threshold"]
        details = (
            f"TRANSITIONAL regime: {bull_signals} bull / {bear_signals} bear signals. "
            f"Reduced size, higher conviction required."
        )

    return RegimeOutput(
        regime=regime,
        confidence=confidence,
        leverage_multiplier=leverage_mult,
        size_reduction=size_reduction,
        conviction_threshold=conviction_thresh,
        details=details,
    )


def get_regime_bias(regime: Regime) -> str:
    """Get the directional bias for a given regime.

    Args:
        regime: The classified regime.

    Returns:
        Directional bias string: 'long', 'short', or 'neutral'.
    """
    if regime == Regime.BULL:
        return "long"
    elif regime == Regime.BEAR:
        return "short"
    else:
        return "neutral"


def intraday_long_allowed(regime: Regime) -> bool:
    """Check if intraday long positions are allowed in the current regime.

    In BEAR regime, intraday longs are restricted to scalps only.

    Args:
        regime: The classified regime.

    Returns:
        True if longs are fully permitted, False if restricted.
    """
    return regime != Regime.BEAR


def max_leverage_for_regime(regime: Regime, config: Optional[dict] = None) -> float:
    """Get the maximum leverage multiplier for the current regime.

    Args:
        regime: The classified regime.
        config: Optional config dict.

    Returns:
        Leverage multiplier (e.g., 1.5 for bull, 0.5 for bear).
    """
    if config is None:
        config = load_config()

    lev_cfg = config["layer0"]["leverage"]

    if regime == Regime.BULL:
        return lev_cfg["bull_multiplier"]
    elif regime == Regime.BEAR:
        return lev_cfg["bear_multiplier"]
    else:
        return 1.0
