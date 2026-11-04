"""Shared CLI state and helpers: the Typer app, consoles, bootstrap."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console

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
console = Console()
# Diagnostics banner goes to stderr so it never pollutes stdout consumed by
# `--json` callers (e.g. agent CLI shims that parse stdout as JSON).
err_console = Console(stderr=True)
log = logging.getLogger("jobwright.cli")

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

    # One line per HTTP request (and httpcore's per-socket DEBUG) would bury
    # the run log: LinkedIn discovery alone makes thousands of requests.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _LOGGING_CONFIGURED = True

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



def bootstrap() -> None:
    """Run ``jobwright.cli._bootstrap`` looked up at call time.

    Commands call this instead of ``_bootstrap`` directly so tests (and any
    caller) can still monkeypatch ``jobwright.cli._bootstrap``.
    """
    import jobwright.cli as pkg

    pkg._bootstrap()


def _load_profile_or_none() -> Optional[dict]:
    from jobwright.config import load_profile

    try:
        return load_profile()
    except FileNotFoundError:
        return None
