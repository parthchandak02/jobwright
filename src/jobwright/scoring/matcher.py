"""Scoring v2: criteria-driven, example-grounded, tiered job matching.

One call per job returns structured judgments instead of a bare number:
dealbreakers that apply, location fit, seniority fit, a 1-10 fit and a
confidence. Hard rules are applied in code (a dealbreaker caps the score at 3),
so the final score does not depend on the model remembering them.

Tiers (cost-optimized):
  1. cheap model (LLM_MODEL, default glm-5p3-flash) scores every job
  2. jobs that could reach the notify list (tier-1 score >= escalate_at) or
     that tier 1 was unsure about go to a stronger model, whose verdict wins
Optional Jev fast-reject runs before tier 1 (see fastpath.py).
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from jobwright.discovery.filters import apply_fit_score_guards, salary_below_floor
from jobwright.llm import get_client, get_client_for_model, llm_purpose
from jobwright.llm_json import LLMJsonError, parse_json_object
from jobwright.scoring.criteria import MatchCriteria, render_criteria
from jobwright.scoring.examples import ExampleIndex, render_examples

log = logging.getLogger(__name__)

PROMPT_VERSION = "v2.2"
DESC_CHARS = 6000
RESUME_CHARS = 7000
MAX_TOKENS = 2500
ATTEMPTS = 3
DEALBREAKER_CAP = 3
LOCATION_CAP = 3
# Seniority informs fit but does not hard-cap by default: candidates apply to
# stretch roles, and a cap here cost recall in evals. Set to e.g. 5 to enforce.
SENIORITY_CAP = 0
SALARY_CAP = 4
# Escalation is opt-in (LLM_ESCALATION_MODEL). Evals on 249 labeled jobs showed
# no precision/recall gain from glm-5p3 or kimi-k3 over the cheap tier with
# retrieved examples, at 1.2-3x the cost and time (Sep 2026).
DEFAULT_ESCALATION_MODEL = ""
# Hidden-thinking budget per tier (thinking-only models truncate without it).
TIER_REASONING = {"t1": "low", "t2": "medium"}

SYSTEM_TEMPLATE = """You screen job postings for ONE specific candidate and decide whether each posting is worth their time to apply to. Be strict and concrete: the candidate only wants roles they would genuinely want AND can realistically get. A posting that sounds impressive but trips a dealbreaker is a NO.

How to judge:
1. Read the posting's core duties and hard requirements (not the company boilerplate).
2. Check every dealbreaker. Put its id in "dealbreakers" ONLY when it is the PRIMARY function of the role (most of the day-to-day work) or an explicit hard requirement the candidate cannot meet (e.g. a required license or degree). If it is only one duty among several, or a "nice to have", put the id in "concerns" instead. The candidate's past decisions show where their line is: follow them.
3. Check location against the candidate's rules (onsite outside the acceptable areas or outside the country is a NO; remote within the country is fine unless stated otherwise).
4. Check seniority: "too_senior" when the role needs far more experience or a higher level than the candidate has, "too_junior" when clearly entry-level or an internship relative to them, otherwise "match" or "stretch".
5. Use the candidate's past decisions on similar postings as the strongest guide to their taste.
6. Then give fit 1-10 for how well the role matches what they want: 9-10 exactly the kind of role they want and are qualified for; 7-8 strong, would likely apply; 5-6 plausible but meaningful mismatch; 3-4 weak; 1-2 wrong field.
7. confidence 0-1: how sure you are, given how much the posting actually says.

=== CANDIDATE RESUME ===
{resume}

=== CANDIDATE'S RULES ===
{criteria}

