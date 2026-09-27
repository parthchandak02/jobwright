"""Cross-board duplicate detection.

The same posting shows up under different URLs (LinkedIn + Indeed + a repost
with a fresh id). URL keys cannot catch that, so every job gets a normalized
``dedupe_key`` (company | title | place). A newly discovered job whose key
matches an existing job, or a job removed in the last ``window_days``, is
tombstoned as a duplicate before it costs an enrich/score call.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from jobwright.database import tombstone_jobs

log = logging.getLogger(__name__)

_COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co",
    "company", "plc", "lp", "llp", "pbc", "the", "group", "holdings",
}
# Work-arrangement words only; role-distinguishing text (e.g. "(Education)")
# is kept so two different openings at one company never collapse.
_TITLE_NOISE = re.compile(
    r"\b(?:remote|hybrid|on[- ]?site|onsite|full[- ]?time|part[- ]?time|"
    r"contract|temporary|temp|usa|united states)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _squash(text: str) -> str:
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def normalize_company(company: str | None) -> str:
    words = [w for w in _squash(company or "").split() if w not in _COMPANY_SUFFIXES]
    return " ".join(words)


def normalize_title(title: str | None) -> str:
    cleaned = _TITLE_NOISE.sub(" ", title or "")
    return " ".join(_squash(cleaned).split())


def normalize_place(location: str | None) -> str:
    loc = (location or "").lower()
    if not loc.strip() or re.fullmatch(r"\W*remote\W*", loc) or loc.startswith("remote"):
        return "remote"
    first = loc.split(",")[0]
    return " ".join(_squash(first).split())


def dedupe_key(title: str | None, company: str | None, location: str | None) -> str | None:
    """Stable duplicate key, or None when there is not enough signal."""
    c = normalize_company(company)
    t = normalize_title(title)
    if not c or not t:
        return None
    return f"{c}|{t}|{normalize_place(location)}"


def dedupe_new_jobs(conn: sqlite3.Connection, *, window_days: int = 45) -> dict[str, int]:
    """Key every unkeyed job and tombstone duplicates of existing/removed jobs."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT url, title, company, location, source, board_updated_by, discovered_at "
        "FROM jobs WHERE dedupe_key IS NULL ORDER BY discovered_at, rowid"
    ).fetchall()
    if not rows:
        return {"keyed": 0, "duplicates": 0}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    duplicates: list[tuple[str, str]] = []
    keyed = 0
    for row in rows:
        key = dedupe_key(row["title"], row["company"], row["location"])
        if key is None:
            conn.execute("UPDATE jobs SET dedupe_key = '' WHERE url = ?", (row["url"],))
            continue
        protected = (row["source"] or "") == "manual" or (row["board_updated_by"] or "") == "human"
        if not protected:
            original = conn.execute(
                "SELECT url FROM jobs WHERE dedupe_key = ? AND url != ? LIMIT 1",
                (key, row["url"]),
            ).fetchone()
            if original is not None:
                duplicates.append((row["url"], f"duplicate:{original[0]}"))
                continue
            removed = conn.execute(
                "SELECT url, reason FROM job_tombstones WHERE dedupe_key = ? AND removed_at >= ? "
                "AND url != ? LIMIT 1",
                (key, cutoff, row["url"]),
            ).fetchone()
            if removed is not None:
                duplicates.append((row["url"], f"repost_of_removed:{removed[0]}"))
                continue
        conn.execute("UPDATE jobs SET dedupe_key = ? WHERE url = ?", (key, row["url"]))
        keyed += 1
    conn.commit()
    for url, _reason in duplicates:
        row = next(r for r in rows if r["url"] == url)
        conn.execute(
            "UPDATE jobs SET dedupe_key = ? WHERE url = ?",
            (dedupe_key(row["title"], row["company"], row["location"]), url),
        )
    removed_n = tombstone_jobs(conn, duplicates)
    if removed_n:
        log.info("Dedupe: %d duplicate postings removed (%d keyed)", removed_n, keyed)
    return {"keyed": keyed, "duplicates": removed_n}


_TOKEN = re.compile(r"[a-z0-9]+")
_DESC_CHARS = 2000
_MIN_DESC_TOKENS = 30
SIMILAR_DESCRIPTION = 0.9
_STAGE_RANK = {"applied": 2, "in_progress": 2, "offer": 2, "prepare": 1}
PROTECTED_STAGES = ("applied", "in_progress", "offer")


def _desc_tokens(text: str | None) -> frozenset[str]:
    return frozenset(_TOKEN.findall((text or "")[:_DESC_CHARS].lower()))


def description_similarity(a: str | None, b: str | None) -> float:
    """Token Jaccard on the first 2000 chars; 0 when either side is too short to judge."""
    ta, tb = _desc_tokens(a), _desc_tokens(b)
    if len(ta) < _MIN_DESC_TOKENS or len(tb) < _MIN_DESC_TOKENS:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def backfill_dedupe_keys(conn: sqlite3.Connection) -> int:
    """Store dedupe_key on rows that lack one (never removes anything)."""
    rows = conn.execute(
        "SELECT url, title, company, location FROM jobs WHERE dedupe_key IS NULL"
    ).fetchall()
    if rows:
        conn.executemany(
            "UPDATE jobs SET dedupe_key = ? WHERE url = ?",
            [(dedupe_key(r[1], r[2], r[3]) or "", r[0]) for r in rows],
        )
        conn.commit()
    return len(rows)


