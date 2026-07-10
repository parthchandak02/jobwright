"""Agent provider abstraction for stage-6 job application."""

from __future__ import annotations

import os
import re
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ApplyOutcome(str, Enum):
    APPLIED = "applied"
    DRYRUN = "dryrun"
    EXPIRED = "expired"
    CAPTCHA = "captcha"
    LOGIN_ISSUE = "login_issue"
    SKIPPED = "skipped"
    FAILED = "failed"


PROMOTE_TO_STATUS = {"captcha", "expired", "login_issue"}


@dataclass
class WorkerContext:
    worker_id: int
    cdp_port: int
    workdir: Path
    dry_run: bool
    model: str
    timeout_s: int = 300


@dataclass
class ApplyResult:
    outcome: str  # applied, dryrun, expired, captcha, login_issue, failed:reason, skipped
    duration_ms: int
    raw_output: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None


def parse_result_output(output: str, dry_run: bool = False) -> str:
    """Parse agent output for RESULT:* protocol line.

    Returns status string compatible with launcher.mark_result.
    """
    if dry_run and "RESULT:DRYRUN" in output:
        return "dryrun"

    for result_status in ["APPLIED", "EXPIRED", "CAPTCHA", "LOGIN_ISSUE"]:
        if f"RESULT:{result_status}" in output:
            return result_status.lower()

    if "RESULT:FAILED" in output:
        for out_line in output.split("\n"):
            if "RESULT:FAILED" in out_line:
                reason = (
                    out_line.split("RESULT:FAILED:")[-1].strip()
                    if ":" in out_line[out_line.index("FAILED") + 6 :]
                    else "unknown"
                )
                reason = re.sub(r'[*`"]+$', "", reason).strip()
                if reason in PROMOTE_TO_STATUS:
                    return reason
                return f"failed:{reason}"
        return "failed:unknown"

    return "failed:no_result_line"


class AgentProvider(ABC):
    name: str

    _active: dict[int, Any] = {}
    _lock = threading.Lock()

    @abstractmethod
    def run_apply(self, prompt: str, ctx: WorkerContext, mcp_config: dict) -> ApplyResult:
        """Execute one apply agent session."""

    def cancel(self, worker_id: int) -> None:
        with self._lock:
            handle = self._active.pop(worker_id, None)
        if handle is not None:
            self._cancel_handle(handle)

    def _cancel_handle(self, handle: Any) -> None:
        """Override in subprocess-based providers."""

    @classmethod
    def register_active(cls, worker_id: int, handle: Any) -> None:
        with cls._lock:
            cls._active[worker_id] = handle

    @classmethod
    def unregister_active(cls, worker_id: int) -> None:
        with cls._lock:
            cls._active.pop(worker_id, None)


def get_provider(name: str | None = None) -> AgentProvider:
    """Factory for agent providers."""
    provider_name = (name or os.environ.get("AGENT_PROVIDER", "cursor-sdk")).lower()

    if provider_name == "cursor-sdk":
        from applypilot.apply.providers.cursor_sdk import CursorSdkProvider
        return CursorSdkProvider()
    if provider_name == "cursor-cli":
        from applypilot.apply.providers.cursor_cli import CursorCliProvider
        return CursorCliProvider()
    if provider_name == "claude":
        from applypilot.apply.providers.claude import ClaudeProvider
        return ClaudeProvider()

    raise ValueError(
        f"Unknown AGENT_PROVIDER '{provider_name}'. "
        "Choose: cursor-sdk, cursor-cli, claude"
    )