Return ONLY JSON: {{"dealbreakers": [ids], "concerns": [ids], "location_ok": true|false|null, "seniority": "too_junior"|"match"|"stretch"|"too_senior", "fit": 1-10, "confidence": 0-1, "reasoning": "2-3 sentences naming the deciding facts"}}"""

SCHEMA = {
    "name": "job_match_v2",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "dealbreakers": {"type": "array", "items": {"type": "string"}},
            "concerns": {"type": "array", "items": {"type": "string"}},
            "location_ok": {"type": ["boolean", "null"]},
            "seniority": {"type": "string", "enum": ["too_junior", "match", "stretch", "too_senior"]},
            "fit": {"type": "integer", "minimum": 1, "maximum": 10},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
        },
        "required": ["dealbreakers", "concerns", "location_ok", "seniority", "fit", "confidence", "reasoning"],
        "additionalProperties": False,
    },
}


@dataclass
class MatchResult:
    url: str
    score: int
    fit: int
    confidence: float
    dealbreakers: list[str]
    location_ok: bool | None
    seniority: str
    reasoning: str
    model: str
    tier: str
    caps: list[str] = field(default_factory=list)
    escalated_from: dict[str, Any] | None = None
    concerns: list[str] = field(default_factory=list)

    def gates_json(self) -> str:
        return json.dumps(
            {
                "fit": self.fit,
                "dealbreakers": self.dealbreakers,
                "concerns": self.concerns,
                "location_ok": self.location_ok,
                "seniority": self.seniority,
                "caps": self.caps,
                "escalated_from": self.escalated_from,
            }
        )

    def reasoning_text(self) -> str:
        cap = f" [{'; '.join(self.caps)}]" if self.caps else ""
        return f"{self.reasoning}{cap}"


@dataclass
class MatchContext:
    resume_text: str
    criteria: MatchCriteria
    index: ExampleIndex | None
    search_cfg: dict[str, Any] | None = None
    k_examples: int = 8
    leave_one_out: bool = False
    min_positive_examples: int = 2

    def __post_init__(self) -> None:
        self.system_prompt = SYSTEM_TEMPLATE.format(
            resume=(self.resume_text or "")[:RESUME_CHARS],
            criteria=render_criteria(self.criteria) or "(none given; infer from the resume)",
        )

    @property
    def version(self) -> str:
        digest = hashlib.sha1(self.system_prompt.encode()).hexdigest()[:8]
        return f"{PROMPT_VERSION}+{digest}"


def _job_block(job: dict) -> str:
    return (
        f"TITLE: {job.get('title') or ''}\n"
        f"COMPANY: {job.get('company') or 'not stated'}\n"
        f"LOCATION: {job.get('location') or 'not stated'}\n"
        f"SALARY: {job.get('salary') or 'not stated'}\n"
        f"DESCRIPTION:\n{(job.get('full_description') or job.get('description') or '')[:DESC_CHARS]}"
    )


def _user_message(ctx: MatchContext, job: dict) -> str:
    examples = ""
    if ctx.index is not None:
        exclude = {job["url"]} if ctx.leave_one_out else set()
        keys = set()
        if ctx.leave_one_out:
            from jobwright.discovery.dedupe import normalize_company, normalize_title

            keys = {f"{normalize_company(job.get('company'))}|{normalize_title(job.get('title'))}"}
        examples = render_examples(
            ctx.index.query(
                job.get("title") or "",
                job.get("company") or "",
                job.get("full_description") or job.get("description") or "",
                k=ctx.k_examples,
                exclude_urls=exclude,
                exclude_keys=keys,
                min_positive=ctx.min_positive_examples,
            )
        )
    parts = [examples, "=== POSTING TO JUDGE ===", _job_block(job)]
    return "\n\n".join(p for p in parts if p)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def apply_gates(raw: dict[str, Any], job: dict, ctx: MatchContext) -> tuple[int, list[str], list[str]]:
    """Deterministic caps on top of the model's fit. Returns (score, dealbreakers, caps)."""
    fit = max(1, min(10, int(raw.get("fit") or 1)))
    valid = ctx.criteria.dealbreaker_ids()
    deals = [d for d in (raw.get("dealbreakers") or []) if isinstance(d, str) and d in valid]
    score, caps = fit, []
    if deals:
        score = min(score, DEALBREAKER_CAP)
        caps.append(f"dealbreaker: {', '.join(deals)}")
    if raw.get("location_ok") is False:
        score = min(score, LOCATION_CAP)
        caps.append("location")
    seniority_cap = _env_int("JOBWRIGHT_SENIORITY_CAP", SENIORITY_CAP)
    if seniority_cap and raw.get("seniority") in ("too_senior", "too_junior"):
        score = min(score, seniority_cap)
        caps.append(f"seniority: {raw.get('seniority')}")
    if ctx.criteria.min_salary and salary_below_floor(job.get("salary"), ctx.criteria.min_salary):
        score = min(score, SALARY_CAP)
        caps.append("salary below floor")
    guarded = apply_fit_score_guards(job, {"score": score, "reasoning": ""}, ctx.search_cfg)
    if int(guarded["score"]) < score:
        score = int(guarded["score"])
        caps.append(guarded["reasoning"].strip(" []") or "search filter")
    return score, deals, caps


class BillingDead(RuntimeError):
    """Provider refused on billing/auth grounds; stop the whole stage."""


_BILLING_STATUS = frozenset({401, 402, 403})


