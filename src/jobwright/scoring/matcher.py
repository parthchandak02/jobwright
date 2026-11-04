"""Scoring v2: criteria-driven, example-grounded job matching.

One call per job returns structured judgments instead of a bare number:
dealbreakers that apply, location fit, seniority fit, a 1-10 fit and a
confidence. Hard rules are applied in code (a dealbreaker caps the score at 3),
so the final score does not depend on the model remembering them.

By default a single model (LLM_MODEL, default glm-5p3-flash) scores every job
(tier 1). Escalation to a stronger model is opt-in: set LLM_ESCALATION_MODEL
(DEFAULT_ESCALATION_MODEL is empty, so it is off) and jobs that could reach the
notify list (tier-1 score >= escalate_at) or that tier 1 was unsure about are
re-scored by that model, whose verdict wins. Optional Jev fast-reject runs
before tier 1 (see fastpath.py). Optional borderline second opinion
(JOBWRIGHT_BORDERLINE_BAND, default off) re-asks for tier-1 scores inside a
band; evals showed no gain, so it stays off.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from jobwright.discovery.filters import apply_fit_score_guards, salary_below_floor
from jobwright.llm import get_client, get_client_for_model, llm_purpose
from jobwright.llm_json import LLMJsonError, parse_json_object
from jobwright.discovery.location import remote_scope
from jobwright.scoring.criteria import MatchCriteria, render_criteria
from jobwright.scoring.examples import ExampleIndex, render_examples

log = logging.getLogger(__name__)

PROMPT_VERSION = "v2.4"
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
# A job with no stated location (and no "remote" in the text) never reaches the
# daily list: high confidence requires knowing it is somewhere acceptable.
UNKNOWN_LOCATION_CAP = 6
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
3. Check location against the candidate's rules (onsite outside the acceptable areas or outside the country is a NO; remote within the country is fine unless stated otherwise). When the posting's LOCATION is "not stated", infer it only from explicit evidence in the description or the company name (e.g. "Goodwill of Central Arizona" is Arizona); never assume the candidate's own city. If you cannot tell, set location_ok to null.
4. Check seniority: "too_senior" when the role needs far more experience or a higher level than the candidate has, "too_junior" when clearly entry-level or an internship relative to them, otherwise "match" or "stretch".
5. Use the candidate's past decisions on similar postings as the strongest guide to their taste.
6. Then give fit 1-10 for how well the role matches what they want: 9-10 exactly the kind of role they want and are qualified for; 7-8 strong, would likely apply; 5-6 plausible but meaningful mismatch; 3-4 weak; 1-2 wrong field. Seniority is not a veto: when the role type is what they want, "stretch" or "too_senior" lowers fit by 1-2 points, not into 1-4 (candidates apply to stretch roles; follow their past decisions on where the line is).
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
    second_opinion: dict[str, Any] | None = None

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
                "second_opinion": self.second_opinion,
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
            criteria=render_criteria(self.criteria, remote=remote_scope(self.search_cfg))
            or "(none given; infer from the resume)",
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


def _user_message(ctx: MatchContext, job: dict, *, min_positive: int | None = None) -> str:
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
                min_positive=ctx.min_positive_examples if min_positive is None else min_positive,
            )
        )
    parts = [examples, "=== POSTING TO JUDGE ===", _job_block(job)]
    return "\n\n".join(p for p in parts if p)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _text_places_job_ok(job: dict, search_cfg: dict | None) -> bool:
    """Evidence (not the model's word) that a location-less job is remote or in an accepted area."""
    from jobwright.config import load_location_filters

    text = f"{job.get('title') or ''} {(job.get('full_description') or job.get('description') or '')[:4000]}"
    if re.search(r"\bremote\b", text, re.IGNORECASE):
        return True
    try:
        accept, _reject = load_location_filters(search_cfg or {})
    except Exception:  # noqa: BLE001
        accept = []
    for pat in accept:
        p = str(pat).strip()
        if len(p) >= 4 and re.search(rf"\b{re.escape(p)}\b", text, re.IGNORECASE):
            return True
    return False


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
    if not (job.get("location") or "").strip() and score > UNKNOWN_LOCATION_CAP:
        if not _text_places_job_ok(job, ctx.search_cfg):
            score = UNKNOWN_LOCATION_CAP
            caps.append("location not stated")
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
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_WORKERS = 16
# Concurrent 429s within this many seconds of a concurrency cut count as one burst.
LIMITER_WINDOW = 2.0


def _is_billing(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in _BILLING_STATUS


def _is_retry_exhausted(exc: Exception) -> bool:
    """429/5xx that already went through the client's own backoff retries."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in _RETRY_STATUS


def score_workers(default: int = DEFAULT_WORKERS) -> int:
    """Concurrent scoring calls: JOBWRIGHT_SCORE_WORKERS (default 16)."""
    try:
        return max(1, int(os.environ.get("JOBWRIGHT_SCORE_WORKERS", default)))
    except ValueError:
        return default


class AdaptiveLimiter:
    """Shared cap on in-flight scoring calls that backs off on rate limits.

    Starts at ``limit``. A 429 halves it (down to ``floor``); concurrent 429s
    from one burst (within ``window`` seconds of the last cut) halve it once.
    Every ``recover_after`` successes raise it by one, back up to ``limit``.
    A call that is sleeping in a retry keeps its slot, so a cut takes effect as
    soon as in-flight calls drop below the new cap.
    """

    def __init__(self, limit: int, *, floor: int = 1, recover_after: int = 8, window: float = 2.0,
                 clock=time.monotonic) -> None:
        self.max_limit = max(1, int(limit))
        self.limit = self.max_limit
        self.floor = max(1, min(int(floor), self.max_limit))
        self.recover_after = max(1, int(recover_after))
        self.window = window
        self.min_limit = self.limit
        self.cuts = 0
        self.active = 0
        self.peak_active = 0
        self._clock = clock
        self._ok = 0
        self._last_cut = float("-inf")
        self._cond = threading.Condition()

    def acquire(self, stop: threading.Event | None = None) -> bool:
        """Wait for a slot. False when ``stop`` was set while waiting."""
        with self._cond:
            while self.active >= self.limit:
                if stop is not None and stop.is_set():
                    return False
                self._cond.wait(timeout=0.25)
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            return True

    def release(self) -> None:
        with self._cond:
            self.active = max(0, self.active - 1)
            self._cond.notify_all()

    def throttled(self) -> None:
        with self._cond:
            now = self._clock()
            self._ok = 0
            if now - self._last_cut < self.window:
                return
            self._last_cut = now
            new = max(self.floor, self.limit // 2)
            if new < self.limit:
                self.limit = new
                self.cuts += 1
                self.min_limit = min(self.min_limit, new)
                log.warning("Scoring rate-limited: concurrency cut to %d", new)

    def succeeded(self) -> None:
        with self._cond:
            self._ok += 1
            if self._ok >= self.recover_after and self.limit < self.max_limit:
                self.limit += 1
                self._ok = 0
                self._cond.notify_all()


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


def judge_job(
    ctx: MatchContext, job: dict, client, *, tier: str, stop: threading.Event | None = None,
    min_positive: int | None = None, limiter: AdaptiveLimiter | None = None, on_retry=None,
) -> MatchResult | None:
    """One structured call with retries. None when the job could not be scored.

    Rate limits (429) and 5xx are retried with backoff inside the LLM client
    (``on_retry`` hears about each one); here only bad JSON / empty replies get
    another attempt. ``limiter`` bounds how many calls run at once.
    """
    messages = [
        {"role": "system", "content": ctx.system_prompt},
        {"role": "user", "content": _user_message(ctx, job, min_positive=min_positive)},
    ]
    rng = random.Random()
    held = [False]

    def retry_hook(status: int, wait: float) -> bool:
        # Give the slot back while backing off, then queue for one again, so a
        # concurrency cut also throttles retries already in flight.
        if on_retry is not None:
            on_retry(status, wait)
        if limiter is None:
            return False
        if held[0]:
            limiter.release()
            held[0] = False
        time.sleep(wait)
        held[0] = limiter.acquire(stop)
        if not held[0]:
            raise RuntimeError("scoring stopped")
        return True

    for attempt in range(1, ATTEMPTS + 1):
        if stop is not None and stop.is_set():
            return None
        try:
            if limiter is not None:
                held[0] = limiter.acquire(stop)
                if not held[0]:
                    return None
            try:
                with llm_purpose(f"score:{tier}"):
                    extra = {"on_retry": retry_hook} if (on_retry is not None or limiter is not None) else {}
                    text = client.chat_structured(
                        messages, SCHEMA, max_tokens=MAX_TOKENS, temperature=0.0,
                        reasoning_effort=os.environ.get(
                            f"JOBWRIGHT_REASONING_{tier.upper()}", TIER_REASONING.get(tier, TIER_REASONING["t1"])
                        ),
                        **extra,
                    )
            finally:
                if held[0]:
                    limiter.release()
                    held[0] = False
            if limiter is not None:
                limiter.succeeded()
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
            if _is_retry_exhausted(exc) or attempt >= ATTEMPTS:
                log.warning("Scoring failed for '%s' (%s): %s", job.get("title", "?"), tier, exc)
                return None
            time.sleep(min(8.0, 1.0 * 2 ** (attempt - 1) + rng.uniform(0, 0.5)))
    return None


@dataclass
class Borderline:
    """Second opinion for jobs the first pass scored inside [low, high].

    The second call sees a positive-balanced example set (and optionally a
    different model); ``combine`` merges the two scores.
    """

    low: int = 0
    high: int = 0
    model: str | None = None
    combine: str = "max"

    @property
    def enabled(self) -> bool:
        return 1 <= self.low <= self.high <= 10

    def applies(self, result: MatchResult) -> bool:
        # A capped score is deterministic: a second opinion cannot lift it.
        return self.enabled and self.low <= result.score <= self.high and not result.caps


def parse_band(text: str | None) -> tuple[int, int]:
    raw = (text or "").strip().lower()
    if raw in ("", "off", "none", "0"):
        return 0, 0
    parts = [p for p in re.split(r"[-:,\s]+", raw) if p]
    try:
        nums = [int(p) for p in parts[:2]]
    except ValueError:
        return 0, 0
    lo, hi = (nums[0], nums[-1]) if nums else (0, 0)
    return (min(lo, hi), max(lo, hi)) if 1 <= min(lo, hi) and max(lo, hi) <= 10 else (0, 0)


def borderline_from_env() -> Borderline:
    lo, hi = parse_band(os.environ.get("JOBWRIGHT_BORDERLINE_BAND"))
    combine = os.environ.get("JOBWRIGHT_BORDERLINE_COMBINE", "max").strip().lower()
    return Borderline(
        low=lo, high=hi, model=os.environ.get("JOBWRIGHT_BORDERLINE_MODEL", "").strip() or None,
        combine=combine if combine in ("max", "mean") else "max",
    )


def combine_opinions(first: MatchResult, second: MatchResult, how: str) -> MatchResult:
    if how == "mean":
        score = int((first.score + second.score) / 2 + 0.5)
        base = second if second.score > first.score else first
    else:
        base = second if second.score > first.score else first
        score = base.score
    out = MatchResult(**{**base.__dict__, "score": score})
    out.second_opinion = {
        "model": second.model, "first_score": first.score, "second_score": second.score,
        "second_fit": second.fit, "combine": how,
    }
    return out


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
    workers: int | None = None,
    escalate_at: int = 6,
    min_confidence: float = 0.55,
    escalate: bool = True,
    on_result=None,
    cheap_model: str | None = None,
    strong_model: str | None = None,
    borderline: Borderline | None = None,
    prior: dict[str, MatchResult] | None = None,
    stats: dict | None = None,
) -> tuple[list[MatchResult], int]:
    """Tiered concurrent scoring. ``on_result`` is called per final result (for incremental saves).

    ``prior`` maps url -> an existing first-pass result (evals reuse a stored run
    so only second opinions cost tokens). ``workers`` defaults to
    JOBWRIGHT_SCORE_WORKERS; an AdaptiveLimiter halves the number of calls in
    flight on a 429 and slowly recovers. When given, ``stats`` is filled with
    ``retries`` (all LLM retries), ``rate_limited`` (429s retried),
    ``workers`` and ``workers_min`` (lowest concurrency cap reached).
    """
    workers = score_workers() if workers is None else max(1, int(workers))
    limiter = AdaptiveLimiter(workers, window=LIMITER_WINDOW)
    counts = {"retries": 0, "rate_limited": 0}
    cheap = get_client_for_model(cheap_model) if cheap_model else get_client()
    borderline = borderline if borderline is not None else borderline_from_env()
    second_client = None
    if borderline.enabled:
        second_client = get_client_for_model(borderline.model) if borderline.model else cheap
    balanced = max(ctx.min_positive_examples, ctx.k_examples // 2)
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

    def on_retry(status: int, wait: float) -> None:
        with lock:
            counts["retries"] += 1
            if status == 429:
                counts["rate_limited"] += 1
        if status == 429:
            limiter.throttled()

    call = {"stop": stop, "limiter": limiter, "on_retry": on_retry}

    def run(job: dict) -> MatchResult | None:
        first = (prior or {}).get(job["url"]) or judge_job(ctx, job, cheap, tier="t1", **call)
        if first is not None and second_client is not None and borderline.applies(first):
            other = judge_job(ctx, job, second_client, tier="b2", min_positive=balanced, **call)
            if other is not None:
                first = combine_opinions(first, other, borderline.combine)
        if first is None or strong is None or not should_escalate(first, escalate_at, min_confidence):
            return first
        with lock:
            t2["tried"] += 1
        second = judge_job(ctx, job, strong, tier="t2", **call)
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
    if counts["retries"]:
        log.info(
            "Scoring retries: %d (%d rate-limited); concurrency %d -> min %d",
            counts["retries"], counts["rate_limited"], workers, limiter.min_limit,
        )
    if stats is not None:
        stats.update(counts, workers=workers, workers_min=limiter.min_limit)
    if billing is not None and not results:
        raise billing
    return results, errors
