"""Setup and health: `status`, `dashboard`, `doctor`, `preflight`."""

from __future__ import annotations

import typer
from rich.table import Table

from jobwright.cli._common import bootstrap, console


def status() -> None:
    """Show pipeline statistics from the database."""
    bootstrap()

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


def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    bootstrap()

    from jobwright.view import open_dashboard

    open_dashboard()


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
                        f"Set FIREWORKS_API_KEY in {config.global_env_path()} (the repo-root .env)"))

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


def preflight(
    fix: bool = typer.Option(False, "--fix", help="Repair what can be repaired (e.g. install Playwright Chromium)."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Pre-run checks used by the daily brief. Exit 1 if a blocking check fails."""
    bootstrap()
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
