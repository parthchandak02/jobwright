"""jobwright Pipeline Orchestrator.

Runs pipeline stages in sequence under a per-user lock and writes a
machine-readable summary (logs/last_run.json) used by alerts and the dashboard.

Usage (via CLI):
    jobwright run                        # default brief stages (honors human_gate, search_enabled)
    jobwright run discover enrich        # specific stages
    jobwright run score tailor cover     # LLM-only stages
    jobwright run --dry-run              # preview without executing
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import jobwright.config as config
from jobwright import stage_budget
from jobwright.config import load_env, ensure_dirs
from jobwright.database import init_db, get_connection, get_stats
from jobwright.llm import flush_active_usage, llm_purpose

log = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

STAGE_ORDER = ("discover", "enrich", "score", "portfolio", "tailor", "cover", "pdf", "docx", "connect")

STAGE_META: dict[str, dict] = {
    "discover": {"desc": "Job discovery (job boards incl. LinkedIn, Workday, impact boards; smart extract in full mode)"},
    "enrich":   {"desc": "Detail enrichment (full descriptions + apply URLs)"},
    "score":    {"desc": "Match scoring (criteria + past ratings, 1-10 with hard gates)"},
    "portfolio": {"desc": "Portfolio project selection per job"},
    "tailor":   {"desc": "Resume tailoring (LLM + validation)"},
    "cover":    {"desc": "Cover letter generation"},
    "pdf":      {"desc": "PDF conversion (tailored resumes + cover letters)"},
    "docx":     {"desc": "DOCX conversion (editable resume + cover letter)"},
    "connect":  {"desc": "Per-job connection ranking (CSV + web research)"},
}

# Default daily-brief stage list when the active user has human_gate enabled:
# the pipeline stops before material generation (tailor/cover/pdf/docx). Jobs
# are reviewed first; materials are generated on demand after approval.
BRIEF_STAGES_HUMAN_GATED = ("discover", "enrich", "score", "portfolio", "connect")
# Full brief runs every stage (the pre-gate default / on-demand full pipeline).
BRIEF_STAGES_FULL = STAGE_ORDER


def default_brief_stages() -> list[str]:
    """Resolve the default pipeline stage list for the active user.

    Honors the per-user ``human_gate`` config key: when True the default drops
    tailor/cover/pdf/docx. Explicit stage lists (e.g. ``jobwright run tailor
    cover docx``) are never altered and always run their full on-demand path.
    """
    from jobwright.config import get_active_user_id
    from jobwright.users import get_human_gate

    if get_human_gate(get_active_user_id()):
        return list(BRIEF_STAGES_HUMAN_GATED)
    return list(STAGE_ORDER)


def search_paused() -> bool:
    """True when the active profile turned off "Keep looking for new jobs".

    Only the default brief (``jobwright run`` with no stages, i.e. the cron)
    honors it; explicit stage lists always run.
    """
    from jobwright.config import get_active_user_id
    from jobwright.users import is_search_enabled

    return not is_search_enabled(get_active_user_id())


# ---------------------------------------------------------------------------
# Individual stage runners
# ---------------------------------------------------------------------------

def _source_health(new, errors=0, rate_limited=0, status: str | None = None, **extra) -> dict:
    """One discovery source's result: {new, errors, rate_limited, status}.

    ``degraded`` means it ran but some queries failed or were rate-limited, so
    "0 new" may be a broken source rather than a quiet day.
    """
    new, errors, rate_limited = int(new or 0), int(errors or 0), int(rate_limited or 0)
    if status is None:
        status = "degraded" if errors or rate_limited else "ok"
    return {"new": new, "errors": errors, "rate_limited": rate_limited, "status": status, **extra}


# Boards the circuit breaker took out (HTTP 403 all run, or cooling down after
# one): reported once as "blocked, skipped", not as a partial discover.
_SKIPPED_STATUSES = ("blocked", "cooldown")


def _add_site_health(sources: dict, site_health: dict) -> None:
    """Fold JobSpy's circuit-breaker summary into per-source health.

    ``blocked`` / ``cooldown`` boards get their own entry (no errors: the
    skip is deliberate); a rate-limited one (e.g. LinkedIn) keeps its counts
    and gains ``skipped``.
    """
    for site, health in site_health.items():
        status = health.get("status")
        skipped = int(health.get("skipped") or 0)
        if status in _SKIPPED_STATUSES:
            sources[site] = {
                "errors": 0, "rate_limited": 0, "status": status, "skipped": skipped,
                "blocked_responses": int(health.get("blocked_responses") or 0),
                **({"until": health["until"]} if health.get("until") else {}),
            }
        elif site in sources:
            sources[site]["skipped"] = skipped
            if sources[site].get("status") == "ok":
                sources[site]["status"] = "degraded"
        else:
            sources[site] = _source_health(
                None, 0, health.get("blocked_responses"), status="degraded", skipped=skipped,
            )
            sources[site].pop("new")


def _run_discover(workers: int = 1) -> dict:
    """Stage: Job discovery — JobSpy, Workday, and (full mode) smart-extract.

    DISCOVER_MODE env:
      fast (default) — JobSpy + Workday tier-1 only; skip smart-extract
      full — all configured queries + smart-extract

    ``sources`` records every source's {new, errors, rate_limited, status}
    (see ``_source_health``) so the brief report can name a broken board.
    """
    discover_mode = os.environ.get("DISCOVER_MODE", "fast").strip().lower()
    if discover_mode not in ("fast", "full"):
        log.warning("Unknown DISCOVER_MODE=%r; using fast", discover_mode)
        discover_mode = "fast"

    stats: dict = {"jobspy": None, "workday": None, "smartextract": None, "mode": discover_mode}
    sources: dict[str, dict] = {}
    console.print(f"  [dim]DISCOVER_MODE={discover_mode}[/dim]")
    if os.environ.get("BRIEF_SMOKE", "").strip() == "1":
        console.print("  [dim]BRIEF_SMOKE=1 (narrow discover, top 3 digest)[/dim]")

    # JobSpy (Indeed, ZipRecruiter, Glassdoor, ... plus the LinkedIn guest client)
    console.print("  [cyan]JobSpy full crawl...[/cyan]")
    try:
        from jobwright.discovery.jobspy import run_discovery
        res = run_discovery(workers=workers) or {}
        site_errors = res.get("site_errors") or {}
        li = res.get("linkedin") or None
        sources["jobspy"] = _source_health(
            res.get("new"), int(res.get("errors") or 0) + sum(site_errors.values()),
            queries=res.get("queries"), site_errors=site_errors,
        )
        if li is not None:
            sources["linkedin"] = _source_health(
                None, site_errors.get("linkedin", 0), li.get("rate_limited"),
                throttled=li.get("throttled"), requests=li.get("requests"),
            )
            sources["linkedin"].pop("new")  # counted inside jobspy's total
        _add_site_health(sources, res.get("site_health") or {})
        stats["jobspy"] = "ok"
    except Exception as e:
        log.error("JobSpy crawl failed: %s", e)
        console.print(f"  [red]JobSpy error:[/red] {e}")
        stats["jobspy"] = f"error: {e}"
        sources["jobspy"] = _source_health(0, 1, status=f"error: {e}"[:200])

    skip_workday = os.environ.get("DISCOVER_WORKDAY", "1").strip().lower() in ("0", "false", "no")
    if skip_workday:
        console.print("  [dim]Workday skipped (DISCOVER_WORKDAY=0)[/dim]")
        stats["workday"] = "skipped"
    else:
        # Workday corporate scraper
        console.print("  [cyan]Workday corporate scraper...[/cyan]")
        try:
            from jobwright.discovery.workday import run_workday_discovery
            res = run_workday_discovery(workers=workers) or {}
            sources["workday"] = _source_health(res.get("new"), res.get("errors"), queries=res.get("queries"))
            stats["workday"] = "ok"
        except Exception as e:
            log.error("Workday scraper failed: %s", e)
            console.print(f"  [red]Workday error:[/red] {e}")
            stats["workday"] = f"error: {e}"
            sources["workday"] = _source_health(0, 1, status=f"error: {e}"[:200])

    # Impact / social-sector boards — deterministic scrapers, no LLM, so they run
    # in fast mode too (the mode the daily brief uses). See discovery/impactboards.py.
    console.print("  [cyan]Impact boards (social sector)...[/cyan]")
    try:
        from jobwright.discovery.impactboards import run_impact_boards
        impact_report = run_impact_boards(workers=max(1, workers))
        stats["impact_boards"] = impact_report
        failed = [n for n, r in impact_report.items()
                  if isinstance(r, dict) and r.get("error")]
        for name, r in impact_report.items():
            if isinstance(r, dict):
                err = r.get("error")
                sources[f"impact:{name}"] = _source_health(
                    r.get("new"), 1 if err else 0, status=f"error: {err}"[:200] if err else None,
                )
        if failed:
            console.print(f"  [yellow]Impact boards failed:[/yellow] {', '.join(failed)}")
            stats["impact_boards_failed"] = failed
    except Exception as e:
        log.error("Impact boards failed: %s", e)
        console.print(f"  [red]Impact boards error:[/red] {e}")
        stats["impact_boards"] = f"error: {e}"
        sources["impact_boards"] = _source_health(0, 1, status=f"error: {e}"[:200])

    # Smart extract (full mode only — expensive LLM + Playwright)
    if discover_mode == "full":
        console.print("  [cyan]Smart extract (AI-powered scraping)...[/cyan]")
        try:
            from jobwright.discovery.smartextract import run_smart_extract
            res = run_smart_extract(workers=workers) or {}
            failed_sites = max(0, int(res.get("total") or 0) - int(res.get("passed") or 0))
            sources["smartextract"] = _source_health(res.get("total_new"), failed_sites)
            stats["smartextract"] = "ok"
        except Exception as e:
            log.error("Smart extract failed: %s", e)
            console.print(f"  [red]Smart extract error:[/red] {e}")
            stats["smartextract"] = f"error: {e}"
            sources["smartextract"] = _source_health(0, 1, status=f"error: {e}"[:200])
    else:
        console.print("  [dim]Smart extract skipped (DISCOVER_MODE=fast)[/dim]")
        stats["smartextract"] = "skipped"

    stats["sources"] = sources
    stats["new"] = sum(int(v.get("new") or 0) for v in sources.values())
    stats["dedupe"] = _dedupe()
    top = ("jobspy", "workday", "impact_boards", "smartextract")
    ran = [stats[k] for k in top if stats.get(k) not in (None, "skipped")]
    if ran and all(str(v).startswith("error") for v in ran):
        stats["status"] = "error: every discovery source failed"
    elif any(str(stats.get(k)).startswith("error") for k in top) or any(
        v.get("status") not in ("ok", *_SKIPPED_STATUSES) for v in sources.values()
    ):
        stats["status"] = "partial"
    else:
        stats["status"] = "ok"
    return stats


def _dedupe() -> dict:
    try:
        from jobwright.discovery.dedupe import dedupe_new_jobs

        return dedupe_new_jobs(get_connection())
    except Exception as e:  # noqa: BLE001 - dedupe must never sink a run
        log.warning("Dedupe skipped: %s", e)
        return {"error": str(e)}


def _collapse_duplicates() -> dict:
    """Close duplicate open cards (existing backlog, multi-location reposts); no LLM."""
    try:
        from jobwright.discovery.dedupe import collapse_duplicates

        out = collapse_duplicates(get_connection(), apply=True)
        return {k: out[k] for k in ("group_count", "closed")} | {"blocked": len(out["blocked"])}
    except Exception as e:  # noqa: BLE001 - dedupe must never sink a run
        log.warning("Duplicate collapse skipped: %s", e)
        return {"error": str(e)}


def _run_enrich(workers: int = 1) -> dict:
    """Stage: Detail enrichment — scrape full descriptions and apply URLs."""
    try:
        from jobwright.enrichment.detail import run_enrichment
        stats = run_enrichment(workers=workers) or {}
        processed = int(stats.get("processed") or 0)
        ok = int(stats.get("ok") or 0) + int(stats.get("partial") or 0)
        errors = int(stats.get("error") or 0)
        if processed > 0 and ok == 0 and errors > 0:
            return {"status": f"error: all {errors} enrichments failed", **stats}
        return {"status": "ok", **stats}
    except Exception as e:
        log.error("Enrichment failed: %s", e)
        return {"status": f"error: {e}"}


def _run_score() -> dict:
    """Stage: match scoring (v2 structured judgment + gates; v1 via JOBWRIGHT_SCORER)."""
    try:
        from jobwright.scoring.scorer import run_scoring

        _dedupe()
        result = run_scoring()
        scored = int(result.get("scored") or 0)
        errors = int(result.get("errors") or 0)
        if scored == 0 and errors > 0:
            return {"status": f"error: {errors} scoring failures", **result}
        try:
            from jobwright.database import get_connection
            from jobwright.discovery.cleanup import prune_after_score

            prune_stats = prune_after_score(get_connection(), dry_run=False)
            result["prune"] = prune_stats
        except Exception as prune_err:
            log.warning("Post-score prune skipped: %s", prune_err)
        result["collapse"] = _collapse_duplicates()
        return {"status": "ok", **result}
    except Exception as e:
        log.error("Scoring failed: %s", e)
        return {"status": f"error: {e}"}


def _prep_limit() -> int:
    """Cap portfolio/tailor/cover batch size for daily prep (default: 2x APPLY_LIMIT)."""
    apply_limit = int(os.environ.get("APPLY_LIMIT", "5"))
    return int(os.environ.get("APPLY_PREP_LIMIT", str(max(apply_limit * 2, 10))))


def _run_portfolio(min_score: int = 7) -> dict:
    """Stage: Portfolio project selection for high-fit jobs."""
    try:
        from jobwright.scoring.portfolio import run_portfolio_selection
        return run_portfolio_selection(min_score=min_score, limit=_prep_limit())
    except Exception as e:
        log.error("Portfolio selection failed: %s", e)
        return {"status": f"error: {e}"}


def _run_tailor(min_score: int = 7, validation_mode: str = "normal") -> dict:
    """Stage: Resume tailoring — generate tailored resumes for high-fit jobs."""
    try:
        from jobwright.scoring.tailor import run_tailoring
        stats = run_tailoring(min_score=min_score, limit=_prep_limit(), validation_mode=validation_mode) or {}
        ok = int(stats.get("approved") or 0)
        bad = int(stats.get("failed") or 0) + int(stats.get("errors") or 0)
        if ok == 0 and bad > 0:
            return {"status": f"error: all {bad} tailor attempts failed", **stats}
        return {"status": "ok", **stats}
    except Exception as e:
        log.error("Tailoring failed: %s", e)
        return {"status": f"error: {e}"}


def _run_cover(min_score: int = 7, validation_mode: str = "normal") -> dict:
    """Stage: Cover letter generation."""
    try:
        from jobwright.scoring.cover_letter import run_cover_letters
        stats = run_cover_letters(min_score=min_score, limit=_prep_limit(), validation_mode=validation_mode) or {}
        ok = int(stats.get("generated") or 0)
        bad = int(stats.get("errors") or 0)
        if ok == 0 and bad > 0:
            return {"status": f"error: all {bad} cover letters failed", **stats}
        return {"status": "ok", **stats}
    except Exception as e:
        log.error("Cover letter generation failed: %s", e)
        return {"status": f"error: {e}"}


def _run_pdf() -> dict:
    """Stage: PDF conversion — convert tailored resumes and cover letters to PDF."""
    try:
        from jobwright.scoring.pdf import batch_convert
        converted = batch_convert()
        return {"status": "ok", "converted": converted}
    except Exception as e:
        log.error("PDF conversion failed: %s", e)
        return {"status": f"error: {e}"}


def _run_docx(min_score: int = 7) -> dict:
    """Stage: DOCX conversion — editable Word docs for WhatsApp review."""
    try:
        from jobwright.scoring.docx_export import batch_convert_docx
        return batch_convert_docx(limit=_prep_limit(), min_score=min_score)
    except Exception as e:
        log.error("DOCX conversion failed: %s", e)
        return {"status": f"error: {e}"}


def _run_connect(min_score: int = 7) -> dict:
    """Stage: Per-job connection ranking (CSV + optional Exa web research)."""
    try:
        from jobwright.network.per_job import run_per_job_connect
        limit = int(os.environ.get("JOBWRIGHT_CONNECT_LIMIT", "15"))
        return run_per_job_connect(min_score=min_score, limit=limit)
    except Exception as e:
        log.error("Connect stage failed: %s", e)
        return {"status": f"error: {e}"}


# Map stage names to their runner functions
_STAGE_RUNNERS: dict[str, callable] = {
    "discover": _run_discover,
    "enrich":   _run_enrich,
    "score":    _run_score,
    "portfolio": _run_portfolio,
    "tailor":   _run_tailor,
    "cover":    _run_cover,
    "pdf":      _run_pdf,
    "docx":     _run_docx,
    "connect":  _run_connect,
}


# ---------------------------------------------------------------------------
# Stage resolution
# ---------------------------------------------------------------------------

def _resolve_stages(stage_names: list[str]) -> list[str]:
    """Resolve 'all' and validate/order stage names."""
    if "all" in stage_names:
        return list(STAGE_ORDER)

    resolved = []
    for name in stage_names:
        if name not in STAGE_META:
            console.print(
                f"[red]Unknown stage:[/red] '{name}'. "
                f"Available: {', '.join(STAGE_ORDER)}, all"
            )
            raise SystemExit(1)
        if name not in resolved:
            resolved.append(name)

    # Maintain canonical order
    return [s for s in STAGE_ORDER if s in resolved]


# ---------------------------------------------------------------------------
# Run lock + summary
# ---------------------------------------------------------------------------

class PipelineLocked(RuntimeError):
    """Another pipeline run already holds this user's lock."""


