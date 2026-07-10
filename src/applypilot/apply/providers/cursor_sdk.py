"""Cursor SDK agent provider for stage-6 apply."""

from __future__ import annotations

import logging
import os
import time

from applypilot.apply.providers.base import (
    AgentProvider,
    ApplyResult,
    WorkerContext,
    parse_result_output,
)

log = logging.getLogger(__name__)


class CursorSdkProvider(AgentProvider):
    name = "cursor-sdk"

    def run_apply(self, prompt: str, ctx: WorkerContext, mcp_config: dict) -> ApplyResult:
        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

        start = time.time()
        api_key = os.environ.get("CURSOR_API_KEY", "")
        if not api_key:
            return ApplyResult(
                outcome="failed:missing_cursor_api_key",
                duration_ms=0,
                raw_output="CURSOR_API_KEY not set",
            )

        model = ctx.model or os.environ.get("APPLY_AGENT_MODEL", "composer-2.5")
        servers = mcp_config.get("mcpServers", mcp_config)

        try:
            result = Agent.prompt(
                prompt,
                AgentOptions(
                    api_key=api_key,
                    model=model,
                    local=LocalAgentOptions(
                        cwd=str(ctx.workdir),
                        setting_sources=[],
                    ),
                    mcp_servers=servers,
                ),
            )
            duration_ms = int((time.time() - start) * 1000)
            output = result.result or ""
            status = parse_result_output(output, dry_run=ctx.dry_run)
            return ApplyResult(
                outcome=status,
                duration_ms=duration_ms,
                raw_output=output,
                run_id=getattr(result, "id", None),
            )
        except CursorAgentError as e:
            duration_ms = int((time.time() - start) * 1000)
            log.error("Cursor SDK startup failed: %s", e)
            return ApplyResult(
                outcome=f"failed:cursor_sdk:{str(e)[:80]}",
                duration_ms=duration_ms,
                raw_output=str(e),
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            log.exception("Cursor SDK apply failed")
            return ApplyResult(
                outcome=f"failed:{str(e)[:100]}",
                duration_ms=duration_ms,
                raw_output=str(e),
            )
