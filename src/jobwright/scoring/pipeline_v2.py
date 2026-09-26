"""Scoring stage v2: select jobs, optional Jev fast-reject, tiered matcher, persist.

Results are written in small batches as they arrive (a crash keeps what was
scored), every score is appended to score_history, and token usage is flushed
to llm_usage at the end.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from jobwright.config import load_profile, load_search_config
from jobwright.database import get_connection, get_jobs_by_stage
from jobwright.labels import build_eval_set
from jobwright.llm import flush_usage
from jobwright.scoring.criteria import load_criteria
from jobwright.scoring.examples import ExampleIndex
from jobwright.scoring.matcher import BillingDead, MatchContext, MatchResult, score_jobs

log = logging.getLogger(__name__)

BATCH_SAVE = 20
K_EXAMPLES = 12
MIN_POSITIVE_EXAMPLES = 4


def _workers() -> int:
    try:
        return max(1, int(os.environ.get("JOBWRIGHT_SCORE_WORKERS", "16")))
    except ValueError:
        return 16


def build_context(conn, profile: dict | None, search_cfg: dict | None, resume_text: str) -> MatchContext:
    labeled = build_eval_set(conn)
    return MatchContext(
        resume_text=resume_text,
        criteria=load_criteria(profile),
        index=ExampleIndex(labeled) if labeled else None,
        search_cfg=search_cfg,
        k_examples=K_EXAMPLES,
        min_positive_examples=MIN_POSITIVE_EXAMPLES,
        # Harmless for new jobs; required when rescoring already-labeled ones.
        leave_one_out=True,
    )


class _Saver:
    def __init__(self, conn, *, version: str, run_kind: str, run_id: str) -> None:
        self.conn = conn
        self.version = version
        self.run_kind = run_kind
        self.run_id = run_id
        self.pending: list[MatchResult] = []
        self.lock = threading.Lock()
        self.saved = 0

    def add(self, result: MatchResult) -> None:
        with self.lock:
            self.pending.append(result)
            if len(self.pending) >= BATCH_SAVE:
                self._flush_locked()

    def flush(self) -> None:
        with self.lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self.pending:
            return
        # on_result runs in the calling thread (score_jobs collects futures there),
        # so the stage's own connection is safe to use.
        conn = self.conn
        now = datetime.now(timezone.utc).isoformat()
        rows = self.pending
        self.pending = []
        conn.executemany(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ?, score_confidence = ?, "
            "score_gates = ?, score_tier = ?, score_model = ? WHERE url = ?",
            [(r.score, r.reasoning_text(), now, r.confidence, r.gates_json(), r.tier, r.model, r.url) for r in rows],
        )
        conn.executemany(
            "INSERT INTO score_history (job_url, score, confidence, gates, reasoning, model, prompt_version, tier, "
            "run_kind, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(r.url, r.score, r.confidence, r.gates_json(), r.reasoning_text(), r.model, self.version, r.tier,
              self.run_kind, self.run_id, now) for r in rows],
        )
        conn.commit()
        self.saved += len(rows)


def _jev_prefilter(jobs: list[dict], profile: dict | None, conn, saver: _Saver) -> list[dict]:
    """Jev reject-only tier: drop confident low scores before any LLM call."""
    from jobwright.scoring import fastpath

    mode = fastpath.get_jev_hybrid(profile)
    if mode not in ("shadow", "on", "reject") or not jobs:
        return jobs
    effective = "reject" if mode in ("on", "reject") else "shadow"
    verdicts = {r["url"]: r for r in fastpath.score_fastpath(jobs, {**(profile or {}), "jev_hybrid": effective}, conn)}
    if effective == "shadow":
        return jobs
    keep: list[dict] = []
    for job in jobs:
        v = verdicts.get(job["url"]) or {}
        if v.get("jev_route") == "fast_reject":
            score = max(1, min(4, int(v.get("jev_score") or 1)))
            saver.add(MatchResult(
                url=job["url"], score=score, fit=score, confidence=float(v.get("jev_confidence") or 0.0),
                dealbreakers=[], location_ok=None, seniority="match",
                reasoning=f"Jev fast-reject (score {v.get('jev_score')}, confidence {v.get('jev_confidence')})",
                model="jev-latest", tier="t0",
            ))
        else:
            keep.append(job)
    log.info("Jev reject-only: %d fast-rejected, %d to LLM", len(jobs) - len(keep), len(keep))
    return keep


def score_job_list(
    jobs: list[dict],
    *,
    conn=None,
    profile: dict | None = None,
    search_cfg: dict | None = None,
    resume_text: str | None = None,
    run_kind: str = "pipeline",
    use_jev: bool = True,
) -> dict:
    from jobwright.resume import load_resume_text

    conn = conn or get_connection()
    if profile is None:
        try:
            profile = load_profile()
        except FileNotFoundError:
            profile = None
    if search_cfg is None:
        try:
            search_cfg = load_search_config()
        except Exception:  # noqa: BLE001
            search_cfg = {}
    resume_text = resume_text if resume_text is not None else load_resume_text()
    ctx = build_context(conn, profile, search_cfg, resume_text)
    run_id = os.environ.get("JOBWRIGHT_WEB_RUN_ID") or f"{run_kind}-{uuid.uuid4().hex[:8]}"
    saver = _Saver(conn, version=ctx.version, run_kind=run_kind, run_id=run_id)
    t0 = time.time()
    todo = _jev_prefilter(jobs, profile, conn, saver) if use_jev else jobs
    log.info("Scoring %d jobs (v2 %s, workers=%d)", len(todo), ctx.version, _workers())
    billing_error = None
    errors = 0
    try:
        _results, errors = score_jobs(ctx, todo, workers=_workers(), on_result=saver.add)
    except BillingDead as exc:
        billing_error = str(exc)
    finally:
        saver.flush()
        try:
            flush_usage(conn, run_id)
        except Exception as exc:  # noqa: BLE001 - accounting must not sink a run
            log.warning("Usage flush failed: %s", exc)
    elapsed = time.time() - t0
    if billing_error and saver.saved == 0:
        raise RuntimeError(
            f"Scoring aborted: LLM provider billing/auth refused ({billing_error}). "
            "Fix the provider key or credits; no scores were written."
        )
    dist = conn.execute(
        "SELECT fit_score, COUNT(*) FROM jobs WHERE fit_score IS NOT NULL GROUP BY fit_score ORDER BY fit_score DESC"
    ).fetchall()
    return {
        "scored": saver.saved,
        "errors": errors,
        "elapsed": elapsed,
        "distribution": [(r[0], r[1]) for r in dist],
        "prompt_version": ctx.version,
        "criteria_derived": ctx.criteria.derived,
        "run_id": run_id,
    }


def run_scoring_v2(limit: int = 0, rescore: bool = False) -> dict:
    conn = get_connection()
    if rescore:
        query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
        rows = conn.execute(query + (" LIMIT ?" if limit > 0 else ""), (limit,) if limit > 0 else ()).fetchall()
        jobs = [dict(r) for r in rows]
    else:
        jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)
    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}
    return score_job_list(jobs, conn=conn, run_kind="rescore" if rescore else "pipeline")
