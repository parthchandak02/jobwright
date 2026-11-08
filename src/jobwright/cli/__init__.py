"""jobwright CLI — the main entry point.

The Typer ``app`` lives in ``_common``; commands live in one module per area
and are registered here, in the order ``jobwright --help`` lists them:

| Module | Commands |
|--------|----------|
| ``stages``    | ``init``, ``run`` |
| ``apply_cmds`` | ``apply`` (+ ``auto``, ``pick``, ``veto``, ``due``, ``provide``, ...), ``answers ...`` |
| ``materials`` | ``tailor-job``, ``network``, ``targets`` |
| ``health``    | ``status``, ``dashboard``, ``doctor``, ``preflight`` |
| ``brief``     | ``notify``, ``summary``, ``briefstats``, ``dedupe`` |
| ``scoring``   | ``eval``, ``rescore``, ``criteria ...``, ``labels ...`` |
| ``users`` / ``ops`` / ``access`` / ``hermes`` | the sub-apps of the same name |

``jobwright.cli:app`` (``[project.scripts]``), ``python -m jobwright.cli``
(``__main__.py``) and the names tests use (``_bootstrap``,
``_register_usage_flush``) stay importable from here. Commands call
``_common.bootstrap()``, which looks ``_bootstrap`` up on this package at call
time, so monkeypatching ``jobwright.cli._bootstrap`` still takes effect.
"""

from __future__ import annotations

from typing import Optional

import typer

from jobwright import __version__
from jobwright.cli._common import (
    VALID_STAGES,
    _bootstrap,
    _configure_logging,
    _load_profile_or_none,
    _resolve_user_option,
    app,
    console,
    err_console,
    log,
)


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
    _register_usage_flush()


_usage_flush_registered = False


def _register_usage_flush() -> None:
    """Flush any LLM usage left in the ledger to the active user's DB at exit.

    Covers commands that call the LLM outside a pipeline stage (tailor-job,
    criteria suggest, ...). Pipeline stages also flush after each stage.
    """
    global _usage_flush_registered
    if _usage_flush_registered:
        return
    import atexit

    from jobwright.llm import flush_active_usage

    atexit.register(flush_active_usage)
    _usage_flush_registered = True
    # SIGTERM (dashboard Stop, pm2, kill) -> SystemExit, so finally blocks and
    # this atexit flush run instead of losing the run's LLM spend.
    import signal
    import sys

    try:
        if signal.getsignal(signal.SIGTERM) is signal.SIG_DFL:
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    except ValueError:  # not the main thread (e.g. called from a test thread)
        pass


# ---------------------------------------------------------------------------
# Command registration (order = `jobwright --help` order)
# ---------------------------------------------------------------------------

from jobwright.cli.access import _access_call, _print_access_plan, access_app, access_status, access_sync  # noqa: E402
from jobwright.cli.brief import briefstats_cmd, dedupe, notify, summary  # noqa: E402
from jobwright.cli.health import dashboard, doctor, preflight, status  # noqa: E402
from jobwright.cli.hermes import hermes_app, hermes_channels_cmd  # noqa: E402
from jobwright.cli.materials import network, tailor_job, targets  # noqa: E402
from jobwright.cli.ops import (  # noqa: E402
    eval_eligible,
    ops_app,
    ops_backup,
    ops_brief_report,
    ops_install_crons,
    ops_release_uncertain,
    ops_restore,
    ops_set_target,
    ops_watchdog,
    ops_weekly_eval,
)
from jobwright.cli.scoring import (  # noqa: E402
    criteria_app,
    criteria_show,
    criteria_suggest,
    eval_cmd,
    labels_app,
    labels_export,
    labels_list,
    rescore,
)
from jobwright.cli.apply_cmds import answers_app, apply, apply_app  # noqa: E402
from jobwright.cli.stages import init, run  # noqa: E402
from jobwright.cli.users import users_add, users_app, users_list, users_remove, users_set, users_show  # noqa: E402

app.add_typer(users_app, name="users")
app.command()(init)
app.command()(run)
app.command("tailor-job")(tailor_job)
app.add_typer(apply_app, name="apply")
app.add_typer(answers_app, name="answers")
app.command()(status)
app.command()(dashboard)
app.command()(doctor)
app.command()(notify)
app.command()(summary)
app.command("briefstats")(briefstats_cmd)
app.command()(network)
app.command()(targets)
app.add_typer(criteria_app, name="criteria")
app.add_typer(labels_app, name="labels")
app.command("eval")(eval_cmd)
app.command()(rescore)
app.command()(dedupe)
app.command()(preflight)
app.add_typer(ops_app, name="ops")
app.add_typer(access_app, name="access")
app.add_typer(hermes_app, name="hermes")

__all__ = [
    "VALID_STAGES", "app", "console", "err_console", "log", "main",
    "_bootstrap", "_configure_logging", "_load_profile_or_none", "_register_usage_flush", "_resolve_user_option",
    "_access_call", "_print_access_plan", "access_app", "access_status", "access_sync",
    "briefstats_cmd", "dedupe", "notify", "summary",
    "dashboard", "doctor", "preflight", "status",
    "hermes_app", "hermes_channels_cmd",
    "network", "tailor_job", "targets",
    "eval_eligible", "ops_app", "ops_backup", "ops_brief_report", "ops_install_crons", "ops_release_uncertain",
    "ops_restore", "ops_set_target", "ops_watchdog", "ops_weekly_eval",
    "criteria_app", "criteria_show", "criteria_suggest", "eval_cmd", "labels_app", "labels_export", "labels_list",
    "rescore",
    "apply", "apply_app", "answers_app", "init", "run",
    "users_add", "users_app", "users_list", "users_remove", "users_set", "users_show",
]
