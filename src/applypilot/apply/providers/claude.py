"""Legacy Claude Code CLI provider (upstream compatibility)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time

from applypilot.apply.chrome import _kill_process_tree
from applypilot.apply.providers.base import (
    AgentProvider,
    ApplyResult,
    WorkerContext,
    parse_result_output,
)
from applypilot.config import write_private_text

log = logging.getLogger(__name__)

_GMAIL_DISALLOWED = (
    "mcp__gmail__draft_email,mcp__gmail__modify_email,"
    "mcp__gmail__delete_email,mcp__gmail__download_attachment,"
    "mcp__gmail__batch_modify_emails,mcp__gmail__batch_delete_emails,"
    "mcp__gmail__create_label,mcp__gmail__update_label,"
    "mcp__gmail__delete_label,mcp__gmail__get_or_create_label,"
    "mcp__gmail__list_email_labels,mcp__gmail__create_filter,"
    "mcp__gmail__list_filters,mcp__gmail__get_filter,"
    "mcp__gmail__delete_filter"
)


class ClaudeProvider(AgentProvider):
    name = "claude"

    def _cancel_handle(self, handle: subprocess.Popen) -> None:
        if handle.poll() is None:
            _kill_process_tree(handle.pid)

    def run_apply(self, prompt: str, ctx: WorkerContext, mcp_config: dict) -> ApplyResult:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            return ApplyResult(
                outcome="failed:claude_not_found",
                duration_ms=0,
            )

        start = time.time()
        from applypilot import config

        mcp_path = config.APP_DIR / f".mcp-apply-{ctx.worker_id}.json"
        write_private_text(mcp_path, json.dumps(mcp_config))

        disallowed = (
            "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Task,KillShell,"
            + _GMAIL_DISALLOWED
        )
        if ctx.dry_run:
            disallowed += ",mcp__gmail__send_email"

        cmd = [
            claude_bin,
            "--model", ctx.model or "haiku",
            "-p",
            "--mcp-config", str(mcp_path),
            "--permission-mode", "bypassPermissions",
            "--no-session-persistence",
            "--disallowedTools", disallowed,
            "--output-format", "stream-json",
            "--verbose", "-",
        ]

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        text_parts: list[str] = []
        stats: dict = {}
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=str(ctx.workdir),
            )
            self.register_active(ctx.worker_id, proc)
            proc.stdin.write(prompt)
            proc.stdin.close()

            for line in proc.stdout or []:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "assistant":
                        for block in msg.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                text_parts.append(block["text"])
                    elif msg.get("type") == "result":
                        stats = {
                            "cost_usd": msg.get("total_cost_usd", 0),
                            "turns": msg.get("num_turns", 0),
                        }
                        text_parts.append(msg.get("result", ""))
                except json.JSONDecodeError:
                    text_parts.append(line)

            proc.wait(timeout=ctx.timeout_s)
            output = "\n".join(text_parts)
            duration_ms = int((time.time() - start) * 1000)
            status = parse_result_output(output, dry_run=ctx.dry_run)
            return ApplyResult(
                outcome=status,
                duration_ms=duration_ms,
                raw_output=output,
                stats=stats,
            )
        except subprocess.TimeoutExpired:
            if proc:
                self._cancel_handle(proc)
            return ApplyResult(outcome="failed:timeout", duration_ms=int((time.time() - start) * 1000))
        finally:
            self.unregister_active(ctx.worker_id)
