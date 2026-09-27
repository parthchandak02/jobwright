"""Offline scoring evaluation against the human-labeled eval set.

Replays the scorer over labeled jobs (leave-one-out retrieval, so a job never
sees its own label) and reports precision / recall / F0.5 at the notify
threshold, plus the stored production scores as a baseline. Every eval score
is appended to score_history (run_kind='eval') and a JSON report is written to
logs/eval_<timestamp>.json.
"""

from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jobwright.config as config
from jobwright.labels import EvalItem, build_eval_set
from jobwright.llm import usage_snapshot
from jobwright.scoring.criteria import load_criteria
from jobwright.scoring.examples import ExampleIndex
from jobwright.scoring.matcher import Borderline, MatchContext, MatchResult, apply_gates, score_jobs


def metrics(pairs: list[tuple[int | None, int]], threshold: int) -> dict[str, Any]:
    """pairs = (predicted score or None, true label)."""
    tp = sum(1 for s, y in pairs if s is not None and s >= threshold and y == 1)
    fp = sum(1 for s, y in pairs if s is not None and s >= threshold and y == 0)
    fn = sum(1 for s, y in pairs if (s is None or s < threshold) and y == 1)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    beta2 = 0.25
    f05 = (1 + beta2) * precision * recall / (beta2 * precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold, "predicted_pos": tp + fp, "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3), "recall": round(recall, 3), "f05": round(f05, 3),
    }


SWEEP_THRESHOLDS = tuple(range(3, 10))
MIN_EXPLICIT_PRECISION = 0.85
MIN_SURFACED = 3


def threshold_sweep(rows: list[dict[str, Any]], thresholds: tuple[int, ...] = SWEEP_THRESHOLDS) -> list[dict[str, Any]]:
    """P / R / F0.5 per threshold, on all labels and on explicit labels only."""
    explicit = [(r["score"], r["label"]) for r in rows if r.get("source") != "closed_unapplied"]
    every = [(r["score"], r["label"]) for r in rows]
    return [{"threshold": t, "all": metrics(every, t), "explicit": metrics(explicit, t)} for t in thresholds]


def recommend_threshold(
    sweep: list[dict[str, Any]], *, min_precision: float = MIN_EXPLICIT_PRECISION, min_surfaced: int = MIN_SURFACED,
) -> dict[str, Any] | None:
    """Lowest threshold (max recall) whose explicit-label precision meets the bar.

    Falls back to the best explicit F0.5 (``meets_bar`` False) when none does.
    """
    if not sweep:
        return None
    ok = [s for s in sweep if s["explicit"]["precision"] >= min_precision and s["explicit"]["tp"] >= min_surfaced]
    if ok:
        best = max(ok, key=lambda s: (s["explicit"]["recall"], s["threshold"]))
        meets = True
    else:
        best = max(sweep, key=lambda s: (s["explicit"]["f05"], s["threshold"]))
        meets = False
    return {
        "threshold": best["threshold"], "meets_bar": meets, "min_precision": min_precision,
        "precision": best["explicit"]["precision"], "recall": best["explicit"]["recall"],
        "precision_all": best["all"]["precision"], "recall_all": best["all"]["recall"],
    }


def _item_job(item: EvalItem) -> dict[str, Any]:
    return {
        "url": item.url, "title": item.title, "company": item.company, "location": item.location,
        "salary": item.salary, "full_description": item.description, "dedupe_key": item.dedupe_key,
    }


def prior_from_report(path: Path, jobs: list[dict[str, Any]], ctx: MatchContext) -> dict[str, MatchResult]:
    """First-pass results from a stored eval report, re-gated with the current rules.

    Only rows that carry the raw judgment (fit, location_ok, seniority) are reused.
    """
    rows = {r["url"]: r for r in json.loads(Path(path).read_text(encoding="utf-8")).get("items") or []}
    out: dict[str, MatchResult] = {}
    for job in jobs:
        r = rows.get(job["url"])
        if not r or r.get("fit") is None or "seniority" not in r or r.get("tier") not in ("t1", None):
            continue
        raw = {"fit": r["fit"], "dealbreakers": r.get("dealbreakers") or [], "location_ok": r.get("location_ok"),
               "seniority": r.get("seniority") or "match"}
        score, deals, caps = apply_gates(raw, job, ctx)
        out[job["url"]] = MatchResult(
            url=job["url"], score=score, fit=int(r["fit"]), confidence=float(r.get("confidence") or 0.0),
            dealbreakers=deals, location_ok=r.get("location_ok"), seniority=raw["seniority"],
            reasoning=r.get("reasoning") or "", model=r.get("model") or "?", tier="t1", caps=caps,
            concerns=list(r.get("concerns") or []),
        )
    return out


