"""Match quality: criteria, rating history, eval runs, scoreboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import config
from jobwright.database import get_connection
from jobwright.web.jobkeys import resolve_job_key
from jobwright.web.session import current_user_id

router = APIRouter(prefix="/api", tags=["quality"])


def _profile() -> dict:
    try:
        return json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_profile(profile: dict) -> None:
    """Atomically replace the active profile's profile.json (owner-only)."""
    path = Path(config.PROFILE_PATH)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def latest_eval_report() -> dict | None:
    """Newest stored eval report for the active profile (full runs preferred over --limit runs)."""
    parsed = []
    for path in sorted(Path(config.LOG_DIR).glob("eval_*.json")):
        try:
            parsed.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    full = [r for r in parsed if not (r.get("config") or {}).get("limit")]
    return (full or parsed or [None])[-1]


@router.get("/criteria")
def get_criteria(request: Request) -> dict:
    from jobwright.scoring.criteria import load_criteria

    current_user_id(request)
    c = load_criteria(_profile())
    return {"criteria": c.to_dict(), "derived": c.derived}


class CriteriaBody(BaseModel):
    criteria: dict[str, Any]


@router.put("/criteria")
def put_criteria(body: CriteriaBody, request: Request) -> dict:
    from jobwright.scoring.criteria import parse_criteria

    current_user_id(request)
    parsed = parse_criteria(body.criteria)
    profile = _profile()
    profile["match_criteria"] = parsed.to_dict()
    write_profile(profile)
    return {"criteria": parsed.to_dict(), "derived": False}


@router.post("/criteria/suggest")
def suggest(request: Request) -> dict:
    from jobwright.labels import build_eval_set
    from jobwright.resume import load_resume_text
    from jobwright.scoring.criteria_miner import suggest_criteria

    current_user_id(request)
    try:
        resume = load_resume_text()
    except FileNotFoundError as exc:
        raise HTTPException(400, "Upload a resume first.") from exc
    decisions = [i for i in build_eval_set(get_connection()) if i.source != "closed_unapplied"]
    try:
        proposal = suggest_criteria(resume_text=resume, profile=_profile(), decisions=decisions)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Could not draft criteria: {exc}") from exc
    return {"criteria": proposal.to_dict(), "based_on_ratings": len(decisions)}


@router.get("/jobs/{url:path}/labels")
def job_labels(url: str, request: Request) -> dict:
    from jobwright.labels import label_history

    current_user_id(request)
    url = resolve_job_key(url)
    conn = get_connection()
    history = conn.execute(
        "SELECT score, confidence, tier, model, prompt_version, run_kind, created_at FROM score_history "
        "WHERE job_url = ? ORDER BY created_at DESC LIMIT 10",
        (url,),
    ).fetchall()
    return {"labels": label_history(url, conn), "machine_scores": [dict(r) for r in history]}


def _recommendation(report: dict) -> dict | None:
    from jobwright.scoring.criteria import load_criteria
    from jobwright.scoring.evaluate import recommend_threshold, threshold_sweep

    rec = report.get("recommended")
    if rec is None and report.get("items"):
        rec = recommend_threshold(threshold_sweep(report["items"]))
    if not rec:
        return None
    return {**rec, "current": load_criteria(_profile()).notify_threshold}


@router.get("/quality")
def quality(request: Request) -> dict:
    """Scoreboard: ratings, label-based precision of what was shown, latest eval."""
    from jobwright.labels import build_eval_set

    current_user_id(request)
    conn = get_connection()
    items = build_eval_set(conn)
    labels_total = conn.execute("SELECT COUNT(*) FROM score_labels WHERE verdict != 'cleared'").fetchone()[0]
    labels_30d = conn.execute(
        "SELECT COUNT(*) FROM score_labels WHERE verdict != 'cleared' AND created_at >= datetime('now', '-30 days')"
    ).fetchone()[0]
    shown = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN j.funnel_stage IN ('prepare','applied','in_progress','offer') THEN 1 ELSE 0 END) "
        "FROM jobs j WHERE j.whatsapp_notified_at >= datetime('now', '-30 days')"
    ).fetchone()
    latest_eval = None
    rep = latest_eval_report()
    recommended = None
    if rep:
        latest_eval = {k: rep.get(k) for k in ("run_id", "at", "prompt_version", "config", "metrics",
                                               "metrics_explicit", "baseline", "baseline_explicit", "errors")}
        recommended = _recommendation(rep)
    usage = conn.execute(
        "SELECT purpose, SUM(prompt_tokens), SUM(completion_tokens), SUM(cost_usd) FROM llm_usage "
        "WHERE at >= datetime('now', '-30 days') GROUP BY purpose"
    ).fetchall()
    return {
        "labels_total": labels_total,
        "labels_30d": labels_30d,
        "eval_set": {"size": len(items), "relevant": sum(i.label for i in items)},
        "notified_30d": shown[0] or 0,
        "notified_advanced_30d": shown[1] or 0,
        "latest_eval": latest_eval,
        "recommended_threshold": recommended,
        "usage_30d": [
            {"purpose": r[0], "prompt_tokens": r[1] or 0, "completion_tokens": r[2] or 0, "cost_usd": r[3]}
            for r in usage
        ],
    }


@router.post("/quality/eval")
def start_eval(request: Request) -> dict:
    from jobwright.web.routers.runs import spawn_logged_run

    uid = current_user_id(request)
    return spawn_logged_run(args=["eval"], user_id=uid, stages=["eval"], log_name="web_eval", kind="eval")


@router.post("/quality/rescore")
def start_rescore(request: Request) -> dict:
    from jobwright.web.routers.runs import spawn_logged_run

    uid = current_user_id(request)
    return spawn_logged_run(
        args=["rescore", "--scope", "active"], user_id=uid, stages=["rescore"], log_name="web_rescore",
        kind="rescore",
    )
