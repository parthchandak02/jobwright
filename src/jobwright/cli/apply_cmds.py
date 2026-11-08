"""`apply` (one-off and automatic applications) and `answers` (the answer bank)."""

from __future__ import annotations

import json
from typing import Optional

import typer

from jobwright.cli._common import bootstrap, console

apply_app = typer.Typer(
    help="Apply to jobs (dry run unless --live). Subcommands: auto, pick, veto, due, provide, pending, "
         "submissions, resume.",
    invoke_without_command=True,
)
answers_app = typer.Typer(help="Saved application answers (attestations are only ever answered from here).")

LEGACY_PROVIDERS = ("cursor-sdk", "cursor-cli", "claude")


def _active() -> str | None:
    from jobwright.config import get_active_user_id

    return get_active_user_id()


def _find_job(url: str) -> dict | None:
    from jobwright.database import get_connection

    norm = url.split("?")[0].rstrip("/")
    conn = get_connection()
    for row in conn.execute("SELECT * FROM jobs WHERE url = ? OR application_url = ? OR job_id = ?",
                            (url, url, url)).fetchall():
        return dict(row)
    for row in conn.execute("SELECT * FROM jobs").fetchall():
        for key in ("url", "application_url"):
            if (row[key] or "").split("?")[0].rstrip("/") == norm:
                return dict(row)
    return None


def _print_outcome(res) -> None:
    color = {"applied": "green", "dry_run": "cyan", "unverified": "yellow", "needs_answer": "yellow"}.get(
        res.outcome, "red")
    console.print(f"[{color}]{res.outcome}[/{color}]  {res.title} @ {res.company}"
                  + (f"  (submission {res.submission_id})" if res.submission_id else ""))
    for r in res.reasons:
        console.print(f"   - {r}")
    for q in res.questions:
        console.print(f"   needs answer: {q}")


@apply_app.callback()
def apply(
    ctx: typer.Context,
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications."),
    workers: int = typer.Option(1, "--workers", "-w", help="(legacy) parallel browser workers."),
    min_score: int = typer.Option(8, "--min-score", help="Minimum score for job selection."),
    model: str = typer.Option("", "--model", "-m", help="Agent model (default JOBWRIGHT_APPLY_MODEL)."),
    agent_provider: str = typer.Option(
        None, "--agent-provider",
        help="anthropic (default). Legacy cursor-sdk / cursor-cli / claude are dry-run only.",
    ),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="(legacy, dry run) poll for jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fill but never submit (the default)."),
    live: bool = typer.Option(False, "--live", help="Actually submit (requires apply_enabled)."),
    headless: bool = typer.Option(False, "--headless", help="Run the browser headless."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="(legacy) write the prompt file for debugging."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
) -> None:
    """Apply to jobs: dry run unless --live; live needs apply_enabled."""
    if ctx.invoked_subcommand:
        return
    bootstrap()
    import os

    from jobwright.users import is_apply_enabled

    if live and dry_run:
        console.print("[red]--live and --dry-run are mutually exclusive.[/red]")
        raise typer.Exit(code=2)
    dry_run = not live
    active = _active()
    if live and not is_apply_enabled(active):
        console.print(
            f"[red]Live apply disabled[/red] for user '{active}'.\n"
            f"Enable with: jobwright users set {active} --apply\n"
            "Finding + tailoring still work without apply."
        )
        raise typer.Exit(code=1)
    if live:
        from jobwright.users import get_user

        via = getattr(get_user(active), "apply_via", "connector") if active else "server"
        if via != "server":
            console.print(
                f"[red]Live apply via the server runner is off[/red] for '{active}' (apply_via: {via}).\n"
                "This profile applies through the person's own Claude (docs/agents/claude-connector.md).\n"
                f"Owner only: jobwright users set {active} --apply-via server"
            )
            raise typer.Exit(code=1)
    if agent_provider:
        os.environ["AGENT_PROVIDER"] = agent_provider
    from jobwright.config import get_agent_provider

    provider = get_agent_provider()

    if mark_applied:
        from jobwright.apply.launcher import mark_job
        mark_job(mark_applied, "applied")
        console.print(f"[green]Marked as applied:[/green] {mark_applied}")
        return
    if mark_failed:
        from jobwright.apply.launcher import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        console.print(f"[yellow]Marked as failed:[/yellow] {mark_failed} ({fail_reason or 'manual'})")
        return
    if reset_failed:
        from jobwright.apply.launcher import reset_failed as do_reset
        console.print(f"[green]Reset {do_reset()} failed job(s) for retry.[/green]")
        return

    if provider in LEGACY_PROVIDERS:
        if live:
            console.print(f"[red]{provider} is a legacy provider and cannot submit applications.[/red] "
                          "Use the default anthropic provider.")
            raise typer.Exit(code=2)
        _legacy_dry_run(limit=limit, workers=workers, min_score=min_score, model=model or "composer-2.5",
                        continuous=continuous, headless=headless, url=url, gen=gen)
        return
    if gen or continuous or workers != 1:
        console.print("[yellow]--gen / --continuous / --workers only apply to legacy providers; ignored.[/yellow]")
    if model:
        os.environ["JOBWRIGHT_APPLY_MODEL"] = model

    from jobwright.apply.auto import candidates
    from jobwright.apply.runner import apply_job

    if url:
        job = _find_job(url)
        if job is None:
            console.print("[red]No job with that URL on the board.[/red]")
            raise typer.Exit(code=1)
        jobs = [job]
    else:
        jobs = candidates(active, limit or 1, min_score=min_score)
        if not jobs:
            console.print(f"[yellow]No eligible job scores {min_score}+.[/yellow]")
            return
    console.print(f"[bold]Applying[/bold] ({'LIVE' if live else 'dry run'}) to {len(jobs)} job(s)")
    failed = False
    for job in jobs:
        res = apply_job(job, dry_run=dry_run, user_id=active, headless=headless or None,
                        min_score=min_score)
        _print_outcome(res)
        failed = failed or res.outcome in ("failed", "error")
    if failed:
        raise typer.Exit(code=1)


