"""Pre-run health checks shared by the daily brief, the CLI and the dashboard.

Each check returns a Check(name, ok, blocking, detail). ``fix=True`` repairs
what can be repaired safely on this host (today: installing the Playwright
Chromium build that matches the installed playwright package, the cause of
the Sep 22-26 enrich outage).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

import httpx

import jobwright.config as config


@dataclass
class Check:
    name: str
    ok: bool
    blocking: bool
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


def _playwright_launch() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright package not installed in this Python"
    try:
        with sync_playwright() as pw:
            pw.chromium.launch(headless=True).close()
        return True, "chromium headless launch OK"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).splitlines()[0][:200]


def check_playwright(fix: bool = False) -> Check:
    ok, detail = _playwright_launch()
    if not ok and fix and "not installed in this Python" not in detail:
        proc = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=900, check=False,
        )
        if proc.returncode == 0:
            ok, detail = _playwright_launch()
            detail = f"installed chromium; {detail}"
        else:
            detail = f"{detail}; auto-install failed: {(proc.stderr or proc.stdout).strip()[:200]}"
    return Check("playwright", ok, True, detail)


def check_llm_key() -> Check:
    for key in ("FIREWORKS_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL"):
        if os.environ.get(key):
            return Check("llm_key", True, True, f"{key} set")
    return Check("llm_key", False, True, "no LLM provider key in the environment")


def check_user_inputs() -> Check:
    missing = []
    if not config.PROFILE_PATH.exists():
        missing.append("profile.json")
    if not (config.RESUME_PDF_PATH.exists() or config.RESUME_MD_PATH.exists()):
        missing.append("resume/base.pdf")
    if missing:
        return Check("user_inputs", False, True, "missing " + ", ".join(missing))
    return Check("user_inputs", True, True, "profile and resume present")


def check_disk(min_free_gb: float = 2.0) -> Check:
    try:
        free = shutil.disk_usage(config.APP_DIR).free / 1e9
    except OSError as exc:
        return Check("disk", False, True, f"data dir unavailable: {exc}")
    return Check("disk", free >= min_free_gb, True, f"{free:.1f} GB free at {config.APP_DIR}")


def check_hermes() -> Check:
    path = shutil.which("hermes")
    return Check("hermes_cli", bool(path), False, path or "hermes not on PATH (WhatsApp notify unavailable)")


def check_whatsapp_bridge(url: str = "http://127.0.0.1:3000/health") -> Check:
    try:
        resp = httpx.get(url, timeout=3)
        status = resp.json().get("status")
        return Check("whatsapp_bridge", status == "connected", False, f"bridge status={status}")
    except Exception as exc:  # noqa: BLE001
        return Check("whatsapp_bridge", False, False, f"bridge unreachable ({type(exc).__name__})")


def run_checks(*, fix: bool = False, include_browser: bool = True, include_whatsapp: bool = True) -> list[Check]:
    config.load_env()
    checks = [check_user_inputs(), check_llm_key(), check_disk(), check_hermes()]
    if include_browser:
        checks.append(check_playwright(fix=fix))
    if include_whatsapp:
        checks.append(check_whatsapp_bridge())
    return checks


def blocking_failures(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.blocking and not c.ok]
