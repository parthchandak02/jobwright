"""Prune noise jobs from the user's DB using searches.yaml filters."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from jobwright.config import load_location_filters, load_search_config
from jobwright.discovery.filters import (
    apply_fit_score_guards,
    has_impact_track,
    passes_discovery_filters,
    title_excluded,
)
from jobwright.discovery.location import location_ok as _location_ok

log = logging.getLogger(__name__)

# Never delete cards the human moved, or anything past agent handoff.
_PROTECTED_STAGES = frozenset({"prepare", "applied", "in_progress", "offer", "closed"})


def _row_is_protected(row: sqlite3.Row) -> bool:
    if (row["board_updated_by"] or "") == "human":
        return True
    try:
        stage = row["funnel_stage"]
    except (KeyError, IndexError):
        stage = None
    return (stage or "backlog") in _PROTECTED_STAGES

# Sites that produced junk for US Bay Area profiles (smart-extract Canada, etc.)
DEFAULT_BLOCK_SITES = frozenset({
    "job bank canada",
    "randstad canada",
    "careerjet canada",
    "eluta",
    "simplyhired",
    "powertofly",
    "dice",
    # Workday smart-extract Canada employers (not Bay Area targets)
    "rbc",
    "td bank",
    "bmo",
    "manulife",
    "magna international",
    "cibc",
    "telus health",
    "intact financial",
})

# Railroad / unrelated Dice false positives
NOISE_TITLE_FRAGMENTS = (
    "conductor",
    "brakeman",
    "go team conductor",
    "bayway terminal",
)


def _title_is_obvious_noise(title: str) -> bool:
    t = title.lower()
    return (
        any(x in t for x in NOISE_TITLE_FRAGMENTS)
        and "chief of staff" not in t
        and "operations" not in t.split("conductor")[0][-20:]
        and ("engineer" in t or "brakeman" in t or "terminal" in t)
    )


def _block_sites(search_cfg: dict[str, Any]) -> set[str]:
    sites = set(DEFAULT_BLOCK_SITES)
    for s in search_cfg.get("block_sites") or []:
        sites.add(str(s).lower().strip())
    return sites


def job_is_noise(row: sqlite3.Row, search_cfg: dict[str, Any]) -> tuple[bool, str]:
    """Return (is_noise, reason) for a jobs table row."""
    title = row["title"] or ""
    location = row["location"] or ""
    salary = row["salary"] or ""
    description = (row["description"] or "") + " " + (row["full_description"] or "")
    site = (row["site"] or "").lower().strip()
    url = (row["url"] or "").lower()

    blocked = _block_sites(search_cfg)
    if site in blocked:
        return True, f"blocked site: {row['site']}"

    company_l = (row["company"] or "").lower()
    for exc in search_cfg.get("exclude_companies") or []:
        token = str(exc).lower().strip()
        if token and token in company_l:
            return True, f"excluded company: {row['company']}"

    if _title_is_obvious_noise(title):
        return True, f"noise title: {title[:60]}"

    for fragment in (".gc.ca", "randstad.ca", "careerjet.ca", "jobbank.gc.ca"):
        if fragment in url:
            return True, f"blocked url: {fragment}"

    accept, reject = load_location_filters(search_cfg)
    if location and not _location_ok(location, accept, reject):
        return True, f"location: {location[:60]}"

    if not passes_discovery_filters(
        title=title,
        salary=salary or None,
        description=description or None,
        search_cfg=search_cfg,
    ):
        if title_excluded(title, search_cfg.get("exclude_titles") or []):
            return True, f"excluded title: {title[:60]}"
        return True, "salary/title filter"

    # CSR false positives (customer service, not corporate social responsibility)
    t = title.lower()
    if "csr" in t and any(
        x in t
        for x in (
            "receptionist", "veterinary", "vet ", "customer service",
            "client service", "drug & alcohol", "temporary, remote",
            "operations (temporary",
        )
    ):
        return True, f"csr false positive: {title[:60]}"

    return False, ""


def prune_noise_jobs(
    conn: sqlite3.Connection,
    search_cfg: dict[str, Any] | None = None,
    *,
    dry_run: bool = True,
    reset: bool = False,
) -> dict[str, int]:
    """Delete jobs that fail location/title/site noise checks. Returns stats."""
    if search_cfg is None:
        search_cfg = load_search_config()

    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs").fetchall()

    if reset:
        deleted = len(rows)
        if not dry_run and deleted:
            conn.execute("DELETE FROM jobs")
            conn.commit()
            try:
                conn.execute("VACUUM")
            except sqlite3.OperationalError:
                pass
        return {
            "total": len(rows),
            "deleted": deleted,
            "kept": 0,
            "reasons": {"reset": deleted},
            "dry_run": dry_run,
            "reset": True,
        }

    to_delete: list[tuple[str, str]] = []
    reasons: dict[str, int] = {}

    for row in rows:
        if _row_is_protected(row):
            continue
        is_noise, reason = job_is_noise(row, search_cfg)
        if is_noise:
            to_delete.append((row["url"], reason))
            key = reason.split(":")[0] if ":" in reason else reason
            reasons[key] = reasons.get(key, 0) + 1

    if not dry_run and to_delete:
        conn.executemany("DELETE FROM jobs WHERE url = ?", [(u,) for u, _ in to_delete])
        conn.commit()
        try:
            conn.execute("VACUUM")
        except sqlite3.OperationalError:
            pass  # vacuum may fail if DB busy

    kept = len(rows) - len(to_delete)
    log.info(
        "Prune %s: %d deleted, %d kept (of %d)",
        "dry-run" if dry_run else "applied",
        len(to_delete),
        kept,
        len(rows),
    )
    return {
        "total": len(rows),
        "deleted": len(to_delete),
        "kept": kept,
        "reasons": reasons,
        "dry_run": dry_run,
    }


def reapply_fit_score_guards(
    conn: sqlite3.Connection,
    search_cfg: dict[str, Any] | None = None,
) -> int:
    """Lower stored fit_score when current guards would cap the LLM value."""
    if search_cfg is None:
        search_cfg = load_search_config()
    conn.row_factory = sqlite3.Row
    updated = 0
    for row in conn.execute(
        "SELECT url, title, company, site, full_description, description, fit_score "
        "FROM jobs WHERE fit_score IS NOT NULL"
    ):
        parsed = apply_fit_score_guards(
            {
                "title": row["title"],
                "company": row["company"] or row["site"],
                "full_description": row["full_description"] or row["description"],
            },
            {"score": int(row["fit_score"]), "reasoning": ""},
            search_cfg=search_cfg,
        )
        new_score = int(parsed["score"])
        if new_score < int(row["fit_score"]):
            conn.execute(
                "UPDATE jobs SET fit_score = ? WHERE url = ?",
                (new_score, row["url"]),
            )
            updated += 1
    if updated:
        conn.commit()
    return updated


def prune_after_score(
    conn: sqlite3.Connection | None = None,
    search_cfg: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    drop_at_or_below: int = 3,
) -> dict[str, int]:
    """After scoring: recap fit scores, then drop backlog junk.

    Keeps human-held and prepare+ cards. Deletes backlog that is noise, not on
    the impact track, or scored at or below drop_at_or_below.
    """
    from jobwright.database import get_connection

    owns = conn is None
    if owns:
        conn = get_connection()
    if search_cfg is None:
        search_cfg = load_search_config()

    capped = reapply_fit_score_guards(conn, search_cfg)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    to_delete: list[tuple[str, str]] = []
    reasons: dict[str, int] = {}

    for row in rows:
        if _row_is_protected(row):
            continue
        url = row["url"]
        is_noise, reason = job_is_noise(row, search_cfg)
        if is_noise:
            to_delete.append((url, reason))
        else:
            score = row["fit_score"]
            if score is None:
                continue
            score_i = int(score)
            on_track = has_impact_track(
                row["title"],
                row["company"] or row["site"],
                (row["full_description"] or "") or (row["description"] or ""),
            )
            if not on_track:
                to_delete.append((url, "off-track"))
            elif score_i <= drop_at_or_below:
                to_delete.append((url, f"low score:{score_i}"))
            else:
                continue
        key = to_delete[-1][1].split(":")[0]
        reasons[key] = reasons.get(key, 0) + 1

    if not dry_run and to_delete:
        conn.executemany("DELETE FROM jobs WHERE url = ?", [(u,) for u, _ in to_delete])
        conn.commit()

    stats = {
        "capped": capped,
        "deleted": len(to_delete),
        "kept": len(rows) - len(to_delete),
        "total": len(rows),
        "reasons": reasons,
        "dry_run": dry_run,
    }
    log.info(
        "Prune after score %s: capped %d, deleted %d, kept %d",
        "dry-run" if dry_run else "applied",
        capped,
        stats["deleted"],
        stats["kept"],
    )
    return stats