@contextmanager
def pipeline_lock():
    """Exclusive per-user lock so cron, dashboard and CLI runs never overlap.

    flock is released by the kernel if the process dies, so a crashed run can
    never wedge the next one.
    """
    lock_path = Path(config.APP_DIR) / ".pipeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.seek(0)
            holder = fh.read().strip() or "unknown"
            raise PipelineLocked(f"Another pipeline run is active for this profile ({holder}).") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}")
        fh.flush()
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


def lock_holder() -> str | None:
    """Who holds this profile's pipeline lock right now ("pid=N started=..."), or None if free."""
    lock_path = Path(config.APP_DIR) / ".pipeline.lock"
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    pid = None
    for part in text.split():
        if part.startswith("pid="):
            try:
                pid = int(part[4:])
            except ValueError:
                pid = None
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    return text


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def write_run_summary(result: dict, stages: list[str], started_at: str) -> Path:
    """Persist logs/last_run.json (atomic) for alerts, health and the dashboard."""
    path = Path(config.LOG_DIR) / "last_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "user": config.get_active_user_id(),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stages_requested": stages,
        "ok": not result.get("errors"),
        "errors": result.get("errors", {}),
        "stages": _json_safe(result.get("stages", [])),
        "elapsed": result.get("elapsed"),
        "web_run_id": os.environ.get("JOBWRIGHT_WEB_RUN_ID") or None,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_run_summary() -> dict | None:
    path = Path(config.LOG_DIR) / "last_run.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def _run_sequential(ordered: list[str], min_score: int, workers: int = 1,
                    validation_mode: str = "normal") -> dict:
    """Execute stages one at a time."""
    results: list[dict] = []
    errors: dict[str, str] = {}
    pipeline_start = time.time()
    usage_run_id = os.environ.get("JOBWRIGHT_WEB_RUN_ID") or f"pipeline-{uuid.uuid4().hex[:8]}"

    for name in ordered:
        meta = STAGE_META[name]
        console.print(f"\n{'=' * 70}")
        console.print(f"  [bold]STAGE: {name}[/bold] — {meta['desc']}")
        console.print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")
        console.print(f"{'=' * 70}")

        t0 = time.time()
        runner = _STAGE_RUNNERS[name]
        detail: dict = {}

        budget = stage_budget.start(name)
        if budget:
            console.print(f"  Soft budget: {budget / 60:.0f} min (JOBWRIGHT_STAGE_BUDGET_{name.upper()})")
        try:
            kwargs: dict = {}
            if name in ("tailor", "cover", "portfolio", "docx", "connect"):
                kwargs["min_score"] = min_score
            if name in ("tailor", "cover"):
                kwargs["validation_mode"] = validation_mode
            if name in ("discover", "enrich"):
                kwargs["workers"] = workers
            with llm_purpose(name):  # default tag; call sites refine it
                result = runner(**kwargs)
            elapsed = time.time() - t0

            status = "ok"
            if isinstance(result, dict):
                detail = result
                status = str(result.get("status", "ok"))

        except Exception as e:
            elapsed = time.time() - t0
            status = f"error: {e}"
            log.exception("Stage '%s' crashed", name)
            console.print(f"\n  [red]STAGE FAILED:[/red] {e}")

        over_budget = stage_budget.exceeded()
        stage_budget.clear()
        if over_budget:
            log.warning("Stage '%s' ran past its soft budget (%.0fs); moved on", name, elapsed)
            detail = {**detail, "over_budget": True}
        flush_active_usage(usage_run_id)  # LLM spend per stage -> this user's llm_usage
        results.append({"stage": name, "status": status, "elapsed": elapsed, "detail": detail})
        if status not in ("ok", "partial", "skipped"):
            errors[name] = status

        console.print(f"\n  Stage '{name}' completed in {elapsed:.1f}s — {status}")

    total_elapsed = time.time() - pipeline_start
    return {"stages": results, "errors": errors, "elapsed": total_elapsed}


