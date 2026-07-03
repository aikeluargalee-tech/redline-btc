"""
Daily Run Script

Orchestrates the full daily analysis across all layers:
1. Fetch all data (Layer 0, 1, data packet)
2. Run regime classification (Layer 0)
3. Check macro risk (Layer 1)
4. Check macro short activation (Layer 1.5)
5. Assess positioning (Layer 2)
6. Generate analysis report

Usage:
    python scripts/daily_run.py --mock  # Use mock data
    python scripts/daily_run.py         # Use live data
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer0_regime import RegimeInputs, classify_regime
from redline.layer1_macro_risk import MacroTriggers, assess_macro_risk, RiskState
from redline.layer1_5_macro_short import MacroShortInput, assess_macro_short
from redline.layer2_positioning import PositioningInput, assess_positioning
from redline.checklist import pre_session_checklist
from scripts.fetch_layer0 import fetch_mock_data as fetch_l0_mock, fetch_live_data as fetch_l0_live
from scripts.fetch_layer1 import fetch_mock_data as fetch_l1_mock, fetch_live_data as fetch_l1_live
from scripts.fetch_data_packet import fetch_mock_data as fetch_dp_mock, fetch_live_data as fetch_dp_live

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_daily_analysis(mock: bool = False) -> dict:
    """Run the full daily Redline analysis across all layers."""
    report: dict[str, object] = {
        "timestamp": datetime.utcnow().isoformat(),
        "regime": None,
        "macro_risk": None,
        "macro_short": None,
        "positioning": None,
        "errors": [],
    }

    # Fetch data
    if mock:
        l0_data = fetch_l0_mock()
        l1_data = fetch_l1_mock()
        dp_data = fetch_dp_mock()
    else:
        l0_data = fetch_l0_live()
        l1_data = fetch_l1_live()
        dp_data = fetch_dp_live()

    # Layer 0 — Regime (only pass expected fields)
    try:
        l0_fields = {"mvrv_z_score", "cycle_composite", "options_skew_30d",
                     "etf_flows_weekly", "coinbase_premium_trend"}
        regime_input = RegimeInputs(**{k: v for k, v in l0_data.items() if k in l0_fields})
        regime_output = classify_regime(regime_input)
        report["regime"] = {
            "regime": regime_output.regime.value,
            "confidence": regime_output.confidence,
            "leverage_multiplier": regime_output.leverage_multiplier,
            "size_reduction": regime_output.size_reduction,
            "details": regime_output.details,
        }
        logger.info("Layer 0: %s", report["regime"]["regime"])
    except Exception as e:
        report["errors"].append(f"Layer 0: {e}")
        logger.error("Layer 0 failed: %s", e)

    # Layer 1 — Macro Risk (filter to expected fields)
    try:
        l1_fields = {"mstr_close", "vix_current", "us10y_current", "usdjpy_change_pct",
                     "boj_verbal_response", "mstr_sessions_below", "vix_sessions_above",
                     "usdjpy_stable_hours", "btc_above_structure_low"}
        trigger_input = MacroTriggers(**{k: v for k, v in l1_data.items() if k in l1_fields})
        risk_state = assess_macro_risk(trigger_input)
        report["macro_risk"] = {
            "state": risk_state.state.value,
            "triggered_by": risk_state.triggered_by,
            "can_reactivate": risk_state.can_reactivate,
            "details": risk_state.details,
        }
        logger.info("Layer 1: %s", risk_state.state.value)
    except Exception as e:
        report["errors"].append(f"Layer 1: {e}")
        logger.error("Layer 1 failed: %s", e)

    # Layer 1.5 — Macro Short (only if Risk OFF)
    if report["macro_risk"] and report["macro_risk"]["state"] == "RISK_OFF":
        try:
            ms_input = MacroShortInput(
                btc_price=dp_data.get("btc_price", l1_data.get("btc_price", 62000)),
                layer1_triggered=True,
            )
            report["macro_short"] = assess_macro_short(ms_input)
            logger.info("Layer 1.5: assessment complete")
        except Exception as e:
            report["errors"].append(f"Layer 1.5: {e}")
            logger.error("Layer 1.5 failed: %s", e)
    else:
        report["macro_short"] = {"status": "inactive — Layer 1 is Risk ON"}

    # Layer 2 — Positioning
    try:
        regime_val = report.get("regime", {}).get("regime", "TRANSITIONAL")
        from redline.layer0_regime import Regime
        pos_input = PositioningInput(
            regime=Regime(regime_val),
            btc_price=dp_data.get("btc_price", l1_data.get("btc_price", 62000)),
            total_capital=100_000,
            current_position=0.0,
            tranches_filled=[],
        )
        report["positioning"] = assess_positioning(pos_input)
        logger.info("Layer 2: assessment complete")
    except Exception as e:
        report["errors"].append(f"Layer 2: {e}")
        logger.error("Layer 2 failed: %s", e)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Redline BTC — Daily Analysis")
    parser.add_argument("--mock", action="store_true", help="Use mock data")
    parser.add_argument("--output", "-o", type=str, help="Save report to file")
    args = parser.parse_args()

    report = run_daily_analysis(mock=args.mock)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"Report saved to {args.output}")
    else:
        print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
