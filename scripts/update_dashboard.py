#!/usr/bin/env python3
"""Update Redline BTC dashboard data and regenerate report JSON.

Runs the full daily pipeline and saves output to docs/redline_report.json.
Safe to run on cron — logs to stdout.
"""

import json
import logging
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from scripts.daily_run import run_daily_analysis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("update_dashboard")


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

    # Push to GitHub so GH Pages serves the latest
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(root), "add", "docs/redline_report.json",
         "&&", "git", "-C", str(root), "commit", "-m", "auto: update dashboard report",
         "&&", "git", "-C", str(root), "push", "origin", "main"],
        capture_output=True, text=True, timeout=30, shell=True
    )
    if result.returncode == 0:
        logger.info("Pushed to GitHub Pages")
    else:
        # Non-fatal: maybe nothing to commit
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            logger.info("No changes to push")
        else:
            logger.warning("Push stderr: %s", result.stderr[:200])


if __name__ == "__main__":
    main()
