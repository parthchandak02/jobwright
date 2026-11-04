"""Order daily-list candidates by how much they look like jobs the person applied to.

Every candidate has already cleared the person's cutoff; this only decides
which of them make the top ``brief_top_n``. Applying is the strongest signal a
person gives (much stronger than a thumbs up), so the jobs most similar to past
applications go first, and the order keeps adapting as they apply to more.

Pure-Python TF-IDF over title (weighted x3) + company + the start of the
description, the same document shape the scorer's example index uses. With
fewer than ``MIN_APPLIED`` applications there is not enough signal, so the
original (score, confidence, recency) order is kept unchanged.
"""

from __future__ import annotations

import math
import os
import sqlite3
from collections import Counter

from jobwright.scoring.examples import _tokens

MIN_APPLIED = 5
TOP_K = 3  # a candidate's similarity = mean of its 3 closest applications

_APPLIED_SQL = (
    "SELECT url, title, company, full_description FROM jobs "
    "WHERE applied_at IS NOT NULL OR funnel_stage IN ('applied', 'in_progress', 'offer') "
    "OR url IN (SELECT DISTINCT job_url FROM stage_history "
    "           WHERE to_stage IN ('applied', 'in_progress', 'offer'))"
)


def enabled() -> bool:
    return os.environ.get("JOBWRIGHT_RANK_LIKE_APPLIED", "1").strip().lower() not in ("0", "false", "no", "off")


def _doc(title: str | None, company: str | None, description: str | None) -> Counter[str]:
    return Counter(_tokens(title or "") * 3 + _tokens(company or "") + _tokens((description or "")[:1500]))


class _Index:
    def __init__(self, docs: list[Counter[str]]) -> None:
        df: Counter[str] = Counter()
        for d in docs:
            df.update(d.keys())
        n = max(1, len(docs))
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self._vecs = [self._weigh(d) for d in docs]

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def similarity(self, doc: Counter[str]) -> float:
        q = self._weigh(doc)
        sims = sorted((sum(w * vec.get(t, 0.0) for t, w in q.items()) for vec in self._vecs), reverse=True)
        top = sims[:TOP_K]
        return sum(top) / len(top) if top else 0.0


def rank_like_applied(conn: sqlite3.Connection, jobs: list[dict], min_applied: int = MIN_APPLIED) -> list[dict]:
    """Return ``jobs`` reordered so the ones most like past applications come first.

    Stable: ties keep the incoming order. Each returned job gets a
    ``like_applied`` similarity (0..1) when ranking was applied. Jobs are only
    reordered, never dropped.
    """
    if len(jobs) < 2 or not enabled():
        return jobs
    applied = conn.execute(_APPLIED_SQL).fetchall()
    if len(applied) < min_applied:
        return jobs
    applied_urls = {row[0] for row in applied}
    index = _Index([_doc(row[1], row[2], row[3]) for row in applied])

    urls = [j.get("url") for j in jobs]
    marks = ",".join("?" for _ in urls)
    descriptions = {
        row[0]: row[1]
        for row in conn.execute(f"SELECT url, full_description FROM jobs WHERE url IN ({marks})", urls).fetchall()
    }
    ranked: list[tuple[float, int, dict]] = []
    for pos, job in enumerate(jobs):
        if job.get("url") in applied_urls:
            sim = 0.0  # never happens for unnotified backlog jobs; keep it neutral
        else:
            sim = index.similarity(_doc(job.get("title"), job.get("company"), descriptions.get(job.get("url"))))
        ranked.append((sim, pos, {**job, "like_applied": round(sim, 3)}))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return [job for _, _, job in ranked]
