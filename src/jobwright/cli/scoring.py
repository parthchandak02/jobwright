"""Scoring quality: `eval`, `rescore`, `criteria ...`, `labels ...`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from jobwright.cli._common import _load_profile_or_none, bootstrap, console


criteria_app = typer.Typer(help="Match criteria (what makes a posting worth your time).")
labels_app = typer.Typer(help="Human relevance labels (every rescore is kept).")


def eval_cmd(
    limit: int = typer.Option(0, "--limit", help="Stratified sample size (0 = full labeled set)."),
    escalation_model: Optional[str] = typer.Option(None, "--escalation-model", help="Also test a stronger tier."),
    k_examples: int = typer.Option(12, "--examples", help="Retrieved past decisions per job (0 disables)."),
    workers: int = typer.Option(12, "--workers", "-w"),
    borderline: Optional[str] = typer.Option(
        None, "--borderline", help="Second opinion for first-pass scores in this band, e.g. 5-6 (default: JOBWRIGHT_BORDERLINE_BAND)."
    ),
    borderline_model: Optional[str] = typer.Option(None, "--borderline-model", help="Model for the second opinion."),
    borderline_combine: str = typer.Option("max", "--borderline-combine", help="max or mean."),
    reuse: Optional[Path] = typer.Option(
        None, "--reuse", help="Reuse first-pass judgments from an eval report (re-gated); only new calls cost tokens."
    ),
) -> None:
    """Replay the scorer over your labeled jobs and report precision / recall."""
    bootstrap()
    from jobwright.config import load_search_config
    from jobwright.database import get_connection
    from jobwright.resume import load_resume_text
    from jobwright.scoring.evaluate import run_eval
    from jobwright.scoring.matcher import Borderline, borderline_from_env, parse_band

    if borderline is None:
        band = borderline_from_env()
    else:
        lo, hi = parse_band(borderline)
        band = Borderline(low=lo, high=hi, model=borderline_model, combine=borderline_combine)
    report = run_eval(
        conn=get_connection(), resume_text=load_resume_text(), profile=_load_profile_or_none(),
        search_cfg=load_search_config(), strong_model=escalation_model, escalate=bool(escalation_model),
        use_examples=k_examples > 0, k_examples=max(k_examples, 1), min_positive_examples=4,
        limit=limit, workers=workers, borderline=band, reuse_report=reuse,
    )
    cfg_ = report["config"]
    console.print(f"[bold]Eval[/bold] {report['run_id']}  prompt {report['prompt_version']}  "
                  f"n={cfg_['n']} (relevant {cfg_['positives']})  errors={report['errors']}  {report['elapsed_s']}s")
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    for col in ("threshold", "set", "precision", "recall", "surfaced", "baseline P", "baseline R"):
        table.add_column(col)
    for t in ("6", "7", "8"):
        for label, m, b in (("all", report["metrics"][t], report["baseline"][t]),
                            ("explicit", report["metrics_explicit"][t], report["baseline_explicit"][t])):
            table.add_row(t, label, str(m["precision"]), str(m["recall"]), str(m["predicted_pos"]),
                          str(b["precision"]), str(b["recall"]))
    console.print(table)
    sweep = Table(show_header=True, header_style="bold", title="Threshold sweep")
    for col in ("threshold", "P explicit", "R explicit", "F0.5 explicit", "P all", "R all", "surfaced"):
        sweep.add_column(col)
    for row in report["sweep"]:
        e, a = row["explicit"], row["all"]
        sweep.add_row(str(row["threshold"]), str(e["precision"]), str(e["recall"]), str(e["f05"]),
                      str(a["precision"]), str(a["recall"]), str(a["predicted_pos"]))
    console.print(sweep)
    rec = report.get("recommended")
    if rec:
        bar = "meets" if rec["meets_bar"] else "no threshold meets"
        console.print(f"Recommended threshold: {rec['threshold']}+ ({bar} explicit precision >= {rec['min_precision']}; "
                      f"P {rec['precision']} R {rec['recall']})")
    if report.get("second_opinions"):
        console.print(f"Second opinions: {report['second_opinions']}")
    tokens = sum(u["prompt_tokens"] + u["completion_tokens"] for u in report["usage"])
    console.print(f"Tokens: {tokens:,}   Report: {report['report_path']}")


def rescore(
    scope: str = typer.Option(
        "active", "--scope",
        help="active (backlog+prepare), labeled, all, or since:<days> (discovered within N days).",
    ),
    limit: int = typer.Option(0, "--limit"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show how many jobs would be rescored."),
) -> None:
    """Re-run the current scorer on existing jobs; every new score is kept in score_history."""
    bootstrap()
    from jobwright.database import get_connection
    from jobwright.scoring.pipeline_v2 import score_job_list

    conn = get_connection()
    base = "SELECT * FROM jobs WHERE COALESCE(full_description, description) IS NOT NULL"
    params: list = []
    if scope == "active":
        base += " AND COALESCE(funnel_stage, 'backlog') IN ('backlog', 'prepare')"
    elif scope == "labeled":
        base += " AND url IN (SELECT job_url FROM score_labels)"
    elif scope.startswith("since:"):
        days = int(scope.split(":", 1)[1])
        base += " AND discovered_at >= datetime('now', ?)"
        params.append(f"-{days} days")
    elif scope != "all":
        console.print(f"[red]Unknown scope:[/red] {scope}")
        raise typer.Exit(code=2)
    base += " ORDER BY discovered_at DESC"
    if limit > 0:
        base += " LIMIT ?"
        params.append(limit)
    jobs = [dict(r) for r in conn.execute(base, params).fetchall()]
    console.print(f"{len(jobs)} jobs in scope '{scope}'.")
    if dry_run or not jobs:
        return
    out = score_job_list(jobs, conn=conn, run_kind="rescore")
    console.print(f"Rescored {out['scored']} (errors {out['errors']}) with {out['prompt_version']} in {out['elapsed']:.0f}s")


@criteria_app.command("show")
def criteria_show() -> None:
    """Print the criteria the scorer uses (curated, or derived from your profile)."""
    bootstrap()
    from jobwright.scoring.criteria import load_criteria, render_criteria

    c = load_criteria(_load_profile_or_none())
    console.print("[dim](derived from profile.job_preferences — not curated yet)[/dim]" if c.derived else "")
    console.print(render_criteria(c))
    console.print(f"\nNotify threshold: {c.notify_threshold}")


@criteria_app.command("suggest")
def criteria_suggest(
    save: bool = typer.Option(False, "--save", help="Write the proposal into profile.json match_criteria."),
) -> None:
    """Propose criteria from your resume, preferences and every rating you've made."""
    bootstrap()
    import json as _json

    import jobwright.config as config
    from jobwright.database import get_connection
    from jobwright.labels import build_eval_set
    from jobwright.resume import load_resume_text
    from jobwright.scoring.criteria_miner import suggest_criteria

    profile = _load_profile_or_none() or {}
    decisions = [i for i in build_eval_set(get_connection()) if i.source != "closed_unapplied"]
    proposal = suggest_criteria(resume_text=load_resume_text(), profile=profile, decisions=decisions)
    console.print_json(_json.dumps(proposal.to_dict()))
    if save:
        profile["match_criteria"] = proposal.to_dict()
        path = config.PROFILE_PATH
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(profile, indent=2), encoding="utf-8")
        tmp.replace(path)
        console.print(f"[green]Saved[/green] to {path}")


@labels_app.command("list")
def labels_list(limit: int = typer.Option(30, "--limit")) -> None:
    """Most recent human ratings."""
    bootstrap()
    from jobwright.database import get_connection

    rows = get_connection().execute(
        "SELECT created_at, label_score, source, title, company, rationale FROM score_labels "
        "WHERE verdict != 'cleared' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    for r in rows:
        console.print(f"{(r[0] or '')[:10]}  {r[1]:>2}/10  [{r[2]}]  {r[3]} @ {r[4] or '?'}  — {r[5] or ''}")


@labels_app.command("export")
def labels_export(path: str = typer.Argument(..., help="Output .jsonl path.")) -> None:
    """Export the full label history (append-only) as JSON lines."""
    bootstrap()
    import json as _json

    from jobwright.database import get_connection

    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r in conn.execute("SELECT * FROM score_labels ORDER BY created_at, id"):
            fh.write(_json.dumps(dict(r)) + "\n")
            n += 1
    console.print(f"Wrote {n} labels to {path}")
