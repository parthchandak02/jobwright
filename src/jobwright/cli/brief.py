"""Daily brief and its follow-ups: `notify`, `summary`, `briefstats`, `dedupe`."""

from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from jobwright.cli._common import _configure_logging, bootstrap, console


def notify(
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Build and preview the message without sending or marking jobs.",
    ),
    status_file: Optional[str] = typer.Option(
        None, "--status-file",
        help="Append 'notify_sent N' / 'notify_skipped <reason>' / 'notify_failed <error>' to this file.",
    ),
) -> None:
    """Send a WhatsApp digest of newly prepared jobs (deduped one-shot per job)."""
    bootstrap()
    from jobwright.notify import SendUncertain, run_notify

    def _status(line: str) -> None:
        if status_file:
            with open(status_file, "a", encoding="utf-8") as fh:
                fh.write(line.replace("\n", " ")[:300] + "\n")

    try:
        result = run_notify(dry_run=dry_run)
    except SendUncertain as e:
        # May have been delivered: jobs stay marked (never resent automatically).
        console.print(f"[yellow]Delivery uncertain:[/yellow] {e}")
        _status(f"notify_uncertain {e}")
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        _status(f"notify_failed {e}")
        raise typer.Exit(code=1)
    except RuntimeError as e:
        console.print(f"[red]Delivery failed:[/red] {e}")
        _status(f"notify_failed {e}")
        raise typer.Exit(code=1)

    if result.get("skipped"):
        console.print(f"[yellow]Nothing to send:[/yellow] {result.get('reason', 'no new jobs')}")
        _status(f"notify_skipped {result.get('reason', 'no new jobs')}")
        return
    if not result.get("dry_run"):
        paused_note = f" (search paused; {result.get('followups', 0)} follow-ups)" if result.get("paused") else ""
        _status(f"notify_sent {result['sent']}{paused_note}")

    if result.get("dry_run"):
        console.print(f"[bold]Preview[/bold] ({len(result['jobs'])} job(s)):\n")
        console.print(result["message"])
        return

    if result.get("paused"):
        console.print(f"[green]Search paused: sent {result.get('followups', 0)} follow-up reminder(s).[/green]")
        return
    console.print(f"[green]Sent {result['sent']} job(s) to WhatsApp.[/green]")
    for j in result["jobs"]:
        console.print(f"  {j['title']} @ {j.get('company') or '?'}  [dim]{j['job_id']}[/dim]")


def summary(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview each message without sending."),
    days: int = typer.Option(7, "--days", help="How many days the summary covers."),
    force: bool = typer.Option(False, "--force", help="Send even if a summary went out recently."),
) -> None:
    """Weekly WhatsApp summary: every profile, or only the --user one."""
    _configure_logging()
    from jobwright.config import get_active_user_id, load_env
    from jobwright.summary import run_summary_all

    load_env()
    active = get_active_user_id()
    results = run_summary_all([active] if active else None, dry_run=dry_run, days=days, force=force)
    failed = False
    for r in results:
        if r.get("error"):
            failed = True
            console.print(f"[red]{r['user']}: failed[/red] {r['error']}")
        elif r.get("skipped"):
            console.print(f"[yellow]{r['user']}: skipped[/yellow] {r.get('reason', '')}")
        elif r.get("dry_run"):
            console.print(f"[bold]{r['user']}[/bold] (preview)\n{r['message']}\n")
        else:
            console.print(f"[green]{r['user']}: sent[/green]")
    if failed:
        if not dry_run:
            from jobwright.ops import Report, deliver

            errors = [f"{r['user']}: {r['error']}" for r in results if r.get("error")]
            console.print(deliver(Report("weekly-summary", "fail", errors[:5])))
        raise typer.Exit(code=1)


def briefstats_cmd(
    days: int = typer.Option(14, "--days", help="Number of days of brief history to report."),
) -> None:
    """Per-brief scoreboard: precision proxy (advanced / shown) over recent briefs."""
    from jobwright.briefstats import briefstats as compute_briefstats
    from jobwright.config import get_active_user_id

    bootstrap()
    active = get_active_user_id()
    if not active:
        console.print("[red]No active user.[/red] Set one with: jobwright --user <id> briefstats")
        raise typer.Exit(code=1)

    history = compute_briefstats(user=active, days=days)
    if not history:
        console.print(f"[yellow]No brief_items recorded for the last {days} day(s).[/yellow] "
                      "Briefs are recorded when notify sends.")
        return

    table = Table(title=f"Scoreboard (last {days}d)", show_header=True, header_style="bold cyan")
    table.add_column("brief_date", style="bold")
    table.add_column("shown", justify="right")
    table.add_column("applied", justify="right")
    table.add_column("in_progress", justify="right")
    table.add_column("offer", justify="right")
    table.add_column("closed", justify="right")
    table.add_column("untouched", justify="right")
    table.add_column("precision@K", justify="right")
    for r in history:
        table.add_row(
            r["brief_date"],
            str(r["shown"]),
            str(r["applied"]),
            str(r["in_progress"]),
            str(r["offer"]),
            str(r["closed"]),
            str(r["untouched"]),
            f"{r['precision']:.3f}" if r["precision"] is not None else "-",
        )
    console.print(table)
    console.print("\n[dim]precision@K = (applied + in_progress) / shown, per brief[/dim]")


def dedupe(
    apply_changes: bool = typer.Option(
        False, "--apply", help="Close duplicates and tombstone their URLs (default: preview only).",
    ),
    dry_run: bool = typer.Option(True, "--dry-run", help="Preview duplicate groups (the default)."),
) -> None:
    """Find duplicate open jobs; keep the best card per group, close the rest as duplicates."""
    bootstrap()
    from jobwright.database import get_connection
    from jobwright.discovery.dedupe import collapse_duplicates

    out = collapse_duplicates(get_connection(), apply=apply_changes)
    for group in out["groups"]:
        keeper = group["keeper"]
        console.print(
            f"\n[bold]{keeper['title']}[/bold] @ {keeper['company'] or '?'}  "
            f"[dim]({group['match']} match, {len(group['losers']) + 1} cards)[/dim]"
        )
        console.print(
            f"  [green]keep[/green]   {keeper['job_id']}  {keeper['funnel_stage'] or 'backlog'}  "
            f"fit {keeper['fit_score'] if keeper['fit_score'] is not None else '-'}  {keeper['location'] or ''}"
        )
        for loser in group["losers"]:
            tag = f"[yellow]keep ({loser['blocked']})[/yellow]" if loser["blocked"] else "[red]close[/red]"
            console.print(
                f"  {tag}  {loser['job_id']}  {loser['funnel_stage'] or 'backlog'}  "
                f"fit {loser['fit_score'] if loser['fit_score'] is not None else '-'}  {loser['location'] or ''}"
            )
    verb = "Closed" if apply_changes else "Would close"
    console.print(
        f"\n{out['group_count']} duplicate group(s), {out['duplicates']} extra card(s). "
        f"{verb} {out['closed'] if apply_changes else out['duplicates'] - len(out['blocked'])}; "
        f"{len(out['blocked'])} left open (applied or added by hand)."
    )
    if not apply_changes:
        console.print("[dim]Preview only. Re-run with --apply to close duplicates.[/dim]")