def _keeper_rank(job: dict) -> tuple:
    return (
        _STAGE_RANK.get(job.get("funnel_stage") or "backlog", 0),
        bool(job.get("has_label")) or job.get("user_fit_score") is not None,
        bool(job.get("tailored_resume_path") or job.get("cover_letter_path")),
        job.get("fit_score") if job.get("fit_score") is not None else -1,
        job.get("discovered_at") or "",
        job.get("url") or "",
    )


def _merge_similar(clusters: list[list[dict]]) -> list[list[dict]]:
    merged = True
    while merged and len(clusters) > 1:
        merged = False
        for i in range(len(clusters)):
            for k in range(i + 1, len(clusters)):
                if any(
                    description_similarity(a["desc_head"], b["desc_head"]) >= SIMILAR_DESCRIPTION
                    for a in clusters[i]
                    for b in clusters[k]
                ):
                    clusters[i] = clusters[i] + clusters.pop(k)
                    merged = True
                    break
            if merged:
                break
    return clusters


def find_duplicate_groups(conn: sqlite3.Connection) -> list[dict]:
    """Group open jobs that are the same posting.

    Primary: identical ``dedupe_key``. Secondary: same company + title with a
    different place but a near-identical description (one multi-location
    posting). Returns ``[{"keeper", "losers", "match"}]``; the keeper is chosen
    by funnel stage, human label/score, materials, fit score, then recency.
    """
    conn.row_factory = sqlite3.Row
    backfill_dedupe_keys(conn)
    rows = conn.execute(
        "SELECT j.url, j.job_id, j.title, j.company, j.location, j.dedupe_key, j.funnel_stage, "
        "j.source, j.fit_score, j.user_fit_score, j.tailored_resume_path, j.cover_letter_path, "
        "j.discovered_at, substr(COALESCE(j.full_description, j.description), 1, ?) AS desc_head, "
        "EXISTS (SELECT 1 FROM score_labels l WHERE l.job_url = j.url) AS has_label "
        "FROM jobs j WHERE COALESCE(j.funnel_stage, 'backlog') != 'closed' "
        "AND COALESCE(j.dedupe_key, '') != ''",
        (_DESC_CHARS,),
    ).fetchall()

    by_identity: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        job = dict(row)
        ident = job["dedupe_key"].rsplit("|", 1)[0]
        by_identity.setdefault(ident, {}).setdefault(job["dedupe_key"], []).append(job)

    groups: list[dict] = []
    for buckets in by_identity.values():
        for jobs in _merge_similar(list(buckets.values())):
            if len(jobs) < 2:
                continue
            ordered = sorted(jobs, key=_keeper_rank, reverse=True)
            match = "key" if len({j["dedupe_key"] for j in jobs}) == 1 else "description"
            groups.append({"keeper": ordered[0], "losers": ordered[1:], "match": match})
    groups.sort(key=lambda g: (g["keeper"].get("company") or "", g["keeper"].get("title") or ""))
    return groups


def _loser_blocked(job: dict) -> str | None:
    stage = job.get("funnel_stage") or "backlog"
    if stage in PROTECTED_STAGES:
        return stage
    if (job.get("source") or "") == "manual":
        return "manual"
    return None


def collapse_duplicates(conn: sqlite3.Connection, *, apply: bool = False) -> dict:
    """Close duplicate open jobs, keeping the best card of each group.

    Losers move to Closed (outcome ``duplicate``, ``duplicate_of`` = keeper
    job_id) and their URLs are tombstoned so discovery never brings them back.
    Rows and labels are kept. Losers already applied to (or added by hand) are
    reported in ``blocked`` and never closed.
    """
    from jobwright.database import advance_funnel, job_id_for_url

    groups = find_duplicate_groups(conn)
    closed = 0
    blocked: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for group in groups:
        keeper = group["keeper"]
        keeper_id = keeper.get("job_id") or job_id_for_url(keeper["url"])
        note = f"Duplicate of job {keeper_id}"
        for loser in group["losers"]:
            loser["blocked"] = _loser_blocked(loser)
            if loser["blocked"]:
                blocked.append({"url": loser["url"], "why": loser["blocked"], "keeper": keeper["url"]})
                continue
            if not apply:
                continue
            advance_funnel(
                loser["url"], "closed", "system", note=f"duplicate_of:{keeper_id}",
                outcome="duplicate", conn=conn,
            )
            conn.execute(
                "UPDATE jobs SET close_reason = 'duplicate', duplicate_of = ?, "
                "notes = CASE WHEN COALESCE(notes, '') = '' THEN ? ELSE notes || char(10) || ? END "
                "WHERE url = ?",
                (keeper_id, note, note, loser["url"]),
            )
            conn.execute(
                "INSERT OR IGNORE INTO job_tombstones "
                "(url, title, company, location, site, fit_score, dedupe_key, reason, removed_at) "
                "SELECT url, title, company, location, site, fit_score, dedupe_key, ?, ? "
                "FROM jobs WHERE url = ?",
                (f"duplicate:{keeper['url']}", now, loser["url"]),
            )
            closed += 1
    if apply:
        conn.commit()
    if closed:
        log.info("Dedupe: closed %d duplicate open jobs", closed)
    return {
        "groups": groups,
        "group_count": len(groups),
        "duplicates": sum(len(g["losers"]) for g in groups),
        "closed": closed,
        "blocked": blocked,
        "applied": apply,
    }
