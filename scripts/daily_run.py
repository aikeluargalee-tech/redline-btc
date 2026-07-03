"""Daily Run Script — Full Redline Pipeline

Orchestrates the complete daily analysis:
  L0: Regime classification (on-chain)
  L1: Macro risk switch
  L1.5: Macro short activation (emergency)
  L2: Positioning / spot accumulation
  L3: Swing trade signals (2-10 day)
  L4: Intraday trade signals (hours)
  L5: Market structure engine + conflict resolver + sizing

Usage:
    python scripts/daily_run.py --mock   # Mock data
    python scripts/daily_run.py          # Live data
    python scripts/daily_run.py -o report.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redline.layer0_regime import RegimeInputs, classify_regime, Regime
from redline.layer1_macro_risk import MacroTriggers, assess_macro_risk, RiskState
from redline.layer1_5_macro_short import MacroShortInput, assess_macro_short
from redline.layer2_positioning import PositioningInput, assess_positioning
from redline.layer3_swing import SwingInputs, assess_swing_trade, SwingDirection
from redline.layer4_intraday import (
    IntradayInputs, IntradayDirection, TradeType, assess_intraday_trade,
)
from redline.layer5_engine import analyze_enriched, check_enriched_risk_signals
from redline.conflict_resolver import ConflictInput, resolve_conflicts
from redline.sizing import SizingInput, calculate_position_size, check_loss_limit
from redline.checklist import pre_session_checklist

from scripts.packet_source import fetch_enriched
from scripts.fetch_layer0 import fetch_mock_data as fetch_l0_mock, fetch_live_data as fetch_l0_live
from scripts.fetch_layer1 import fetch_mock_data as fetch_l1_mock, fetch_live_data as fetch_l1_live
from scripts.fetch_data_packet import fetch_mock_data as fetch_dp_mock, fetch_live_data as fetch_dp_live
from scripts.fetch_swing_signals import fetch_swing_signals, fetch_mock_data as fetch_l3_mock
from scripts.fetch_intraday_signals import fetch_intraday_signals, fetch_mock_data as fetch_l4_mock

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_daily_analysis(mock: bool = False) -> dict:
    """Run the full daily Redline analysis across all layers."""
    report: dict = {
        "timestamp": datetime.utcnow().isoformat(),
        "regime": None,
        "macro_risk": None,
        "macro_short": None,
        "positioning": None,
        "swing": None,
        "intraday": None,
        "market_structure": None,
        "conflict_resolution": None,
        "sizing": {},
        "overall_status": "Unknown",
        "errors": [],
    }

    # ----- Fetch data -----
    try:
        if mock:
            l0_data = fetch_l0_mock()
            l1_data = fetch_l1_mock()
            dp_data = fetch_dp_mock()
            l3_data = fetch_l3_mock()
            l4_data = fetch_l4_mock()
        else:
            l0_data = fetch_l0_live()
            l1_data = fetch_l1_live()
            dp_data = fetch_dp_live()
            l3_data = fetch_swing_signals()
            l4_data = fetch_intraday_signals()
    except Exception as e:
        report["errors"].append(f"Data fetch failed: {e}")
        logger.error("Data fetch failed: %s", e)
        return report

    # ----- Layer 0 — Regime -----
    try:
        l0_fields = {"mvrv_z_score", "cycle_composite", "options_skew_30d",
                     "etf_flows_weekly", "coinbase_premium_trend"}
        regime_input = RegimeInputs(**{k: v for k, v in l0_data.items() if k in l0_fields})
        regime_output = classify_regime(regime_input)
        regime_val = regime_output.regime.value
        report["regime"] = {
            "regime": regime_val,
            "confidence": regime_output.confidence,
            "leverage_multiplier": regime_output.leverage_multiplier,
            "size_reduction": regime_output.size_reduction,
            "details": regime_output.details,
        }
        logger.info("Layer 0: %s (%.0f%%)", regime_val, regime_output.confidence * 100)
    except Exception as e:
        report["errors"].append(f"Layer 0: {e}")
        logger.error("Layer 0 failed: %s", e)
        regime_val = "TRANSITIONAL"

    # ----- Layer 1 — Macro Risk -----
    try:
        l1_fields = {"mstr_close", "vix_current", "us10y_current", "usdjpy_change_pct",
                     "boj_verbal_response", "mstr_sessions_below", "vix_sessions_above",
                     "usdjpy_stable_hours", "btc_above_structure_low"}
        trigger_input = MacroTriggers(**{k: v for k, v in l1_data.items() if k in l1_fields})
        risk_state = assess_macro_risk(trigger_input)
        risk_state_val = risk_state.state.value
        report["macro_risk"] = {
            "state": risk_state_val,
            "triggered_by": risk_state.triggered_by,
            "can_reactivate": risk_state.can_reactivate,
            "details": risk_state.details,
        }
        logger.info("Layer 1: %s", risk_state_val)
    except Exception as e:
        report["errors"].append(f"Layer 1: {e}")
        logger.error("Layer 1 failed: %s", e)
        risk_state_val = "RISK_ON"

    # ----- Layer 1.5 — Macro Short -----
    if risk_state_val == "RISK_OFF":
        try:
            ms_input = MacroShortInput(
                layer1_state=RiskState.OFF,
                btc_price=dp_data.get("btc_price", l1_data.get("btc_price", 62000)),
                btc_key_structure_low=dp_data.get("btc_key_structure_low", 58000),
                trigger_event_level=dp_data.get("trigger_event_level", 75000),
            )
            ms_out = assess_macro_short(ms_input)
            report["macro_short"] = {
                "activated": ms_out.activated,
                "entry_price": ms_out.entry_price,
                "tp1": ms_out.tp1,
                "tp2": ms_out.tp2,
                "tp3": ms_out.tp3,
                "stop_loss": ms_out.stop_loss,
                "details": ms_out.details,
            }
            logger.info("Layer 1.5: %s", "ACTIVATED" if ms_out.activated else "inactive")
        except Exception as e:
            report["errors"].append(f"Layer 1.5: {e}")
            logger.error("Layer 1.5 failed: %s", e)
    else:
        report["macro_short"] = {"status": "inactive — Layer 1 is Risk ON"}

    # ----- Layer 2 — Positioning (spot accumulation) -----
    btc_price = 62000.0  # fallback
    try:
        btc_price = dp_data.get("btc_price", l3_data.get("btc_price", 62000))
        pos_input = PositioningInput(
            regime=Regime(regime_val),
            btc_price=btc_price,
            total_capital=100_000,
            current_position=0.0,
            tranches_filled=[],
        )
        pos_out = assess_positioning(pos_input)
        report["positioning"] = {
            "action": pos_out.action,
            "tranche": pos_out.tranche.name if pos_out.tranche else None,
            "amount_usd": pos_out.amount_usd,
            "btc_amount": pos_out.btc_amount,
            "details": pos_out.details,
            "total_allocation_pct": pos_out.total_allocation_pct,
        }
        logger.info("Layer 2: %s", pos_out.action)
    except Exception as e:
        report["errors"].append(f"Layer 2: {e}")
        logger.error("Layer 2 failed: %s", e)

    # ----- Layer 3 — Swing Trade Signals -----
    swing_out = None
    try:
        swing_input = SwingInputs(
            regime=Regime(regime_val),
            btc_price=l3_data.get("btc_price", btc_price),
            structure_4h=l3_data["structure_4h"],
            structure_1d=l3_data["structure_1d"],
            daily_sr_level=l3_data["daily_sr_level"],
            adx_value=l3_data["adx_value"],
            cvd_trend=l3_data["cvd_trend"],
            daily_oversold=l3_data["daily_oversold"],
            mvrv_z_score=l3_data["mvrv_z_score"],
            at_major_support=l3_data["at_major_support"],
        )
        swing_out = assess_swing_trade(swing_input)
        report["swing"] = {
            "direction": swing_out.direction.value,
            "entry_allowed": swing_out.entry_allowed,
            "reasons": swing_out.reasons,
            "details": swing_out.details,
            "allocation_pct": swing_out.allocation_pct,
        }
        logger.info("Layer 3: %s %s",
                     swing_out.direction.value,
                     "ALLOWED" if swing_out.entry_allowed else "BLOCKED")
    except Exception as e:
        report["errors"].append(f"Layer 3: {e}")
        logger.error("Layer 3 failed: %s", e)

    # ----- Layer 4 — Intraday Trade Signals -----
    l4_out = None
    direction_enum = IntradayDirection.NONE
    trade_type_enum = TradeType.TYPE_C
    try:
        l4_data_with_l3 = fetch_intraday_signals(l3_output=report.get("swing"))
        direction_enum = {
            "LONG": IntradayDirection.LONG,
            "SHORT": IntradayDirection.SHORT,
            "NONE": IntradayDirection.NONE,
        }.get(l4_data_with_l3["direction"], IntradayDirection.NONE)

        trade_type_enum = {
            "type_a": TradeType.TYPE_A,
            "type_b": TradeType.TYPE_B,
            "type_c": TradeType.TYPE_C,
        }.get(l4_data_with_l3["trade_type"], TradeType.TYPE_C)

        l4_input = IntradayInputs(
            regime=Regime(regime_val),
            direction=direction_enum,
            trade_type=trade_type_enum,
            adx_direction=l4_data_with_l3["adx_direction"],
            mtf_alignment=l4_data_with_l3["mtf_alignment"],
            cvd_invalidation=l4_data_with_l3["cvd_invalidation"],
            price_vs_liq_cluster=l4_data_with_l3["price_vs_liq_cluster"],
            vp_state=l4_data_with_l3["vp_state"],
            session_context=l4_data_with_l3["session_context"],
            layer3_alignment=l4_data_with_l3["layer3_alignment"],
        )
        l4_out = assess_intraday_trade(l4_input)
        report["intraday"] = {
            "direction": l4_data_with_l3["direction"],
            "trade_type": l4_data_with_l3["trade_type"],
            "entry_allowed": l4_out.entry_allowed,
            "checklist_results": l4_out.checklist_results,
            "trade_type_allowed": l4_out.trade_type_allowed,
            "reasons": l4_out.reasons,
            "details": l4_out.details,
            "allocation_pct": l4_out.allocation_pct,
        }
        logger.info("Layer 4: %s %s (checklist %d/%s)",
                     l4_data_with_l3["direction"],
                     "ALLOWED" if l4_out.entry_allowed else "BLOCKED",
                     sum(l4_out.checklist_results.values()),
                     len(l4_out.checklist_results))
    except Exception as e:
        report["errors"].append(f"Layer 4: {e}")
        logger.error("Layer 4 failed: %s", e)

    # ----- Layer 5 — Enriched Market Structure -----
    try:
        enriched = fetch_enriched()
        if enriched:
            analysis = analyze_enriched(enriched)
            enriched_risk = check_enriched_risk_signals(enriched)
            report["market_structure"] = analysis
            report["enriched_risk"] = enriched_risk
            logger.info("Layer 5: momentum=%s, leverage=%s, vol=%s, sent=%s",
                         analysis["momentum"], analysis["leverage"],
                         analysis["volatility_regime"], analysis["sentiment"])
        else:
            report["market_structure"] = {"status": "No enriched data available"}
    except Exception as e:
        report["errors"].append(f"Layer 5: {e}")
        logger.error("Layer 5 failed: %s", e)

    # ----- Conflict Resolution -----
    try:
        l2_dir = report.get("positioning", {}).get("action", "neutral")
        l3_dir = SwingDirection.NONE
        if swing_out:
            l3_dir = swing_out.direction if hasattr(swing_out, "direction") else SwingDirection.NONE

        l4_dir = IntradayDirection.NONE
        l4_type = TradeType.TYPE_C
        if l4_out:
            l4_dir = direction_enum if direction_enum else IntradayDirection.NONE
            l4_type = trade_type_enum if trade_type_enum else TradeType.TYPE_C

        conflict_input = ConflictInput(
            layer0_regime=Regime(regime_val),
            layer2_direction=l2_dir,
            layer3_direction=l3_dir,
            layer4_direction=l4_dir,
            layer4_trade_type=l4_type,
            layer4_pnl_pct=0.0,  # No current position
            layer3_meets_swing_criteria=bool(swing_out and swing_out.entry_allowed),
        )
        conflict_out = resolve_conflicts(conflict_input)
        report["conflict_resolution"] = {
            "action": conflict_out.action.value,
            "size_multiplier": conflict_out.size_multiplier,
            "allowed_trade_type": conflict_out.allowed_trade_type.value,
            "reasons": conflict_out.reasons,
            "details": conflict_out.details,
        }
        logger.info("Conflict resolution: %s (multiplier=%.1f)",
                     conflict_out.action.value, conflict_out.size_multiplier)
    except Exception as e:
        report["errors"].append(f"Conflict resolution: {e}")
        logger.error("Conflict resolution failed: %s", e)
        conflict_out = None

    # ----- Sizing -----
    try:
        layers_to_size = {
            "layer3": report.get("swing", {}).get("entry_allowed", False),
            "layer4": report.get("intraday", {}).get("entry_allowed", False),
        }
        size_mult = conflict_out.size_multiplier if conflict_out else 1.0
        for layer_name, active in layers_to_size.items():
            if not active:
                report["sizing"][layer_name] = {"status": "No entry signal"}
                continue

            sizing_input = SizingInput(
                layer_name=layer_name,
                regime=Regime(regime_val),
                account_balance=100_000,
                entry_price=btc_price,
                stop_loss_price=btc_price * 0.97,  # 3% stop placeholder
                conflict_size_multiplier=size_mult,
            )
            size_out = calculate_position_size(sizing_input)
            report["sizing"][layer_name] = {
                "position_size_usd": size_out.position_size_usd,
                "position_size_btc": size_out.position_size_btc,
                "risk_amount_usd": size_out.risk_amount_usd,
                "risk_pct": size_out.risk_pct,
                "leverage": size_out.leverage,
                "details": size_out.details,
            }
        logger.info("Sizing complete")
    except Exception as e:
        report["errors"].append(f"Sizing: {e}")
        logger.error("Sizing failed: %s", e)

    # ----- Overall Status -----
    err_count = len(report["errors"])
    if err_count > 0:
        report["overall_status"] = "DEGRADED" if err_count <= 2 else "FAILED"
    else:
        report["overall_status"] = "OPERATIONAL"

    report["summary"] = {
        "regime": regime_val,
        "risk_state": risk_state_val,
        "swing_direction": report.get("swing", {}).get("direction", "N/A"),
        "swing_allowed": report.get("swing", {}).get("entry_allowed", False),
        "intraday_direction": report.get("intraday", {}).get("direction", "N/A"),
        "intraday_allowed": report.get("intraday", {}).get("entry_allowed", False),
        "conflict_action": report.get("conflict_resolution", {}).get("action", "N/A"),
        "errors": err_count,
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Redline BTC — Full Daily Analysis")
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
