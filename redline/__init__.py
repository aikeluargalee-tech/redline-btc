"""
Redline BTC - 5-Layer Bitcoin Trading Framework

A systematic trading framework with regime-aware position management,
macro risk controls, and multi-timeframe analysis.
"""

__version__ = "0.1.0"
__author__ = "Redline BTC Team"

from . import (
    layer0_regime,
    layer1_macro_risk,
    layer1_5_macro_short,
    layer2_positioning,
    layer3_swing,
    layer4_intraday,
    layer5_engine,
    conflict_resolver,
    sizing,
    checklist,
)

__all__ = [
    "layer0_regime",
    "layer1_macro_risk",
    "layer1_5_macro_short",
    "layer2_positioning",
    "layer3_swing",
    "layer4_intraday",
    "layer5_engine",
    "conflict_resolver",
    "sizing",
    "checklist",
]
