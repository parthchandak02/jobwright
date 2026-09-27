"""jobwright CLI — the main entry point."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from jobwright import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="jobwright",
    help="AI-powered end-to-end job application pipeline.",
    no_args_is_help=True,
)
users_app = typer.Typer(help="Manage multi-profile users (local registry).")
app.add_typer(users_app, name="users")
console = Console()
# Diagnostics banner goes to stderr so it never pollutes stdout consumed by
# `--json` callers (e.g. agent CLI shims that parse stdout as JSON).
err_console = Console(stderr=True)
log = logging.getLogger(__name__)

# Valid pipeline stages (in execution order)
VALID_STAGES = ("discover", "enrich", "score", "portfolio", "tailor", "cover", "pdf", "docx", "connect")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOGGING_CONFIGURED = False


def _configure_logging() -> None:
    """Configure verbose stdout logging when JOBWRIGHT_LOG_LEVEL is set.

    This makes module-level ``log.info/debug`` from pipeline/discovery/scoring
    appear in captured output (e.g. the web run log). Invalid levels fall back
    to INFO. Runs at most once per process.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    import os
    import sys

    raw = os.environ.get("JOBWRIGHT_LOG_LEVEL", "").strip()
    if not raw:
        return
    level = getattr(logging, raw.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    _LOGGING_CONFIGURED = True


def _bootstrap() -> None:
    """Common setup: configure logging, load env, create dirs, init DB."""
    from jobwright.config import load_env, ensure_dirs
    from jobwright.database import init_db

    _configure_logging()
    load_env()
    ensure_dirs()
    init_db()


def _resolve_user_option(user: Optional[str]) -> None:
    """Activate a registry user (sets JOBWRIGHT_DIR) before bootstrap."""
    if not user:
        return
    from jobwright.config import set_active_user

    path = set_active_user(user)
    err_console.print(f"[dim]Active user:[/dim] {user}  [dim]({path})[/dim]")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show version and exit.",
        is_eager=True,
    ),
    user: Optional[str] = typer.Option(
        None,
        "--user", "-u",
        help="Multi-profile user id (sets JOBWRIGHT_DIR to users/<id>). "
             "Put --user BEFORE the subcommand. Hermes wrappers should pass --user explicitly; "
             "do not rely on a leftover JOBWRIGHT_USER env for interactive CLI.",
    ),
) -> None:
    """jobwright — AI-powered end-to-end job application pipeline."""
    if version:
        console.print(f"[bold]jobwright[/bold] {__version__}")
        raise typer.Exit()
    # Prefer explicit --user; only fall back to JOBWRIGHT_USER when set by Hermes wrappers
    # after an explicit export (scripts set both JOBWRIGHT_USER and JOBWRIGHT_DIR).
    if not user:
        import os
        # Only honor env when JOBWRIGHT_DIR already points at that user's data dir
        # (avoids accidental cross-user switches from a stale shell export).
        env_user = os.environ.get("JOBWRIGHT_USER")
        env_dir = os.environ.get("JOBWRIGHT_DIR", "")
        if env_user and f"/users/{env_user}" in env_dir.replace("\\", "/"):
            user = env_user
    _resolve_user_option(user)


# ---------------------------------------------------------------------------
# users subcommands
# ---------------------------------------------------------------------------

