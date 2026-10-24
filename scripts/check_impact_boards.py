#!/usr/bin/env python3
"""Health check for the curated impact job boards (discovery/impactboards.py).

Runs every board scraper for the active user, prints a per-board report and a
non-zero exit code when any board errors. Safe to run repeatedly: stored jobs
dedupe on URL and tombstoned URLs are skipped, so a healthy second run reports
0 new.

Usage:
    JOBWRIGHT_USER=<profile-id> .venv/bin/python scripts/check_impact_boards.py
"""

import json
import logging
import os
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


def main() -> int:
    from jobwright.discovery.impactboards import run_impact_boards

    report = run_impact_boards(workers=int(os.environ.get("IMPACT_BOARDS_WORKERS", "4")))
    print(json.dumps(report, indent=1))
    if isinstance(report, dict) and report.get("skipped"):
        print("impact boards disabled via IMPACT_BOARDS=0")
        return 0
    failed = [n for n, r in report.items() if isinstance(r, dict) and r.get("error")]
    total_new = report.get("_total_new", 0) if isinstance(report, dict) else 0
    print(f"\nboards={len(report) - 1} new={total_new} failed={len(failed)}")
    for n in failed:
        print(f"  FAIL {n}: {report[n]['error']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