def run_eval(
    *,
    conn: sqlite3.Connection,
    resume_text: str,
    profile: dict | None,
    search_cfg: dict | None = None,
    cheap_model: str | None = None,
    strong_model: str | None = None,
    escalate: bool = True,
    escalate_at: int = 6,
    use_examples: bool = True,
    k_examples: int = 8,
    min_positive_examples: int = 2,
    limit: int = 0,
    workers: int = 12,
    seed: int = 7,
    thresholds: tuple[int, ...] = (6, 7, 8),
    write_history: bool = True,
    report_dir: Path | None = None,
    borderline: Borderline | None = None,
    reuse_report: Path | None = None,
) -> dict[str, Any]:
    items = [i for i in build_eval_set(conn) if len(i.description) >= 200]
    if limit and limit < len(items):
        rng = random.Random(seed)
        pos = [i for i in items if i.label == 1]
        neg = [i for i in items if i.label == 0]
        n_pos = max(1, round(limit * len(pos) / len(items)))
        items = rng.sample(pos, min(n_pos, len(pos))) + rng.sample(neg, min(limit - n_pos, len(neg)))
    criteria = load_criteria(profile)
    index = ExampleIndex(build_eval_set(conn)) if use_examples else None
    ctx = MatchContext(
        resume_text=resume_text, criteria=criteria, index=index, search_cfg=search_cfg,
        k_examples=k_examples, leave_one_out=True, min_positive_examples=min_positive_examples,
    )
    jobs = [_item_job(i) for i in items]
    prior = prior_from_report(reuse_report, jobs, ctx) if reuse_report else None
    borderline = borderline or Borderline()
    usage_snapshot(reset=True)
    t0 = time.time()
    results, errors = score_jobs(
        ctx, jobs, workers=workers, escalate=escalate, escalate_at=escalate_at,
        cheap_model=cheap_model, strong_model=strong_model, borderline=borderline, prior=prior,
    )
    elapsed = time.time() - t0
    usage = usage_snapshot(reset=True)
    by_url = {r.url: r for r in results}
    run_id = f"eval-{uuid.uuid4().hex[:8]}"
    rows = []
    for it in items:
        r = by_url.get(it.url)
        rows.append({
            "url": it.url, "title": it.title, "company": it.company, "label": it.label, "source": it.source,
            "label_score": it.label_score, "rationale": it.rationale, "baseline": it.model_score,
            "score": r.score if r else None, "fit": r.fit if r else None, "confidence": r.confidence if r else None,
            "dealbreakers": r.dealbreakers if r else None, "caps": r.caps if r else None,
            "concerns": r.concerns if r else None, "location_ok": r.location_ok if r else None,
            "seniority": r.seniority if r else None, "location": it.location, "salary": it.salary,
            "tier": r.tier if r else None, "model": r.model if r else None,
            "reasoning": r.reasoning if r else None,
            "escalated_from": r.escalated_from if r else None,
            "second_opinion": r.second_opinion if r else None,
        })
    report = {
        "run_id": run_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": ctx.version,
        "criteria_derived": criteria.derived,
        "config": {
            "cheap_model": cheap_model, "strong_model": strong_model, "escalate": escalate,
            "escalate_at": escalate_at, "use_examples": use_examples, "k_examples": k_examples,
            "min_positive_examples": min_positive_examples,
            "borderline": borderline.__dict__ if borderline.enabled else None,
            "reused": str(reuse_report) if reuse_report else None, "reused_rows": len(prior or {}),
            "limit": limit, "n": len(items), "positives": sum(i.label for i in items),
        },
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
        "usage": usage,
        "metrics": {str(t): metrics([(r["score"], r["label"]) for r in rows], t) for t in thresholds},
        "baseline": {str(t): metrics([(r["baseline"], r["label"]) for r in rows], t) for t in thresholds},
        # Explicit labels only: drops "closed without applying" negatives, which
        # are weak (expired postings, bulk triage) and cap measurable precision.
        "metrics_explicit": {
            str(t): metrics([(r["score"], r["label"]) for r in rows if r["source"] != "closed_unapplied"], t)
            for t in thresholds
        },
        "baseline_explicit": {
            str(t): metrics([(r["baseline"], r["label"]) for r in rows if r["source"] != "closed_unapplied"], t)
            for t in thresholds
        },
        "escalated": sum(1 for r in results if r.tier == "t2"),
        "second_opinions": sum(1 for r in results if r.second_opinion),
        "items": rows,
    }
    report["sweep"] = threshold_sweep(rows)
    report["recommended"] = recommend_threshold(report["sweep"])
    if write_history:
        now = report["at"]
        conn.executemany(
            "INSERT INTO score_history (job_url, score, confidence, gates, reasoning, model, prompt_version, "
            "tier, run_kind, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'eval', ?, ?)",
            [(r.url, r.score, r.confidence, r.gates_json(), r.reasoning_text(), r.model, ctx.version, r.tier,
              run_id, now) for r in results],
        )
        conn.commit()
    out_dir = report_dir or Path(config.LOG_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id}.json"
    path.write_text(json.dumps(report, indent=2, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o)))
    report["report_path"] = str(path)
    return report