@users_app.command("add")
def users_add(
    user_id: str = typer.Argument(..., help="Short id (e.g. richa)."),
    name: str = typer.Option("", "--name", "-n", help="Display name."),
    whatsapp: str = typer.Option(
        "", "--whatsapp", "-w",
        help="Hermes deliver target, e.g. whatsapp:1203634...",
    ),
    apply_enabled: bool = typer.Option(
        False, "--apply/--no-apply",
        help="Enable gated live apply for this user (default: off / find-only).",
    ),
    schedule: str = typer.Option(
        "0 */3 * * 1-5", "--schedule",
        help="Cron schedule for morning prep (default: every 3h weekdays).",
    ),
    template: Optional[str] = typer.Option(
        None, "--template",
        help="Seed searches.yaml from a packaged template (e.g. nontech-bay-area).",
    ),
) -> None:
    """Register a new user and create their data directory.

    API keys are global (one .env, see `jobwright doctor`); a new user only gets
    a data dir for their profile/resume/searches.
    """
    from jobwright.users import add_user, USERS_ROOT
    from jobwright.config import CONFIG_DIR
    import shutil

    try:
        user = add_user(
            user_id=user_id,
            name=name,
            whatsapp_target=whatsapp,
            apply_enabled=apply_enabled,
            schedule=schedule,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    data_dir = user.resolve_data_dir()
    if template:
        src = CONFIG_DIR / f"searches.{template}.yaml"
        if not src.exists():
            src = CONFIG_DIR / f"{template}.yaml"
        if src.exists():
            shutil.copy2(src, data_dir / "searches.yaml")
            console.print(f"[green]Seeded searches.yaml from {src.name}[/green]")
        else:
            console.print(f"[yellow]Template not found:[/yellow] {template}")
        # Seed a starter profile when using the nontech template
        if template in ("nontech-bay-area", "richa") and not (data_dir / "profile.json").exists():
            profile_src = CONFIG_DIR / "profile.richa.example.json"
            if profile_src.exists():
                shutil.copy2(profile_src, data_dir / "profile.json")
                console.print(f"[green]Seeded profile.json from {profile_src.name}[/green]")
                console.print("[yellow]Edit profile.json: email, phone, sponsorship, etc.[/yellow]")

    console.print(f"[green]Created user[/green] {user.user_id}")
    console.print(f"  data dir:       {data_dir}")
    console.print(f"  apply_enabled:  {user.apply_enabled}")
    console.print(f"  whatsapp:       {user.whatsapp_target or '(none)'}")
    console.print(f"  registry:       {USERS_ROOT / 'users.yaml'}")
    console.print(
        "\nNext: copy resume/base.pdf + profile.json into the data dir, "
        f"or run [bold]jobwright --user {user_id} init[/bold]"
    )


@users_app.command("list")
def users_list() -> None:
    """List registered multi-profile users."""
    from jobwright.users import list_users, REGISTRY_PATH

    users = list_users()
    if not users:
        console.print(
            f"[yellow]No users registered.[/yellow]\n"
            f"Add one: jobwright users add <id>\n"
            f"Registry: {REGISTRY_PATH}"
        )
        return

    table = Table(title="jobwright Users", show_header=True, header_style="bold cyan")
    table.add_column("user_id")
    table.add_column("name")
    table.add_column("apply")
    table.add_column("whatsapp")
    table.add_column("schedule")
    table.add_column("data_dir")
    for u in users:
        table.add_row(
            u.user_id,
            u.name,
            "yes" if u.apply_enabled else "no",
            u.whatsapp_target or "-",
            u.schedule,
            str(u.resolve_data_dir()),
        )
    console.print(table)


@users_app.command("show")
def users_show(user_id: str = typer.Argument(...)) -> None:
    """Show one user's registry record and data dir contents."""
    from jobwright.users import get_user

    user = get_user(user_id)
    if user is None:
        console.print(f"[red]Unknown user:[/red] {user_id}")
        raise typer.Exit(code=1)
    data_dir = user.resolve_data_dir()
    console.print(f"[bold]{user.user_id}[/bold] ({user.name})")
    console.print(f"  apply_enabled:   {user.apply_enabled}")
    console.print(f"  whatsapp_target: {user.whatsapp_target or '-'}")
    console.print(f"  schedule:        {user.schedule}")
    console.print(f"  digest_schedule: {user.digest_schedule}")
    console.print(f"  data_dir:        {data_dir}")
    for fname in (
        "profile.json", "resume/base.pdf", "searches.yaml",
        "connections.csv", "target_companies.yaml",
        "jobwright.db",
    ):
        exists = (data_dir / fname).exists()
        mark = "[green]OK[/green]" if exists else "[dim]missing[/dim]"
        console.print(f"  {fname:24} {mark}")
    examples_dir = data_dir / "cover-letter" / "examples"
    ex_count = len(list(examples_dir.glob("*.pdf"))) if examples_dir.is_dir() else 0
    console.print(f"  cover-letter/examples   {ex_count} file(s)")


@users_app.command("remove")
def users_remove(
    user_id: str = typer.Argument(...),
    delete_data: bool = typer.Option(
        False, "--delete-data",
        help="Also delete users/<id>/ data directory (destructive).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove a user from the registry (optionally delete their data dir)."""
    from jobwright.users import remove_user, get_user

    user = get_user(user_id)
    if user is None:
        console.print(f"[red]Unknown user:[/red] {user_id}")
        raise typer.Exit(code=1)
    if delete_data and not yes:
        confirm = typer.confirm(
            f"Delete data dir {user.resolve_data_dir()} permanently?"
        )
        if not confirm:
            console.print("Aborted.")
            raise typer.Exit()
    remove_user(user_id, delete_data=delete_data)
    console.print(f"[green]Removed user[/green] {user_id}")


@users_app.command("set")
def users_set(
    user_id: str = typer.Argument(...),
    apply_enabled: Optional[bool] = typer.Option(
        None, "--apply/--no-apply", help="Toggle live apply.",
    ),
    whatsapp: Optional[str] = typer.Option(None, "--whatsapp", "-w"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    schedule: Optional[str] = typer.Option(None, "--schedule"),
    human_gate: bool | None = typer.Option(
        None, "--human-gate/--no-human-gate",
        help="Human gate: stop the daily brief before material generation.",
    ),
    brief_top_n: int | None = typer.Option(
        None, "--brief-top-n",
        help="Per-brief notify cap (top N by fit score; 0 = uncapped).",
    ),
) -> None:
    """Update fields on an existing user."""
    from jobwright.users import update_user

    fields: dict = {}
    if apply_enabled is not None:
        fields["apply_enabled"] = apply_enabled
    if whatsapp is not None:
        fields["whatsapp_target"] = whatsapp
    if name is not None:
        fields["name"] = name
    if schedule is not None:
        fields["schedule"] = schedule
    if human_gate is not None:
        fields["human_gate"] = human_gate
    if brief_top_n is not None:
        fields["brief_top_n"] = brief_top_n
    if not fields:
        console.print("[yellow]No fields to update.[/yellow]")
        raise typer.Exit(code=1)
    try:
        user = update_user(user_id, **fields)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Updated[/green] {user.user_id}: {fields}")


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    _bootstrap()
    from jobwright.wizard.init import run_wizard

    run_wizard()


@app.command()
def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=(
            "Pipeline stages to run. "
            f"Valid: {', '.join(VALID_STAGES)}, all. "
            "Defaults to 'all' if omitted."
        ),
    ),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Force JOBWRIGHT_LOG_LEVEL=DEBUG for maximum backend log detail.",
    ),
    validation: str = typer.Option(
        "normal",
        "--validation",
        help=(
            "Validation strictness for tailor/cover stages. "
            "strict: banned words = errors, judge must pass. "
            "normal: banned words = warnings only (default, recommended for Gemini free tier). "
            "lenient: banned words ignored, LLM judge skipped (fastest, fewest API calls)."
        ),
    ),
) -> None:
    """Run pipeline stages: discover, enrich, score, tailor, cover, pdf."""
    if verbose:
        import os
        os.environ["JOBWRIGHT_LOG_LEVEL"] = "DEBUG"
    _bootstrap()

    from jobwright.pipeline import run_pipeline

    # When no stages are given, let the pipeline resolve the default brief
    # stage list (which honors the user's human_gate config key). Explicit
    # stage lists always run verbatim — on-demand `run tailor cover docx`
    # still generates materials for an approved job.
    explicit = list(stages) if stages else None

    # Validate stage names
    if explicit:
        for s in explicit:
            if s != "all" and s not in VALID_STAGES:
                console.print(
                    f"[red]Unknown stage:[/red] '{s}'. "
                    f"Valid stages: {', '.join(VALID_STAGES)}, all"
                )
                raise typer.Exit(code=1)

    # Gate AI stages behind Tier 2 (default briefs include scoring either way).
    llm_stages = {"score", "tailor", "cover"}
    runs_llm = explicit is None or "all" in explicit or any(s in llm_stages for s in explicit)
    if runs_llm:
        from jobwright.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    # Validate the --validation flag value
    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(
            f"[red]Invalid --validation value:[/red] '{validation}'. "
            f"Choose from: {', '.join(valid_modes)}"
        )
        raise typer.Exit(code=1)

    result = run_pipeline(
        stages=explicit,
        min_score=min_score,
        dry_run=dry_run,
        workers=workers,
        validation_mode=validation,
    )

    if result.get("errors"):
        raise typer.Exit(code=1)


@app.command("tailor-job")
def tailor_job(
    url: str = typer.Option(..., "--url", help="Job URL to tailor resume and cover letter for."),
    verbose: bool = typer.Option(True, "--verbose", "-v", help="DEBUG logs to stdout."),
    validation: str = typer.Option("lenient", "--validation"),
    resume_instructions_file: Optional[str] = typer.Option(
        None, "--resume-instructions-file", help="Override resume tailor instructions (text file).",
    ),
    cover_instructions_file: Optional[str] = typer.Option(
        None, "--cover-instructions-file", help="Override cover letter instructions (text file).",
    ),
    resume_only: bool = typer.Option(
        False, "--resume-only", help="Tailor resume and export DOCX only.",
    ),
    cover_only: bool = typer.Option(
        False, "--cover-only", help="Generate cover letter and export DOCX only.",
    ),
) -> None:
    """Tailor resume + cover letter for one job (dashboard / verbose logs)."""
    import os
    from pathlib import Path

    if resume_only and cover_only:
        raise typer.BadParameter("Use only one of --resume-only or --cover-only.")
    if verbose:
        os.environ["JOBWRIGHT_LOG_LEVEL"] = "DEBUG"
    _bootstrap()
    from jobwright.config import check_tier

    check_tier(2, "AI scoring/tailoring")
    from jobwright.scoring.tailor import (
        run_single_job_cover,
        run_single_job_materials,
        run_single_job_resume,
    )

    def _read_opt(path: str | None) -> str | None:
        if not path:
            return None
        p = Path(path)
        if not p.is_file():
            raise typer.BadParameter(f"Instructions file not found: {path}")
        return p.read_text(encoding="utf-8")

    resume_instr = _read_opt(resume_instructions_file)
    cover_instr = _read_opt(cover_instructions_file)
    if resume_only:
        rc = run_single_job_resume(url, validation_mode=validation, resume_instructions=resume_instr)
    elif cover_only:
        rc = run_single_job_cover(url, validation_mode=validation, cover_instructions=cover_instr)
    else:
        rc = run_single_job_materials(
            url,
            validation_mode=validation,
            resume_instructions=resume_instr,
            cover_instructions=cover_instr,
        )
    raise typer.Exit(code=rc)


@app.command()
def apply(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications to submit."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel browser workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for job selection."),
    model: str = typer.Option("composer-2.5", "--model", "-m", help="Agent model name."),
    agent_provider: str = typer.Option(
        None, "--agent-provider",
        help="Stage-6 agent: cursor-sdk (default), cursor-cli, claude.",
    ),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever, polling for new jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting (the default)."),
    live: bool = typer.Option(False, "--live", help="Actually submit applications (requires apply_enabled)."),
    headless: bool = typer.Option(False, "--headless", help="Run browsers in headless mode."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file for manual debugging instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed (provide URL)."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
) -> None:
    """Launch auto-apply to submit job applications."""
    _bootstrap()

    import os
    from jobwright.config import get_active_user_id
    from jobwright.users import is_apply_enabled

    if live and dry_run:
        console.print("[red]--live and --dry-run are mutually exclusive.[/red]")
        raise typer.Exit(code=2)
    # Dry-run unless the caller explicitly asked for --live. Never infer live.
    dry_run = not live

    active = get_active_user_id()
    if live and not is_apply_enabled(active):
        console.print(
            f"[red]Live apply disabled[/red] for user '{active}'.\n"
            f"Enable with: jobwright users set {active} --apply\n"
            "Finding + tailoring still work without apply."
        )
        raise typer.Exit(code=1)

    if agent_provider:
        os.environ["AGENT_PROVIDER"] = agent_provider

    import jobwright.config as config
    from jobwright.config import check_tier, get_agent_provider
    from jobwright.database import get_connection

    # --- Utility modes (no Chrome/Claude needed) ---

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
        count = do_reset()
        console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")
        return

    # --- Full apply mode ---

    # Check 1: Tier 3 required (agent + Chrome)
    check_tier(3, "auto-apply")

    # Check 2: Profile exists
    if not config.PROFILE_PATH.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]jobwright init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    # Check 3: Tailored resumes exist (skip for --gen with --url)
    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]jobwright run score tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)

    if gen:
        from jobwright.apply.launcher import gen_prompt
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = config.PROFILE_PATH.parent / ".mcp-apply-0.json"
        provider = get_agent_provider()
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print(f"\n[bold]Run manually ({provider}):[/bold]")
        if provider == "cursor-cli":
            console.print(
                f"  agent -p --trust --force --approve-mcps --workspace {config.APPLY_WORKER_DIR}/0 "
                f"$(cat {prompt_file})"
            )
        elif provider == "claude":
            console.print(
                f"  claude --model {model} -p "
                f"--mcp-config {mcp_path} "
                f"--permission-mode bypassPermissions < {prompt_file}"
            )
        else:
            console.print(f"  AGENT_PROVIDER=cursor-sdk jobwright apply --url {target}")
        return

    from jobwright.apply.launcher import main as apply_main

    effective_limit = limit if limit is not None else (0 if continuous else 1)

    console.print("\n[bold blue]Launching Auto-Apply[/bold blue]")
    console.print(f"  Limit:    {'unlimited' if continuous else effective_limit}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Provider: {get_agent_provider()}")
    console.print(f"  Model:    {model}")
    console.print(f"  Headless: {headless}")
    console.print(f"  Dry run:  {dry_run}")
    if url:
        console.print(f"  Target:   {url}")
    console.print()

    apply_main(
        limit=effective_limit,
        target_url=url,
        min_score=min_score,
        headless=headless,
        model=model,
        dry_run=dry_run,
        continuous=continuous,
        workers=workers,
    )


