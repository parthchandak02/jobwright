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
from jobwright.scoring.matcher import MatchContext, score_jobs


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


def _item_job(item: EvalItem) -> dict[str, Any]:
    return {
        "url": item.url, "title": item.title, "company": item.company, "location": item.location,
        "salary": item.salary, "full_description": item.description, "dedupe_key": item.dedupe_key,
    }


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
    usage_snapshot(reset=True)
    t0 = time.time()
    results, errors = score_jobs(
        ctx, [_item_job(i) for i in items], workers=workers, escalate=escalate, escalate_at=escalate_at,
        cheap_model=cheap_model, strong_model=strong_model,
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
            "tier": r.tier if r else None, "model": r.model if r else None,
            "reasoning": r.reasoning if r else None,
            "escalated_from": r.escalated_from if r else None,
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
        "items": rows,
    }
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
