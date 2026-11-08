"""Claude agent that drives OUR Playwright browser through ``ApplyTools``.

Why our own tool set instead of Anthropic's browser use toolset
(``browser_toolset_20260801``): the safety rules (answer bank for
attestations, hidden secrets, dry-run submit block, domain allowlist,
evidence) must be enforced in code on every action, which is simplest when we
own each tool. The loop is a plain manual tool-use loop on the Messages API.

Limits: ``JOBWRIGHT_APPLY_MAX_STEPS`` (default 60 tool calls),
``JOBWRIGHT_APPLY_TIMEOUT_S`` (default 900 s wall clock, not counting time
spent waiting for a human), and every response's usage goes to the LLM usage
ledger under ``llm_purpose('apply')``.

Model: ``JOBWRIGHT_APPLY_MODEL`` (default ``claude-sonnet-5-5``), effort
``JOBWRIGHT_APPLY_EFFORT`` (default ``medium``). Server-side refusal fallbacks
are on by default (``JOBWRIGHT_APPLY_FALLBACKS=off`` disables them).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from jobwright.apply.evidence import Transcript
from jobwright.apply.tools import ApplyTools, summarize_args, tool_definitions

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# USD per 1M tokens: input, output, cache read (first-party list prices).
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


def apply_model() -> str:
    return os.environ.get("JOBWRIGHT_APPLY_MODEL", "").strip() or DEFAULT_MODEL


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> float:
    price = PRICES.get(model)
    if not price:
        return 0.0
    inp, out, cached = price
    return round((input_tokens + cache_write * 1.25) / 1e6 * inp + cache_read / 1e6 * cached
                 + output_tokens / 1e6 * out, 6)


@dataclass
class AgentResult:
    status: str  # a FINISH_STATUSES value, or step_limit / timeout / refusal / error
    summary: str
    steps: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


def _block_dict(block: Any) -> dict:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return dict(vars(block))


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def make_client():
    import anthropic

    return anthropic.Anthropic(max_retries=3, timeout=120.0)


class AnthropicApplyAgent:
    provider_name = "anthropic"

    def __init__(self, client: Any = None, model: str | None = None) -> None:
        self._client = client
        self.model = model or apply_model()

    @property
    def client(self):
        if self._client is None:
            self._client = make_client()
        return self._client

    def _create(self, **kwargs):
        if os.environ.get("JOBWRIGHT_APPLY_FALLBACKS", "on").strip().lower() in ("0", "off", "false", "no"):
            return self.client.beta.messages.create(**kwargs)
        return self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)

    def _usage(self, resp: Any) -> tuple[int, int, float]:
        from jobwright.llm import record_usage

        usage = _get(resp, "usage") or {}
        i = int(_get(usage, "input_tokens", 0) or 0)
        o = int(_get(usage, "output_tokens", 0) or 0)
        cr = int(_get(usage, "cache_read_input_tokens", 0) or 0)
        cw = int(_get(usage, "cache_creation_input_tokens", 0) or 0)
        served = _get(resp, "model", None) or self.model
        record_usage("anthropic", served, {"prompt_tokens": i + cr + cw, "completion_tokens": o,
                                           "prompt_tokens_details": {"cached_tokens": cr}})
        return i + cr + cw, o, estimate_cost(served, i, o, cr, cw)

    def answer_open_question(self, question: str, job: dict, resume_text: str, cover_text: str = "") -> str:
        """One short, truthful answer to an open (non-attestation) form question."""
        from jobwright.apply.prompt import open_question_prompt
        from jobwright.llm import llm_purpose

        with llm_purpose("apply"):
            resp = self._create(
                model=self.model, max_tokens=2000,
                system=open_question_prompt(job, resume_text, cover_text),
                messages=[{"role": "user", "content": f"Question on the application form: {question}"}],
                output_config={"effort": "low"},
            )
            self._usage(resp)
        if _get(resp, "stop_reason") == "refusal":
            return ""
        text = " ".join(_block_dict(b).get("text", "") for b in (_get(resp, "content") or [])
                        if _block_dict(b).get("type") == "text").strip()
        return "" if text.upper().startswith("NO_ANSWER") else text

    def run(self, tools: ApplyTools, system_prompt: str, transcript: Transcript) -> AgentResult:
        from jobwright.llm import llm_purpose

        max_steps = _int_env("JOBWRIGHT_APPLY_MAX_STEPS", 60)
        timeout_s = _int_env("JOBWRIGHT_APPLY_TIMEOUT_S", 900)
        effort = os.environ.get("JOBWRIGHT_APPLY_EFFORT", "medium").strip() or "medium"
        defs = tool_definitions()
        messages: list[dict] = [{"role": "user", "content": "Apply to this job now. Begin with snapshot()."}]
        transcript.write("system", {"model": self.model, "prompt_chars": len(system_prompt)})
        started = time.monotonic()
        waited = 0.0
        tin = tout = 0
        cost = 0.0
        steps = 0

        def elapsed() -> float:
            return time.monotonic() - started - waited

        with llm_purpose("apply"):
            while True:
                if steps >= max_steps:
                    return AgentResult("step_limit", f"stopped after {steps} tool calls", steps, tin, tout, cost)
                if elapsed() > timeout_s:
                    return AgentResult("timeout", f"stopped after {int(elapsed())} s", steps, tin, tout, cost)
                try:
                    resp = self._create(
                        model=self.model,
                        max_tokens=16000,
                        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                        tools=defs,
                        messages=messages,
                        output_config={"effort": effort},
                    )
                except Exception as exc:  # noqa: BLE001 - API errors end this attempt
                    log.warning("apply agent API error: %s", exc)
                    transcript.write("error", str(exc)[:500])
                    return AgentResult("error", "model call failed", steps, tin, tout, cost, error=str(exc)[:300])
                used_in, used_out, used_cost = self._usage(resp)
                tin += used_in
                tout += used_out
                cost += used_cost
                content = [_block_dict(b) for b in (_get(resp, "content") or [])]
                stop = _get(resp, "stop_reason")
                transcript.write("assistant", {"stop_reason": stop, "content": [
                    {k: v for k, v in b.items() if k in ("type", "text", "name", "input", "id")} for b in content
                ]})
                # Append the full content unchanged (thinking blocks included).
                messages.append({"role": "assistant", "content": content})
                if stop == "refusal":
                    return AgentResult("refusal", "the model declined", steps, tin, tout, cost)
                tool_uses = [b for b in content if b.get("type") == "tool_use"]
                if not tool_uses:
                    if stop == "max_tokens":
                        messages.append({"role": "user", "content": "Continue. Use the tools."})
                        continue
                    if tools.state.finished:
                        break
                    messages.append({"role": "user", "content": "Use the tools. End with finish()."})
                    steps += 1
                    continue
                results = []
                for tu in tool_uses:
                    steps += 1
                    name, args = tu.get("name"), dict(tu.get("input") or {})
                    if name == "fill" and args.get("category") is None:
                        args.pop("category", None)
                    if name == "select" and args.get("category") is None:
                        args.pop("category", None)
                    if name == "finish" and not args.get("questions"):
                        args.pop("questions", None)
                    t0 = time.monotonic()
                    out = tools.call(name, args)
                    if name == "ask_human":
                        waited += time.monotonic() - t0
                    transcript.write("tool", {"call": summarize_args(name, args), "result": out[:4000]})
                    results.append({"type": "tool_result", "tool_use_id": tu.get("id"), "content": out})
                messages.append({"role": "user", "content": results})
                if tools.state.finished:
                    break
        fin = tools.state.finished or {}
        return AgentResult(fin.get("status", "failed"), fin.get("summary", ""), steps, tin, tout, cost)