@app.command()
def status() -> None:
    """Show pipeline statistics from the database."""
    _bootstrap()

    from jobwright.database import get_stats

    stats = get_stats()

    console.print("\n[bold]jobwright Pipeline Status[/bold]\n")

    # Summary table
    summary = Table(title="Pipeline Overview", show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Count", justify="right")

    summary.add_row("Total jobs discovered", str(stats["total"]))
    summary.add_row("With full description", str(stats["with_description"]))
    summary.add_row("Pending enrichment", str(stats["pending_detail"]))
    summary.add_row("Enrichment errors", str(stats["detail_errors"]))
    summary.add_row("Scored by LLM", str(stats["scored"]))
    summary.add_row("Pending scoring", str(stats["unscored"]))
    summary.add_row("Tailored resumes", str(stats["tailored"]))
    summary.add_row("Pending tailoring (7+)", str(stats["untailored_eligible"]))
    summary.add_row("Cover letters", str(stats["with_cover_letter"]))
    summary.add_row("Ready to apply", str(stats["ready_to_apply"]))
    summary.add_row("Applied", str(stats["applied"]))
    summary.add_row("Apply errors", str(stats["apply_errors"]))

    console.print(summary)

    # Score distribution
    if stats["score_distribution"]:
        dist_table = Table(title="\nScore Distribution", show_header=True, header_style="bold yellow")
        dist_table.add_column("Score", justify="center")
        dist_table.add_column("Count", justify="right")
        dist_table.add_column("Bar")

        max_count = max(count for _, count in stats["score_distribution"]) or 1
        for score, count in stats["score_distribution"]:
            bar_len = int(count / max_count * 30)
            if score >= 7:
                color = "green"
            elif score >= 5:
                color = "yellow"
            else:
                color = "red"
            bar = f"[{color}]{'=' * bar_len}[/{color}]"
            dist_table.add_row(str(score), str(count), bar)

        console.print(dist_table)

    # By site
    if stats["by_site"]:
        site_table = Table(title="\nJobs by Source", show_header=True, header_style="bold magenta")
        site_table.add_column("Site")
        site_table.add_column("Count", justify="right")

        for site, count in stats["by_site"]:
            site_table.add_row(site or "Unknown", str(count))

        console.print(site_table)

    console.print()


@app.command()
def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    _bootstrap()

    from jobwright.view import open_dashboard

    open_dashboard()


@app.command()
def doctor() -> None:
    """Check your setup and diagnose missing requirements."""
    import shutil
    import jobwright.config as config
    from jobwright.config import load_env, get_chrome_path

    load_env()

    ok_mark = "[green]OK[/green]"
    fail_mark = "[red]MISSING[/red]"
    warn_mark = "[yellow]WARN[/yellow]"

    results: list[tuple[str, str, str]] = []  # (check, status, note)

    # Active user / data dir
    from jobwright.config import get_active_user_id
    active = get_active_user_id()
    results.append((
        "data dir",
        ok_mark,
        f"{config.APP_DIR}" + (f" (user={active})" if active else " (legacy single-user)"),
    ))

    # --- Tier 1 checks ---
    if config.PROFILE_PATH.exists():
        results.append(("profile.json", ok_mark, str(config.PROFILE_PATH)))
    else:
        results.append(("profile.json", fail_mark, "Run 'jobwright init' to create"))

    if config.RESUME_PDF_PATH.exists():
        results.append(("resume.pdf", ok_mark, str(config.RESUME_PDF_PATH)))
    else:
        results.append(("resume.pdf", fail_mark, "Run 'jobwright init' to add resume/base.pdf"))

    if config.SEARCH_CONFIG_PATH.exists():
        results.append(("searches.yaml", ok_mark, str(config.SEARCH_CONFIG_PATH)))
    else:
        results.append(("searches.yaml", warn_mark, "Will use example config — run 'jobwright init'"))

    try:
        import jobspy  # noqa: F401
        results.append(("python-jobspy", ok_mark, "Job board scraping available"))
    except ImportError:
        results.append(("python-jobspy", warn_mark,
                        "pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex"))

    # --- Tier 2 checks ---
    import os
    has_fireworks = bool(os.environ.get("FIREWORKS_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_local = bool(os.environ.get("LLM_URL"))
    if has_fireworks:
        from jobwright.llm import _resolve_fireworks_model

        model = _resolve_fireworks_model(os.environ.get("LLM_MODEL", ""))
        results.append(("LLM API key", ok_mark, f"Fireworks ({model})"))
        if not has_gemini:
            results.append((
                "Gemini failover",
                warn_mark,
                "GEMINI_API_KEY unset — Fireworks empty responses will not fail over",
            ))
        else:
            fb = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.7-flash")
            level = os.environ.get("GEMINI_THINKING_LEVEL", "low")
            results.append(("Gemini failover", ok_mark, f"{fb} (thinking={level})"))
    elif has_gemini:
        model = os.environ.get("LLM_MODEL", "gemini-3.7-flash")
        results.append(("LLM API key", ok_mark, f"Gemini ({model})"))
    elif has_openai:
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        results.append(("LLM API key", ok_mark, f"OpenAI ({model})"))
        if not has_gemini:
            results.append((
                "Gemini failover",
                warn_mark,
                "GEMINI_API_KEY unset — empty responses will not fail over to Gemini",
            ))
    elif has_local:
        results.append(("LLM API key", ok_mark, f"Local: {os.environ.get('LLM_URL')}"))
    else:
        results.append(("LLM API key", fail_mark,
                        f"Set FIREWORKS_API_KEY in {config.ENV_PATH} (run 'jobwright init')"))

    # Explicit gemini-* model without GEMINI_API_KEY is a misconfiguration.
    llm_model = os.environ.get("LLM_MODEL", "")
    if llm_model.startswith("gemini-") and not has_gemini:
        results.append((
            "Gemini model vs key",
            fail_mark,
            f"LLM_MODEL={llm_model} but GEMINI_API_KEY is unset",
        ))

    # --- Tier 3 checks ---
    from jobwright.config import get_agent_provider, has_apply_agent

    provider = get_agent_provider()
    if provider == "cursor-sdk":
        cursor_key = os.environ.get("CURSOR_API_KEY")
        if cursor_key:
            results.append(("CURSOR_API_KEY", ok_mark, f"cursor-sdk ({os.environ.get('APPLY_AGENT_MODEL', 'composer-2.5')})"))
        else:
            results.append(("CURSOR_API_KEY", fail_mark,
                            f"Set in {config.ENV_PATH} (Cursor Dashboard → Integrations)"))
        try:
            import cursor_sdk  # noqa: F401
            results.append(("cursor-sdk package", ok_mark, "pip install cursor-sdk"))
        except ImportError:
            results.append(("cursor-sdk package", fail_mark, "pip install cursor-sdk"))
    elif provider == "cursor-cli":
        agent_bin = shutil.which("agent")
        if agent_bin:
            results.append(("Cursor Agent CLI", ok_mark, agent_bin))
        else:
            results.append(("Cursor Agent CLI", fail_mark,
                            "curl https://cursor.com/install -fsSL | bash"))
    else:
        claude_bin = shutil.which("claude")
        if claude_bin:
            results.append(("Claude Code CLI", ok_mark, claude_bin))
        else:
            results.append(("Claude Code CLI", fail_mark,
                            "Install from https://claude.ai/code"))

    results.append(("AGENT_PROVIDER", ok_mark if has_apply_agent() else fail_mark, provider))

    try:
        chrome_path = get_chrome_path()
        results.append(("Chrome/Chromium", ok_mark, chrome_path))
    except FileNotFoundError:
        results.append(("Chrome/Chromium", fail_mark,
                        "Install Chrome or set CHROME_PATH env var (needed for auto-apply)"))

    npx_bin = shutil.which("npx")
    if npx_bin:
        results.append(("Node.js (npx)", ok_mark, npx_bin))
    else:
        results.append(("Node.js (npx)", fail_mark,
                        "Install Node.js 18+ from nodejs.org (needed for auto-apply)"))

    capsolver = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver:
        results.append(("CapSolver API key", ok_mark, "CAPTCHA solving enabled"))
    else:
        results.append(("CapSolver API key", "[dim]optional[/dim]",
                        "Set CAPSOLVER_API_KEY in .env for CAPTCHA solving"))

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        results.append(("Playwright browsers", ok_mark, "chromium headless launch OK"))
    except ImportError:
        results.append(("Playwright browsers", warn_mark,
                        "pip install playwright && playwright install chromium"))
    except Exception as e:
        err = str(e).split("\n")[0][:80]
        results.append(("Playwright browsers", fail_mark,
                        f"Run: playwright install chromium ({err})"))

    console.print()
    console.print("[bold]jobwright Doctor[/bold]\n")

    col_w = max(len(r[0]) for r in results) + 2
    for check, status, note in results:
        pad = " " * (col_w - len(check))
        console.print(f"  {check}{pad}{status}  [dim]{note}[/dim]")

    console.print()

    from jobwright.config import get_tier, TIER_LABELS
    tier = get_tier()
    console.print(f"[bold]Current tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]")

    if tier == 1:
        console.print("[dim]  → Tier 2 unlocks: scoring, tailoring, cover letters (needs LLM API key)[/dim]")
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs CURSOR_API_KEY or agent CLI + Chrome + Node.js)[/dim]")
    elif tier == 2:
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs CURSOR_API_KEY or agent CLI + Chrome + Node.js)[/dim]")

    console.print()


@app.command()
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
    _bootstrap()
    from jobwright.notify import run_notify

    def _status(line: str) -> None:
        if status_file:
            with open(status_file, "a", encoding="utf-8") as fh:
                fh.write(line.replace("\n", " ")[:300] + "\n")

    try:
        result = run_notify(dry_run=dry_run)
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
        _status(f"notify_sent {result['sent']}")

    if result.get("dry_run"):
        console.print(f"[bold]Preview[/bold] ({len(result['jobs'])} job(s)):\n")
        console.print(result["message"])
        return

    console.print(f"[green]Sent {result['sent']} job(s) to WhatsApp.[/green]")
    for j in result["jobs"]:
        console.print(f"  {j['title']} @ {j.get('company') or '?'}  [dim]{j['job_id']}[/dim]")


@app.command()
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


@app.command("briefstats")
def briefstats_cmd(
    days: int = typer.Option(14, "--days", help="Number of days of brief history to report."),
) -> None:
    """Per-brief scoreboard: precision proxy (advanced / shown) over recent briefs."""
    from jobwright.briefstats import briefstats as compute_briefstats
    from jobwright.config import get_active_user_id

    _bootstrap()
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


@app.command()
def network(
    top: int = typer.Option(25, "--top", "-n", help="How many contacts to keep."),
    csv: Optional[str] = typer.Option(
        None, "--csv",
        help="Path to LinkedIn Connections.csv (default: <data_dir>/connections.csv).",
    ),
) -> None:
    """Rank LinkedIn 1st-degree contacts from an exported Connections.csv (no scraping)."""
    _bootstrap()
    from jobwright.config import check_tier
    from pathlib import Path

    check_tier(2, "network ranking")
    from jobwright.network.rank import run_network_rank

    try:
        result = run_network_rank(
            top_n=top,
            csv_path=Path(csv) if csv else None,
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print(result["digest"])
    console.print(
        f"\n[dim]Saved {result['ranked']}/{result['contacts']} → "
        f"{result['txt_path']}[/dim]"
    )


@app.command()
def targets(
    limit: int = typer.Option(30, "--limit", "-n", help="Max companies to generate."),
    merge: bool = typer.Option(
        False, "--merge-searches",
        help="Also write company names into searches.yaml target_companies.",
    ),
) -> None:
    """Build a ranked target-company list from the active profile (LLM)."""
    _bootstrap()
    from jobwright.config import check_tier

    check_tier(2, "target company list")
    from jobwright.targets.build import run_targets

    result = run_targets(limit=limit, merge_into_searches=merge)
    console.print(result["digest"])
    console.print(
        f"\n[dim]Saved {result['count']} companies → {result['yaml_path']}[/dim]"
    )



# ---------------------------------------------------------------------------
# Scoring quality: eval, rescore, criteria, labels
# ---------------------------------------------------------------------------

criteria_app = typer.Typer(help="Match criteria (what makes a posting worth your time).")
app.add_typer(criteria_app, name="criteria")
labels_app = typer.Typer(help="Human relevance labels (every rescore is kept).")
app.add_typer(labels_app, name="labels")


def _load_profile_or_none() -> Optional[dict]:
    from jobwright.config import load_profile

    try:
        return load_profile()
    except FileNotFoundError:
        return None


@app.command("eval")
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
    _bootstrap()
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


@app.command()
def rescore(
    scope: str = typer.Option(
        "active", "--scope",
        help="active (backlog+prepare), labeled, all, or since:<days> (discovered within N days).",
    ),
    limit: int = typer.Option(0, "--limit"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show how many jobs would be rescored."),
) -> None:
    """Re-run the current scorer on existing jobs; every new score is kept in score_history."""
    _bootstrap()
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
    _bootstrap()
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
    _bootstrap()
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
    _bootstrap()
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
    _bootstrap()
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


@app.command()
def dedupe(
    apply_changes: bool = typer.Option(
        False, "--apply", help="Close duplicates and tombstone their URLs (default: preview only).",
    ),
    dry_run: bool = typer.Option(True, "--dry-run", help="Preview duplicate groups (the default)."),
) -> None:
    """Find duplicate open jobs; keep the best card per group, close the rest as duplicates."""
    _bootstrap()
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


@app.command()
def preflight(
    fix: bool = typer.Option(False, "--fix", help="Repair what can be repaired (e.g. install Playwright Chromium)."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Pre-run checks used by the daily brief. Exit 1 if a blocking check fails."""
    _bootstrap()
    import json as _json

    from jobwright.preflight import blocking_failures, run_checks

    checks = run_checks(fix=fix)
    if as_json:
        print(_json.dumps([c.as_dict() for c in checks]))
    else:
        for c in checks:
            mark = "[green]OK[/green]" if c.ok else ("[red]FAIL[/red]" if c.blocking else "[yellow]WARN[/yellow]")
            console.print(f"  {c.name:<16} {mark}  [dim]{c.detail}[/dim]")
    if blocking_failures(checks):
        raise typer.Exit(code=1)


ops_app = typer.Typer(help="Operator health: brief reports, watchdog, alert target.")
app.add_typer(ops_app, name="ops")


@ops_app.command("brief-report")
def ops_brief_report(
    status_file: Optional[str] = typer.Option(None, "--status-file"),
    force: bool = typer.Option(False, "--force", help="Send even when everything is OK."),
) -> None:
    """Summarize today's brief for this user; alert the operator if anything is wrong."""
    _bootstrap()
    from pathlib import Path as _Path

    from jobwright.ops import build_brief_report, deliver, write_health

    rep = build_brief_report(_Path(status_file) if status_file else None)
    write_health(rep)
    console.print(rep.text())
    console.print(f"[dim]{deliver(rep, force=force)}[/dim]")


@ops_app.command("watchdog")
def ops_watchdog(grace: int = typer.Option(120, "--grace", help="Minutes after the scheduled time.")) -> None:
    """Alert for any user whose brief never started or never finished today."""
    _configure_logging()
    from jobwright.config import load_env
    from jobwright.ops import deliver, watchdog

    load_env()
    reports = watchdog(grace_minutes=grace)
    if not reports:
        console.print("All briefs accounted for.")
    for rep in reports:
        console.print(rep.text())
        console.print(f"[dim]{deliver(rep)}[/dim]")


@ops_app.command("set-target")
def ops_set_target(target: str = typer.Argument(..., help="whatsapp:<jid> for operator alerts ('' to clear).")) -> None:
    """Where operator alerts go (usually the admin's own WhatsApp)."""
    from jobwright.ops import set_ops_target

    console.print(f"ops_target = {set_ops_target(target) or '(cleared)'}")


@ops_app.command("backup")
def ops_backup(
    dest: Optional[str] = typer.Option(None, "--dest", help="Backup root (default JOBWRIGHT_BACKUP_DIR or ~/jobwright-backups)."),
    keep: int = typer.Option(14, "--keep", help="Days of snapshots to keep."),
) -> None:
    """Snapshot every profile (consistent DB copies + hard-linked files); alert on errors."""
    _configure_logging()
    from pathlib import Path as _Path

    from jobwright.config import load_env
    from jobwright.ops import Report, backup_users, deliver

    load_env()
    rep = backup_users(_Path(dest) if dest else None, keep_days=keep)
    console.print(f"Snapshot: {rep['snapshot']}  users: {rep['users']}")
    if rep["errors"]:
        for e in rep["errors"]:
            console.print(f"[red]{e}[/red]")
        console.print(deliver(Report("backup", "fail", rep["errors"][:5])))
        raise typer.Exit(code=1)


@ops_app.command("install-crons")
def ops_install_crons(
    backup_dest: Optional[str] = typer.Option(None, "--backup-dest", help="Backup root for the nightly backup cron."),
    skip_ops: bool = typer.Option(False, "--skip-ops", help="Only the per-user brief crons."),
) -> None:
    """Create or update every jobwright Hermes cron: briefs, watchdog, backup, weekly summary."""
    import os as _os

    from jobwright.config import load_env
    from jobwright.hermes_cron import (
        BACKUP_CRON_NAME,
        WATCHDOG_CRON_NAME,
        WEEKLY_SUMMARY_CRON_NAME,
        ensure_backup_cron,
        ensure_brief_cron,
        ensure_watchdog_cron,
        ensure_weekly_summary_cron,
    )
    from jobwright.users import list_users

    load_env()
    from jobwright.onboarding import is_set_up

    results = []
    for u in list_users():
        if not is_set_up(u.user_id):
            console.print(f"[dim]skip  jobwright-brief-{u.user_id}  (setup not finished)[/dim]")
            continue
        results.append((f"jobwright-brief-{u.user_id}", ensure_brief_cron(u.user_id, u.schedule or "0 6 * * *")))
    if not skip_ops:
        results.append((WATCHDOG_CRON_NAME, ensure_watchdog_cron()))
        dest = backup_dest or _os.environ.get("JOBWRIGHT_BACKUP_DIR", "")
        results.append((BACKUP_CRON_NAME, ensure_backup_cron(dest=dest)))
        results.append((WEEKLY_SUMMARY_CRON_NAME, ensure_weekly_summary_cron()))
    failed = False
    for name, r in results:
        ok = bool(r.get("ok"))
        failed = failed or not ok
        console.print(f"{'[green]ok[/green]' if ok else '[red]FAIL[/red]'}  {name}  {r.get('error') or ''}")
    if failed:
        raise typer.Exit(code=1)


access_app = typer.Typer(help="Cloudflare Access allowlist (policy 'jobwright users') kept in sync with users.yaml.")
app.add_typer(access_app, name="access")


def _print_access_plan(plan: dict) -> None:
    app_info = plan.get("app") or {}
    console.print(f"App: {app_info.get('name')} ({app_info.get('domain')})")
    managed = plan.get("managed_policy") or {}
    console.print(f"Policy '{managed.get('name')}': {'exists' if managed.get('exists') else 'missing (created on sync)'}")
    console.print(f"Current: {', '.join(plan['current']) or '(none)'}")
    console.print(f"Desired: {', '.join(plan['desired']) or '(none)'}")
    for e in plan["add"]:
        console.print(f"[green]+ {e}[/green]")
    for e in plan["remove"]:
        console.print(f"[red]- {e}[/red]")
    if plan.get("other_policies_emails"):
        console.print(f"Also allowed by other policies (not managed): {', '.join(plan['other_policies_emails'])}")
    console.print("[green]In sync[/green]" if plan.get("in_sync") else "[yellow]Out of sync[/yellow]")


def _access_call(fn):
    from jobwright.cf_access import CFAccessError
    from jobwright.config import load_env

    load_env()
    try:
        return fn()
    except CFAccessError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@access_app.command("status")
def access_status() -> None:
    """Show the Access allowlist diff (users.yaml emails + admins vs the managed policy)."""
    from jobwright.cf_access import plan_sync

    _print_access_plan(_access_call(plan_sync))


@access_app.command("sync")
def access_sync(yes: bool = typer.Option(False, "--yes", help="Apply the change (default: dry-run diff).")) -> None:
    """Set the 'jobwright users' allow policy to exactly the users.yaml emails + admins."""
    from jobwright.cf_access import apply_sync, plan_sync

    if not yes:
        _print_access_plan(_access_call(plan_sync))
        console.print("Dry run. Re-run with --yes to apply.")
        return
    plan = _access_call(apply_sync)
    _print_access_plan(plan)
    console.print("Created policy." if plan.get("created") else ("Updated policy." if plan.get("applied") else "No change."))


hermes_app = typer.Typer(help="Hermes gateway config generated from users.yaml.")
app.add_typer(hermes_app, name="hermes")


@hermes_app.command("channels")
def hermes_channels_cmd(
    apply_changes: bool = typer.Option(False, "--apply", help="Write the changes (backup first)."),
    prune: bool = typer.Option(False, "--prune", help="Also remove managed entries whose group no longer belongs to a profile."),
    config_path: Optional[str] = typer.Option(None, "--config", help="Hermes config (default $HERMES_CONFIG or ~/.hermes/config.yaml)."),
) -> None:
    """Per-profile WhatsApp group instructions in the Hermes config: show the diff, optionally apply."""
    from jobwright import hermes_channels
    from jobwright.hermes_cron import hermes_dry_run

    try:
        result = hermes_channels.apply(config_path, prune=prune) if apply_changes else \
            hermes_channels.plan(config_path, prune=prune).as_dict()
    except (OSError, ValueError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    for e in result["entries"]:
        console.print(f"{e['status']:<9}  {e['user_id']}  {e['jid']}  {','.join(e['changes'])}")
    for s in result["skipped"]:
        console.print(f"[dim]skipped    {s['user_id']}  {s['reason']}[/dim]")
    for jid in result["orphans"]:
        console.print(f"[yellow]orphan     {jid}  (managed entry with no profile; --prune removes it)[/yellow]")
    if result["diff"]:
        console.print(result["diff"], markup=False, highlight=False, soft_wrap=True)
    if not result["changed"]:
        console.print("Hermes config is up to date.")
    elif not apply_changes:
        console.print("Re-run with --apply to write, then `hermes gateway restart`.")
    elif result.get("written"):
        console.print(f"Written. Backup: {result['backup']}\nRun `hermes gateway restart` to apply it.")
    elif hermes_dry_run():
        console.print("JOBWRIGHT_HERMES_DRY_RUN is set: nothing written.")


# Keep last: every command above must be registered before the app runs.
if __name__ == "__main__":
    app()