def _is_billing(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in _BILLING_STATUS


def _parse(raw_text: str) -> dict[str, Any]:
    data = parse_json_object(raw_text, json_mode=False)
    if "fit" not in data:
        if "score" in data:
            data["fit"] = data["score"]
        else:
            raise LLMJsonError("missing fit")
    try:
        data["fit"] = int(data["fit"])
        data["confidence"] = float(data.get("confidence", 0.5))
    except (TypeError, ValueError) as exc:
        raise LLMJsonError(f"bad numeric field: {exc}") from exc
    data["confidence"] = max(0.0, min(1.0, data["confidence"]))
    if data.get("seniority") not in ("too_junior", "match", "stretch", "too_senior"):
        data["seniority"] = "match"
    data["reasoning"] = str(data.get("reasoning") or "").strip()
    return data


def judge_job(ctx: MatchContext, job: dict, client, *, tier: str, stop: threading.Event | None = None) -> MatchResult | None:
    """One structured call with retries. None when the job could not be scored."""
    messages = [
        {"role": "system", "content": ctx.system_prompt},
        {"role": "user", "content": _user_message(ctx, job)},
    ]
    rng = random.Random()
    for attempt in range(1, ATTEMPTS + 1):
        if stop is not None and stop.is_set():
            return None
        try:
            with llm_purpose(f"score:{tier}"):
                text = client.chat_structured(
                    messages, SCHEMA, max_tokens=MAX_TOKENS, temperature=0.0,
                    reasoning_effort=os.environ.get(f"JOBWRIGHT_REASONING_{tier.upper()}", TIER_REASONING.get(tier)),
                )
            raw = _parse(text)
            score, deals, caps = apply_gates(raw, job, ctx)
            return MatchResult(
                url=job["url"], score=score, fit=int(raw["fit"]), confidence=float(raw["confidence"]),
                dealbreakers=deals, location_ok=raw.get("location_ok"), seniority=raw["seniority"],
                reasoning=raw["reasoning"], model=getattr(client, "model", "?"), tier=tier, caps=caps,
                concerns=[c for c in (raw.get("concerns") or []) if isinstance(c, str)],
            )
        except Exception as exc:  # noqa: BLE001 - classified below
            if _is_billing(exc):
                if stop is not None:
                    stop.set()
                raise BillingDead(str(exc)[:200]) from exc
            if attempt >= ATTEMPTS:
                log.warning("Scoring failed for '%s' (%s): %s", job.get("title", "?"), tier, exc)
                return None
            time.sleep(min(8.0, 1.0 * 2 ** (attempt - 1) + rng.uniform(0, 0.5)))
    return None


def escalation_model() -> str | None:
    model = os.environ.get("LLM_ESCALATION_MODEL", DEFAULT_ESCALATION_MODEL).strip()
    if model.lower() in ("", "off", "none", "0"):
        return None
    return model


def should_escalate(result: MatchResult, escalate_at: int, min_confidence: float) -> bool:
    if result.score >= escalate_at:
        return True
    return result.confidence < min_confidence and result.fit >= escalate_at - 2 and not result.dealbreakers


def score_jobs(
    ctx: MatchContext,
    jobs: list[dict],
    *,
    workers: int = 16,
    escalate_at: int = 6,
    min_confidence: float = 0.55,
    escalate: bool = True,
    on_result=None,
    cheap_model: str | None = None,
    strong_model: str | None = None,
) -> tuple[list[MatchResult], int]:
    """Tiered concurrent scoring. ``on_result`` is called per final result (for incremental saves)."""
    cheap = get_client_for_model(cheap_model) if cheap_model else get_client()
    if escalate:
        strong_model = strong_model or escalation_model()
    else:
        strong_model = None
    strong = get_client_for_model(strong_model) if strong_model else None
    if strong is not None and getattr(strong, "model", None) == getattr(cheap, "model", None):
        strong = None
    stop = threading.Event()
    lock = threading.Lock()
    results: list[MatchResult] = []
    errors = 0
    t2 = {"tried": 0, "failed": 0}

    def run(job: dict) -> MatchResult | None:
        first = judge_job(ctx, job, cheap, tier="t1", stop=stop)
        if first is None or strong is None or not should_escalate(first, escalate_at, min_confidence):
            return first
        with lock:
            t2["tried"] += 1
        second = judge_job(ctx, job, strong, tier="t2", stop=stop)
        if second is None:
            with lock:
                t2["failed"] += 1
            return first
        second.escalated_from = {"model": first.model, "score": first.score, "fit": first.fit, "confidence": first.confidence}
        return second

    billing: BillingDead | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(run, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
            except BillingDead as exc:
                billing = billing or exc
                stop.set()
                continue
            with lock:
                if res is None:
                    errors += 1
                else:
                    results.append(res)
                    if on_result is not None:
                        on_result(res)
    if t2["tried"] and t2["failed"] * 2 >= t2["tried"]:
        log.error(
            "Escalation model %s failed on %d/%d jobs; tier-1 scores were kept. "
            "Check LLM_ESCALATION_MODEL (is it deployed for this key?).",
            strong_model, t2["failed"], t2["tried"],
        )
    if billing is not None and not results:
        raise billing
    return results, errors
