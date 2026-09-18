#!/usr/bin/env python3
"""Weekly stale-posting recheck: revisit live backlog URLs, close the dead ones.

For every backlog job that already has a detail scrape, re-fetch the page with a
lightweight Playwright check. Permanent failures (HTTP 404/410/451 or
"no longer accepting applications" text) soft-close the job via the canonical
advance_funnel path (actor=system, outcome=cancelled, note carries the reason).

Human-held cards and non-backlog stages are never touched.

Usage:
    python3 scripts/stale_check.py --dry-run     # count + list only, no writes
    python3 scripts/stale_check.py --limit 25    # cap how many URLs to check
    python3 scripts/stale_check.py               # full pass (backlog older than 14d)

Scheduling (Hermes cron or launchd): run weekly, after the morning brief.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stale_check")


def _candidate_rows(conn, max_age_days: int):
    """Backlog jobs, already enriched, older than max_age_days, not human-held."""
    from jobwright.database import ANTI_CLOBBER_SQL

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    return conn.execute(
        "SELECT url, title, site, discovered_at FROM jobs "
        "WHERE COALESCE(funnel_stage, 'backlog') = 'backlog' "
        f"AND (board_updated_by IS NULL OR board_updated_by != 'human') "
        f"AND detail_scraped_at IS NOT NULL AND discovered_at < '{cutoff}' "
        f"{ANTI_CLOBBER_SQL} ORDER BY discovered_at ASC"
    ).fetchall()


def _live_check(page, url: str) -> str | None:
    """Return a permanent-failure reason, or None if the page looks alive."""
    from jobwright.enrichment.detail import _is_permanent_failure

    try:
        resp = page.goto(url, timeout=30000)
        if resp and resp.status in (404, 410, 451):
            return f"HTTP {resp.status}"
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception as exc:  # noqa: BLE001
        # Timeouts/transport errors are NOT evidence of death: skip, retry next week.
        if "timeout" in str(exc).lower():
            return None
        return None
    body = ""
    try:
        body = (page.content() or "").lower()
    except Exception:  # noqa: BLE001  page mid-navigation: treat as alive this pass
        return None
    markers = ("no longer accepting applications", "this job no longer exists")
    for m in markers:
        if m in body:
            return m
    # _is_permanent_failure covers HTTP text errors surfaced via detail pages
    if _is_permanent_failure(body[:500]):
        return body[:200]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="list findings, write nothing")
    parser.add_argument("--limit", type=int, default=0, help="max URLs to check this run")
    parser.add_argument(
        "--max-age-days", type=int, default=14,
        help="only recheck backlog jobs discovered more than N days ago (default 14)",
    )
    args = parser.parse_args()

    from jobwright import config

    config.set_app_dir(config.PACKAGE_DIR.parents[1] / "users" / "richa")
    from jobwright.database import advance_funnel, get_connection

    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    rows = _candidate_rows(conn, args.max_age_days)
    if args.limit:
        rows = rows[: args.limit]
    log.info("Rechecking %d backlog URLs (max_age=%dd)", len(rows), args.max_age_days)

    from playwright.sync_api import sync_playwright

    dead: list[tuple[str, str, str]] = []
    checked = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for i, row in enumerate(rows, 1):
            url, title = row["url"], row["title"]
            reason = _live_check(page, url)
            checked += 1
            if reason:
                dead.append((url, (title or "")[:70], reason))
                log.info("[%d/%d] DEAD %s | %s", i, len(rows), reason, title[:60])
                if not args.dry_run:
                    advance_funnel(
                        url, "closed", actor="system",
                        note=f"weekly recheck: posting dead ({reason})",
                        outcome="cancelled", conn=conn,
                    )
            else:
                log.info("[%d/%d] alive | %s", i, len(rows), title[:60])
            if i < len(rows):
                time.sleep(2.0)
        browser.close()

    conn.commit()
    summary = {
        "checked": checked,
        "dead": len(dead),
        "closed": 0 if args.dry_run else len(dead),
        "dry_run": args.dry_run,
        "when": datetime.now(timezone.utc).isoformat(),
    }
    log.info("SUMMARY %s", summary)
    if dead:
        for url, title, reason in dead[:20]:
            print(f"DEAD {reason} | {title} | {url[:80]}")
    conn.close()


if __name__ == "__main__":
    main()
