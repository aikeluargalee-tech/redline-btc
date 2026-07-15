#!/usr/bin/env python3
"""Update Redline BTC dashboard data and regenerate report JSON.

Runs the full daily pipeline and saves output to docs/redline_report.json.
Safe to run on cron — logs to stdout.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
os.chdir(str(root))  # Ensure CWD is project root for config.yaml resolution

from scripts.daily_run import run_daily_analysis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("update_dashboard")

STATE_FILE = root / ".redline_state.json"


def _send_tg_alert(message: str):
    """Send Telegram alert via GetClaw bridge."""
    try:
        subprocess.run(
            [sys.executable, str(root.parent / "getclaw-bridge" / "getclaw_send.py"), message],
            capture_output=True, timeout=30
        )
    except Exception as e:
        logger.warning("TG alert failed: %s", e)


def _load_prev_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    report = run_daily_analysis(mock=False)

    out_path = root / "docs" / "redline_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    summary = report.get("summary", {})
    errors = len(report.get("errors", []))
    logger.info("Dashboard updated: %s | Regime=%s Risk=%s Swing=%s Intraday=%s Errors=%d",
                out_path,
                summary.get("regime", "?"),
                summary.get("risk_state", "?"),
                summary.get("swing_direction", "?"),
                summary.get("intraday_direction", "?"),
                errors)

    # --- Push-on-change: L1 state → Telegram alert ---
    mr = report.get("macro_risk", {})
    current_state = mr.get("state", "RISK_ON")
    prev = _load_prev_state()
    prev_state = prev.get("l1_state", current_state)

    if current_state != prev_state:
        detail = mr.get("triggered_by", [])
        triggers = ", ".join(detail[:5]) if detail else "none"
        alert = (
            f"⚡ REDLINE ALERT — L1 State Change\n"
            f"{prev_state} → {current_state}\n"
            f"Triggers: {triggers}\n"
            f"Regime: {summary.get('regime', '?')}\n"
            f"Details: {mr.get('details', 'N/A')}"
        )
        _send_tg_alert(alert)
        logger.info("L1 state changed: %s → %s (alert sent)", prev_state, current_state)

    # Also alert on enriched risk level changes
    er = report.get("enriched_risk", {})
    prev_er = prev.get("enriched_risk_level", "normal")
    curr_er = er.get("risk_level", "normal")
    if prev_er != "critical" and curr_er == "critical":
        _send_tg_alert(
            f"⚠ REDLINE ALERT — Enriched Risk CRITICAL\n"
            f"Crash: {er.get('crash_score', '?')} BlackSwan: {er.get('black_swan_score', '?')}\n"
            f"Liquidity: {er.get('liquidity_verdict', '?')} DXY: {er.get('dxy', '?')}"
        )
        logger.info("Enriched risk CRITICAL (alert sent)")

    # Save current state for next comparison
    _save_state({"l1_state": current_state, "enriched_risk_level": curr_er})

    # --- Push to GitHub ---
    result = subprocess.run(
        ["git", "-C", str(root), "add", "docs/redline_report.json",
         "&&", "git", "-C", str(root), "commit", "-m", "auto: update dashboard report",
         "&&", "git", "-C", str(root), "push", "origin", "main"],
        capture_output=True, text=True, timeout=30, shell=True
    )
    if result.returncode == 0:
        logger.info("Pushed to GitHub Pages")
    else:
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            logger.info("No changes to push")
        else:
            logger.warning("Push stderr: %s", result.stderr[:200])


if __name__ == "__main__":
    main()