def run_pipeline(
    stages: list[str] | None = None,
    min_score: int = 7,
    dry_run: bool = False,
    workers: int = 1,
    validation_mode: str = "normal",
) -> dict:
    """Run pipeline stages.

    Args:
        stages: List of stage names, or None / ["all"] for full pipeline.
        min_score: Minimum fit score for tailor/cover stages.
        dry_run: If True, preview stages without executing.
        workers: Number of parallel threads for discovery/enrichment stages.

    Returns:
        Dict with keys: stages (list of result dicts), errors (dict), elapsed (float).
    """
    # Bootstrap
    load_env()
    ensure_dirs()
    init_db()

    # Resolve stages
    if stages is None:
        if search_paused():
            console.print(
                "\n  [yellow]New job search is paused for this profile[/yellow] "
                "(search_enabled: false). Skipping the default brief stages; "
                "pass explicit stages to run anyway."
            )
            return {"stages": [], "errors": {}, "elapsed": 0.0, "paused": True}
        stages = default_brief_stages()
    ordered = _resolve_stages(stages)

    # Banner
    mode = "sequential"
    console.print()
    console.print(Panel.fit(
        f"[bold]jobwright Pipeline[/bold] ({mode})",
        border_style="blue",
    ))
    console.print(f"  Min score:  {min_score}")
    console.print(f"  Workers:    {workers}")
    console.print(f"  Validation: {validation_mode}")
    console.print(f"  Stages:     {' -> '.join(ordered)}")

    # Pre-run stats
    pre_stats = get_stats()
    console.print(f"  DB:        {pre_stats['total']} jobs, {pre_stats['pending_detail']} pending enrichment")

    if dry_run:
        console.print(f"\n  [yellow]DRY RUN[/yellow] — would execute ({mode}):")
        for name in ordered:
            meta = STAGE_META[name]
            console.print(f"    {name:<12s}  {meta['desc']}")
        console.print("\n  No changes made.")
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    from jobwright.run_registry import register_pipeline_run

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        with pipeline_lock():
            register_pipeline_run(ordered)
            result = _run_sequential(ordered, min_score, workers=workers,
                                     validation_mode=validation_mode)
            write_run_summary(result, ordered, started_at)
    except PipelineLocked as exc:
        console.print(f"\n  [yellow]{exc}[/yellow] Not starting a second run.")
        return {"stages": [], "errors": {"lock": str(exc)}, "elapsed": 0.0, "locked": True}

    # Summary table
    console.print(f"\n{'=' * 70}")
    summary = Table(title="Pipeline Summary", show_header=True, header_style="bold")
    summary.add_column("Stage", style="bold")
    summary.add_column("Status")
    summary.add_column("Time", justify="right")

    for r in result["stages"]:
        elapsed_str = f"{r['elapsed']:.1f}s"
        status_display = r["status"][:30]
        if r["status"] == "ok":
            style = "green"
        elif r["status"] in ("partial", "skipped"):
            style = "yellow"
        else:
            style = "red"
        summary.add_row(r["stage"], f"[{style}]{status_display}[/{style}]", elapsed_str)

    summary.add_row("", "", "")
    summary.add_row("[bold]Total[/bold]", "", f"[bold]{result['elapsed']:.1f}s[/bold]")
    console.print(summary)

    # Final DB stats
    final = get_stats()
    console.print("\n  [bold]DB Final State:[/bold]")
    console.print(f"    Total jobs:     {final['total']}")
    console.print(f"    With desc:      {final['with_description']}")
    console.print(f"    Scored:         {final['scored']}")
    console.print(f"    Tailored:       {final['tailored']}")
    console.print(f"    Cover letters:  {final['with_cover_letter']}")
    console.print(f"    Ready to apply: {final['ready_to_apply']}")
    console.print(f"    Applied:        {final['applied']}")
    console.print(f"{'=' * 70}\n")

    return result
