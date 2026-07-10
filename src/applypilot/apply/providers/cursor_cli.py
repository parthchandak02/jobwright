"""Cursor Agent CLI provider for stage-6 apply (fallback/debug)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from applypilot.apply.chrome import _kill_process_tree
from applypilot.apply.providers.base import (
    AgentProvider,
    ApplyResult,
    WorkerContext,
    parse_result_output,
)
from applypilot.config import write_private_text

log = logging.getLogger(__name__)


class CursorCliProvider(AgentProvider):
    name = "cursor-cli"

    def _cancel_handle(self, handle: subprocess.Popen) -> None:
        if handle.poll() is None:
            _kill_process_tree(handle.pid)

    def run_apply(self, prompt: str, ctx: WorkerContext, mcp_config: dict) -> ApplyResult:
        agent_bin = shutil.which("agent")
        if not agent_bin:
            return ApplyResult(
                outcome="failed:agent_cli_not_found",
                duration_ms=0,
                raw_output="agent CLI not on PATH",
            )

        start = time.time()
        cursor_dir = ctx.workdir / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        write_private_text(cursor_dir / "mcp.json", json.dumps(mcp_config, indent=2))

        model = ctx.model or os.environ.get("APPLY_AGENT_MODEL", "composer-2.5")
        cmd = [
            agent_bin,
            "-p",
            "--print",
            "--trust",
            "--force",
            "--approve-mcps",
            "--output-format", "stream-json",
            "--workspace", str(ctx.workdir),
            "--model", model,
            prompt,
        ]

        text_parts: list[str] = []
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ctx.workdir),
            )
            self.register_active(ctx.worker_id, proc)

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
            )
        except subprocess.TimeoutExpired:
            if proc:
                self._cancel_handle(proc)
            return ApplyResult(
                outcome="failed:timeout",
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            log.exception("Cursor CLI apply failed")
            return ApplyResult(
                outcome=f"failed:{str(e)[:100]}",
                duration_ms=int((time.time() - start) * 1000),
                raw_output=str(e),
            )
        finally:
            self.unregister_active(ctx.worker_id)
