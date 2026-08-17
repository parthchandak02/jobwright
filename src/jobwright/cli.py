"""jobwright CLI — the main entry point."""

from __future__ import annotations

import logging
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
log = logging.getLogger(__name__)

# Valid pipeline stages (in execution order)
VALID_STAGES = ("discover", "enrich", "score", "portfolio", "tailor", "cover", "pdf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    """Common setup: load env, create dirs, init DB."""
    from jobwright.config import load_env, ensure_dirs
    from jobwright.database import init_db

    load_env()
    ensure_dirs()
    init_db()


def _resolve_user_option(user: Optional[str]) -> None:
    """Activate a registry user (sets JOBWRIGHT_DIR) before bootstrap."""
    if not user:
        return
    from jobwright.config import set_active_user

    path = set_active_user(user)
    console.print(f"[dim]Active user:[/dim] {user}  [dim]({path})[/dim]")


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
        help="Multi-profile user id (sets JOBWRIGHT_DIR to ~/.jobwright-users/<id>). "
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
        if env_user and f"/.jobwright-users/{env_user}" in env_dir.replace("\\", "/"):
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
        help="Allow live apply after CONFIRM APPLY (default: off / find-only).",
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
        "\nNext: copy resume.txt + profile.json into the data dir, "
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
        "profile.json", "resume.txt", "searches.yaml", ".env",
        "connections.csv", "target_companies.yaml", "jobwright.db",
    ):
        exists = (data_dir / fname).exists()
        mark = "[green]OK[/green]" if exists else "[dim]missing[/dim]"
        console.print(f"  {fname:24} {mark}")


@users_app.command("remove")
def users_remove(
    user_id: str = typer.Argument(...),
    delete_data: bool = typer.Option(
        False, "--delete-data",
        help="Also delete ~/.jobwright-users/<id>/ (destructive).",
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
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
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
    _bootstrap()

    from jobwright.pipeline import run_pipeline

    stage_list = stages if stages else ["all"]

    # Validate stage names
    for s in stage_list:
        if s != "all" and s not in VALID_STAGES:
            console.print(
                f"[red]Unknown stage:[/red] '{s}'. "
                f"Valid stages: {', '.join(VALID_STAGES)}, all"
            )
            raise typer.Exit(code=1)

    # Gate AI stages behind Tier 2
    llm_stages = {"score", "tailor", "cover"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
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
        stages=stage_list,
        min_score=min_score,
        dry_run=dry_run,
        stream=stream,
        workers=workers,
        validation_mode=validation,
    )

    if result.get("errors"):
        raise typer.Exit(code=1)


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
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting."),
    live: bool = typer.Option(False, "--live", help="Submit applications (overrides APPLY_DRY_RUN)."),
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

    active = get_active_user_id()
    if live and active and not is_apply_enabled(active):
        console.print(
            f"[red]Live apply disabled[/red] for user '{active}'.\n"
            f"Enable with: jobwright users set {active} --apply\n"
            "Finding + tailoring still work without apply."
        )
        raise typer.Exit(code=1)

    if agent_provider:
        os.environ["AGENT_PROVIDER"] = agent_provider

    if live:
        dry_run = False
    elif os.environ.get("APPLY_DRY_RUN", "").lower() in ("1", "true", "yes"):
        dry_run = True

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

    if config.RESUME_PATH.exists():
        results.append(("resume.txt", ok_mark, str(config.RESUME_PATH)))
    elif config.RESUME_PDF_PATH.exists():
        results.append(("resume.txt", warn_mark, "Only PDF found — plain-text needed for AI stages"))
    else:
        results.append(("resume.txt", fail_mark, "Run 'jobwright init' to add your resume"))

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
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_local = bool(os.environ.get("LLM_URL"))
    if has_gemini:
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
        results.append(("LLM API key", ok_mark, f"Gemini ({model})"))
    elif has_openai:
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        results.append(("LLM API key", ok_mark, f"OpenAI ({model})"))
    elif has_local:
        results.append(("LLM API key", ok_mark, f"Local: {os.environ.get('LLM_URL')}"))
    else:
        results.append(("LLM API key", fail_mark,
                        f"Set GEMINI_API_KEY in {config.ENV_PATH} (run 'jobwright init')"))

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


if __name__ == "__main__":
    app()