def _legacy_dry_run(*, limit, workers, min_score, model, continuous, headless, url, gen) -> None:
    import jobwright.config as config
    from jobwright.config import check_tier

    check_tier(3, "auto-apply")
    if not config.PROFILE_PATH.exists():
        console.print("[red]Profile not found.[/red] Run [bold]jobwright init[/bold] first.")
        raise typer.Exit(code=1)
    if gen:
        from jobwright.apply.launcher import gen_prompt
        if not url:
            console.print("[red]--gen requires --url.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(url, min_score=min_score, model=model)
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        return
    from jobwright.apply.launcher import main as apply_main

    apply_main(limit=limit if limit is not None else (0 if continuous else 1), target_url=url,
               min_score=min_score, headless=headless, model=model, dry_run=True, continuous=continuous,
               workers=workers)


@apply_app.command("auto")
def apply_auto(
    dry_run: bool = typer.Option(False, "--dry-run", help="Rehearse: dry-run today's would-be picks now."),
    no_post: bool = typer.Option(False, "--no-post", help="Pick without posting to WhatsApp."),
) -> None:
    """Daily automatic apply: pick (veto mode posts and waits) or pick + apply (auto mode)."""
    bootstrap()
    from jobwright.apply import auto

    active = _active()
    if dry_run:
        results = auto.dry_run_auto(active)
        if not results:
            console.print("[yellow]Nothing eligible.[/yellow]")
        for r in results:
            console.print(f"{r['outcome']}: {r['title']} @ {r['company']} (submission {r['submission_id']})")
        return
    result = auto.run_auto(active, post=not no_post)
    _print_picks(result)


def _print_picks(result: dict) -> None:
    for reason in result.get("reasons") or []:
        console.print(f"[yellow]{reason}[/yellow]")
    for p in result.get("picks") or []:
        console.print(f"#{p['id']} ({p['number']}) {p['title']} @ {p['company']}  score {p['score']}  "
                      f"applies after {p['apply_after']}")
    for p in result.get("applied") or []:
        console.print(f"  -> #{p['id']} {p['status']} ({p['outcome']})")


@apply_app.command("pick")
def apply_pick(no_post: bool = typer.Option(False, "--no-post", help="Do not post to WhatsApp.")) -> None:
    """Choose today's picks and post them with the veto deadline."""
    bootstrap()
    from jobwright.apply import auto

    _print_picks(auto.pick(_active(), post=not no_post))


@apply_app.command("veto")
def apply_veto(
    target: str = typer.Argument(..., help="Pick id, or 'all'. With --number: the number in the latest message."),
    number: bool = typer.Option(False, "--number", "-n", help="TARGET is the number from the picks message."),
    by: str = typer.Option("cli", "--by", help="Who vetoed (cli, whatsapp, dashboard)."),
) -> None:
    """Skip a planned application before its apply time ("skip 2" / "skip all")."""
    bootstrap()
    from jobwright.apply.auto import VetoError, veto

    try:
        rows = veto(target, by=by, number=number)
    except VetoError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    for r in rows:
        console.print(f"[green]Skipped[/green] {r['number']}. {r['title']} @ {r['company']}")


@apply_app.command("due")
def apply_due(no_report: bool = typer.Option(False, "--no-report", help="Do not post the report.")) -> None:
    """Apply every planned pick whose veto window has passed, then post the report."""
    bootstrap()
    from jobwright.apply import auto

    done = auto.due(_active(), report=not no_report)
    if not done:
        console.print("[dim]Nothing due.[/dim]")
    for p in done:
        console.print(f"#{p['id']} {p['title']} @ {p['company']}: {p['status']} ({p['outcome']})")


@apply_app.command("provide")
def apply_provide(
    pending_id: str = typer.Argument(..., help="Ref from the WhatsApp message."),
    value: str = typer.Argument("", help="The code, the answer, or nothing for a solved CAPTCHA."),
    by: str = typer.Option("whatsapp", "--by"),
) -> None:
    """Hand a verification code / answer / "CAPTCHA solved" to a waiting apply run."""
    bootstrap()
    from jobwright.apply.hitl import ProvideError, provide

    try:
        row = provide(pending_id, value, by=by)
    except ProvideError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    what = {"email_code": "Code passed on", "captcha": "Marked solved", "answer": "Answer saved"}[row["kind"]]
    console.print(f"[green]{what}[/green] ({row['company']}).")


@apply_app.command("pending")
def apply_pending(all_: bool = typer.Option(False, "--all", help="Include resolved / expired.")) -> None:
    """Open requests waiting for the person (codes, CAPTCHAs, answers)."""
    bootstrap()
    from jobwright.apply.hitl import list_pending

    rows = list_pending(None if all_ else "open")
    if not rows:
        console.print("[dim]No open requests.[/dim]")
    for r in rows:
        console.print(f"{r['id']}  {r['kind']:<10} {r['status']:<9} {r['company'] or '':<24} {r['prompt'][:80]}")


@apply_app.command("submissions")
def apply_submissions(limit: int = typer.Option(10, "--limit"), as_json: bool = typer.Option(False, "--json")) -> None:
    """Recent apply attempts with their evidence."""
    bootstrap()
    from jobwright.apply.evidence import list_submissions

    rows = list_submissions(limit)
    if as_json:
        console.print_json(json.dumps(rows, default=str))
        return
    for r in rows:
        console.print(f"#{r['id']} {r['started_at'][:16]} {'dry ' if r['dry_run'] else 'LIVE'} "
                      f"{r['outcome']:<14} {r['title']} @ {r['company']}  "
                      f"{r.get('verification_confidence') or ''}  ${r.get('cost_usd') or 0:.3f}")


@apply_app.command("resume")
def apply_resume() -> None:
    """Clear an auto-pause (after checking why the last attempts failed)."""
    bootstrap()
    from jobwright.users import update_user

    active = _active()
    if not active:
        console.print("[red]Use --user.[/red]")
        raise typer.Exit(code=1)
    update_user(active, apply_paused=False, apply_paused_reason="")
    console.print(f"[green]Auto-apply resumed[/green] for {active}.")


# ---------------------------------------------------------------------------
# answers
# ---------------------------------------------------------------------------


@answers_app.command("show")
def answers_show(as_json: bool = typer.Option(False, "--json")) -> None:
    """Every saved answer with its source and date."""
    bootstrap()
    from jobwright.apply.answers import SPECS, load_answers

    bank = load_answers()
    if as_json:
        console.print_json(json.dumps(bank.as_public_dict()))
        return
    for spec in SPECS:
        entry = bank.entry(spec.key)
        tag = "[magenta]attest[/magenta]" if spec.attestation else "field "
        if entry:
            console.print(f"{tag} {spec.key:<30} {entry['value']}  [dim]({entry['source']}, {entry['updated_at']})[/dim]")
        else:
            console.print(f"{tag} {spec.key:<30} [dim]-[/dim]")
    for entry in bank.data["custom"].values():
        console.print(f"custom {entry['question'][:60]:<30} {entry['value']}  [dim]({entry['source']})[/dim]")


@answers_app.command("set")
def answers_set(
    key: str = typer.Argument(..., help="Answer key (see `answers show`)."),
    value: str = typer.Argument(..., help="The answer, exactly as it should be given ('' clears it)."),
) -> None:
    """Save one answer."""
    bootstrap()
    from jobwright.apply.answers import set_answers

    try:
        set_answers({key: value}, source="cli")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Saved[/green] {key}.")


@answers_app.command("missing")
def answers_missing() -> None:
    """Answers still needed before automatic applications can run smoothly."""
    bootstrap()
    from jobwright.apply.answers import load_answers

    missing = load_answers().missing()
    if not missing:
        console.print("[green]All answers saved.[/green]")
        return
    for spec in missing:
        console.print(f"{'attestation' if spec.attestation else 'field':<12} {spec.key:<30} {spec.label}")


@answers_app.command("import-profile")
def answers_import_profile() -> None:
    """Copy phone / address / links from profile.json (never attestations)."""
    bootstrap()
    from jobwright.apply.answers import seed_from_profile

    seeded = seed_from_profile()
    console.print(f"[green]Copied[/green] {', '.join(seeded) or 'nothing new'}.")
