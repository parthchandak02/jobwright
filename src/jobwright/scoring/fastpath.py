"""TypeSafe Jev fast-path hybrid scorer (D3).

Port of the *verified working* benchmark reference
(``bench_v2_typesafe.py``) into the jobwright pipeline as a plain-HTTP,
no-SDK module. Jev scores every job cheaply; in ``on`` mode its verdicts
fast-accept / fast-reject high/low-confidence jobs so deepseek is skipped.

Pipeline hook — call signature
------------------------------
.. code-block:: python

    from jobwright.scoring import fastpath
    from jobwright.scoring.scorer import run_scoring

    results = fastpath.score_fastpath(jobs, user_config, conn)

Arguments:
    jobs:        ``list[dict]`` — job dicts from the database (must include
                 ``url``; read ``title``/``company``/``location``/
                 ``full_description`` for the Jev state).
    user_config: ``dict`` — the per-user config/profile object as returned by
                 ``jobwright.config.load_profile()``. Read for the
                 ``jev_hybrid`` key (``"off" | "shadow" | "on"``, default
                 ``"off"``). May be ``None``/``{}`` → treated as ``"off"``.
    conn:        ``sqlite3.Connection`` — jev columns (``jev_score``,
                 ``jev_confidence``, ``jev_routed``) are written here.

    The caller MUST also have ``TYPESAFE_API_KEY`` available in the active
    user's ``<user>/ .env``/environment (read from ``config.ENV_PATH``,
    never the repo ``.env``), otherwise the fastpath is a no-op.

Returns:
    ``list[dict]`` — one per job::

        {"url": str, "jev_score": int|None, "jev_confidence": float|None,
         "jev_route": "fast_accept" | "fast_reject" | "escalate"}

    In ``shadow`` mode every job's ``jev_route`` is ``"escalate"`` — the caller
    must still deepseek-score everything and make NO routing decisions; the
    jev fields are stored for calibration only. In ``on`` mode the caller
    interprets ``fast_accept``/``fast_reject`` as *deepseek skipped* verdicts.

Routing thresholds (``on`` mode only): fast_accept ``jev_score >= 8 and
conf >= 0.6``; fast_reject ``jev_score <= 4 and conf >= 0.6``; anything in the
5-7 band or below 0.6 confidence escalates to deepseek.

Errors are logged and downgraded, never raised — the fastpath can never block
the deepseek scoring stage.
"""

from __future__ import annotations

import logging
import os
import statistics
from typing import Any

import httpx

from jobwright import config

log = logging.getLogger(__name__)

# Jev API (verified working: model is jev-latest, NOT jev-1.13;
# response key is 'answers' not 'scores'; Score answers are 0-indexed +1)
MODEL = "jev-latest"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
GATE_THRESHOLD = 0.60

# Composite weights (faithful to benchmark reference)
_W_ROLE = 0.50
_W_MISSION = 0.30
_W_SENIOR = 0.20

# Routing thresholds (on mode)
_FAST_ACCEPT_MIN = 8
_FAST_REJECT_MAX = 4
_ROUTE_CONFIDENCE = 0.60


# ---------------------------------------------------------------------------
# Jev request definition (ported verbatim from the benchmark reference)
# ---------------------------------------------------------------------------

# State = candidate profile + job, filtered to what the questions need.
_DEFAULT_CANDIDATE = {
    "profile": {
        "current_seniority": (
            "associate to director-level strategy/program roles"
        ),
        "target_functions": [
            "program strategy or program officer (foundation PROGRAM side, not fundraising)",
            "impact investing / VC analyst-associate (impact-focused funds only)",
            "chief of staff at mission-driven startups (seed to Series C, non-tech industries welcome)",
            "strategy & operations at mission-driven nonprofits or social enterprises",
        ],
        "sectors_of_interest": [
            "education",
            "workforce development",
            "economic mobility",
            "climate",
            "health",
        ],
        "location_preference": "San Francisco Bay Area or Remote-US",
        "hard_exclusions": [
            "any role with fundraising, development, advancement, or grant-writing/grant-research duties",
            "any role requiring a PhD, clinical/therapy license, or CPA",
        ],
    }
}

EXCLUSIONS: dict[str, dict[str, Any]] = {
    "excl_fundraising": {
        "type": "noul",
        "instructions": {
            "question": "Does this job have fundraising, development, advancement, or grant writing/research as a core duty?",
            "inspect": "job.description",
            "focus": "Look for raising money: donor cultivation, grant proposals, development campaigns. Program roles that merely partner with fundraisers are NOT excluded.",
        },
        "criteria": {
            "true": {
                "what": "The job's responsibilities include raising funds or writing/managing grants",
                "examples": [
                    "manage a portfolio of major donors",
                    "write grant proposals and letters of intent",
                    "lead the development committee",
                    "identify grant opportunities from foundations",
                ],
            },
            "false": {
                "what": "No fundraising duties; the role is program, investing, strategy, or operations work",
                "examples": [
                    "review grant applications to decide funding (grantmaker side)",
                    "run programs funded by grants but raise nothing",
                    "source and evaluate venture investments",
                ],
            },
        },
    },
    "excl_license": {
        "type": "noul",
        "instructions": {
            "question": "Does this job require a PhD, a clinical or therapy license (LCSW, LMFT, psychologist), or a CPA as a qualification?",
            "inspect": "job.description",
            "focus": "Required credentials only. A driver's license or 'preferred' language that appears soft is not a requirement unless stated as required.",
        },
        "criteria": {
            "true": {
                "what": "A listed requirement includes PhD, clinical license (LCSW/LMFT/psychologist), or CPA",
                "examples": [
                    "LCSW or LMFT license required",
                    "CPA required",
                    "PhD in economics required",
                ],
            },
            "false": {
                "what": "No such credential is required",
                "examples": [
                    "Bachelor's degree required",
                    "driver's license required",
                    "teaching credential preferred",
                ],
            },
        },
    },
    "role_function_match": {
        "type": "score",
        "instructions": "How well does this job's core FUNCTION match the candidate's target_functions? Judge the actual day-to-day work described in job.description, not the title alone.",
        "criteria": [
            "Core work is a different function entirely (sales, engineering, accounting, clinical care, asset management)",
            "Adjacent function with partial overlap (general comms, general ops far from strategy)",
            "Some overlap but mostly different day-to-day work",
            "Substantially matches one target function (program strategy, impact investing, chief of staff, strategy & ops)",
            "Core work IS one of the target functions almost exactly",
        ],
    },
    "mission_sector_alignment": {
        "type": "score",
        "instructions": "How well does this job's organization and purpose align with the candidate's sectors_of_interest?",
        "criteria": [
            "Sector is outside all interests (pure tech product, defense, real estate)",
            "Weak alignment (generic corporate, unclear purpose)",
            "Some overlap (e.g., sustainability at a food company)",
            "Strong alignment (nonprofit or company clearly working in education, workforce, economic mobility, climate, or health)",
            "Purpose-built for those sectors (impact fund, education nonprofit, workforce org)",
        ],
    },
    "seniority_fit": {
        "type": "score",
        "instructions": "Is the required seniority appropriate for an associate-to-director-level candidate? Consider years of experience requested and scope (individual contributor to director).",
        "criteria": [
            "Entry-level or internship; well below candidate's level",
            "Requires 8+ years or VP/C-level scope; likely above her level",
            "Requires 5-7 years; a stretch but plausible",
            "Requires 3-5 years; squarely in range",
            "Requires 2-5 years with growth room; ideal band",
        ],
    },
}


# ---------------------------------------------------------------------------
# Config accessors
# ---------------------------------------------------------------------------

def get_jev_hybrid(user_config: dict | None) -> str:
    """Read the user's ``jev_hybrid`` mode ("off" | "shadow" | "on").

    Defaults to ``"off"`` when the key is absent or the config is unavailable,
    so enabling the fastpath always requires an explicit per-user setting.
    """
    if not isinstance(user_config, dict):
        return "off"
    value = str(user_config.get("jev_hybrid") or "off").strip().lower()
    if value not in ("shadow", "on"):
        return "off"
    return value


def _typesafe_api_key() -> str | None:
    """Resolve TYPESAFE_API_KEY: shell env, then the active user's <user>/.env.

    Never reads the repo-root .env (secrets stay per-user / operator env).
    """
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    env_path = getattr(config, "ENV_PATH", None)
    if not env_path or not env_path.exists():
        return None
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() != "TYPESAFE_API_KEY":
                continue
            value = val.strip().strip('"').strip("'")
            return value or None
    except OSError:
        return None
    return None


def _build_candidate(user_config: dict | None) -> dict[str, Any]:
    """Build the Jev candidate profile, overlaying per-user config when present."""
    cfg = user_config or {}
    experience = cfg.get("experience") or {}
    prefs = cfg.get("job_preferences") or {}
    personal = cfg.get("personal") or {}

    target_functions = prefs.get("ideal_roles") or []
    if not target_functions and experience.get("target_role"):
        target_functions = [experience["target_role"]]

    sectors = (
        cfg.get("sectors_of_interest")
        or prefs.get("sectors_of_interest")
        or list(_DEFAULT_CANDIDATE["profile"]["sectors_of_interest"])
    )

    location = cfg.get("location_preference") or (
        f"{(personal.get('city') or '')} / Remote-US" if personal.get("city") else ""
    ) or _DEFAULT_CANDIDATE["profile"]["location_preference"]

    hard_exclusions = cfg.get("hard_exclusions") or prefs.get("avoid_roles")
    if not hard_exclusions:
        hard_exclusions = _DEFAULT_CANDIDATE["profile"]["hard_exclusions"]
    if not isinstance(hard_exclusions, list):
        hard_exclusions = [str(hard_exclusions)]

    seniority = cfg.get("current_seniority") or (
        f"{experience.get('years_of_experience_total', '')} years, "
        f"{experience.get('education_level', '')}".strip()
    ).strip(" ,") or _DEFAULT_CANDIDATE["profile"]["current_seniority"]

    return {
        "profile": {
            "current_seniority": seniority,
            "target_functions": list(target_functions) or _DEFAULT_CANDIDATE["profile"]["target_functions"],
            "sectors_of_interest": list(sectors),
            "location_preference": location,
            "hard_exclusions": hard_exclusions,
        }
    }


def _job_state(job: dict) -> dict[str, Any]:
    """Build the job-side Jev state (title/company/location/description)."""
    return {
        "title": job.get("title") or "",
        "company": job.get("company") or job.get("site") or "",
        "location": job.get("location") or "",
        "description": (job.get("full_description") or job.get("description") or "").strip(),
    }


# ---------------------------------------------------------------------------
# HTTP + composite math
# ---------------------------------------------------------------------------

def _post_systemone(payload: dict, api_key: str) -> dict:
    """POST the Jev payload to TypeSafe /systemone. Returns parsed JSON.

    Plain HTTP via httpx (shared client is safe for concurrent calls).
    Raised errors propagate to the per-job handler, which downgrades them.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    client = _get_client()
    resp = client.post(ENDPOINT, json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or "answers" not in data:
        raise ValueError(f"Jev response missing 'answers' key: keys={list(data.keys())!r}")
    return data


_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=60)
    return _client


def _composite_from_answers(answers: dict) -> tuple[int, float, str | None, float]:
    """Turn Jev ``answers`` into (score, confidence, gated_by, p_yes).

    Port of benchmark composite: 1 + 9 * (0.50*role + 0.30*mission + 0.20*seniority),
    where each dimension is a 0-indexed 0-4 score normalized to 0-1. A Noul gate
    with p(yes) > 0.60 short-circuits to score 1, gated=True.
    """
    for gname in ("excl_fundraising", "excl_license"):
        gate = answers.get(gname) or {}
        p_yes = float(((gate.get("probabilities") or {}).get("true") or 0) or 0)
        if p_yes > GATE_THRESHOLD:
            return 1, 0.0, gname, p_yes

    try:
        role = float(answers["role_function_match"]["score"]) / 4
        mission = float(answers["mission_sector_alignment"]["score"]) / 4
        senior = float(answers["seniority_fit"]["score"]) / 4
        confs = [
            float(answers[k].get("confidence") or 0) if isinstance(answers[k], dict) else 0.0
            for k in ("role_function_match", "mission_sector_alignment", "seniority_fit")
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed Jev answers: {exc}") from exc

    composite = 1 + 9 * (_W_ROLE * role + _W_MISSION * mission + _W_SENIOR * senior)
    return round(composite), round(statistics.mean(confs), 4), None, 0.0


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def jev_route(score: int | None, confidence: float | None, mode: str) -> str:
    """Decide the deepseek-skip route for a jev score + confidence (``on`` only).

    Returns ``"escalate"`` in shadow/off mode (no decision is ever made there).
    """
    if mode != "on" or score is None or confidence is None:
        return "escalate"
    if confidence >= _ROUTE_CONFIDENCE and score >= _FAST_ACCEPT_MIN:
        return "fast_accept"
    if confidence >= _ROUTE_CONFIDENCE and score <= _FAST_REJECT_MAX:
        return "fast_reject"
    return "escalate"


# ---------------------------------------------------------------------------
# Public pipeline hook
# ---------------------------------------------------------------------------

def score_fastpath(
    jobs: list[dict],
    user_config: dict | None,
    conn,
) -> list[dict[str, Any]]:
    """Score every job with Jev and persist jev columns (see module docstring).

    Modes:
      - ``off``: no-op (``[]``).
      - ``shadow``: score + log + store, route=``escalate``, no decisions.
      - ``on``: score + store + return routing verdicts for the caller.

    Never raises — per-job failures are logged and downgraded so the deepseek
    stage is never blocked.
    """
    mode = get_jev_hybrid(user_config)
    if mode not in ("shadow", "on"):
        return []

    api_key = _typesafe_api_key()
    if not api_key:
        log.warning(
            "Jev fastpath %s disabled: TYPESAFE_API_KEY missing from %s",
            mode, config.ENV_PATH,
        )
        return []

    candidate = _build_candidate(user_config or {})
    results: list[dict[str, Any]] = []
    for job in jobs:
        url = job.get("url")
        if not url:
            results.append({"url": "", "jev_score": None, "jev_confidence": None, "jev_route": "error"})
            continue
        item: dict[str, Any] = {"url": url, "jev_score": None, "jev_confidence": None, "jev_route": "error"}
        try:
            payload = {
                "model": MODEL,
                "state": {"candidate": candidate, "job": _job_state(job)},
                "questions": EXCLUSIONS,
            }
            answers = _post_systemone(payload, api_key).get("answers", {})
            score, conf, gated_by, _p_yes = _composite_from_answers(answers)
            route = jev_route(score, conf, mode)
            item.update(jev_score=score, jev_confidence=conf, jev_route=route)
            log.info(
                "jev %s score=%s conf=%.3f route=%s gate=%s %s",
                mode, score, conf, route, gated_by or "-", url[-60:],
            )
        except Exception as exc:  # noqa: BLE001 - fastpath must never block deepseek
            log.warning("Jev fastpath failed for %s: %s", url, exc)
        _persist(conn, item)
        results.append(item)
    return results


def _persist(conn, item: dict[str, Any]) -> None:
    """Write jev columns for one job (idempotent)."""
    try:
        conn.execute(
            "UPDATE jobs SET jev_score = ?, jev_confidence = ?, jev_routed = ? WHERE url = ?",
            (item["jev_score"], item["jev_confidence"], item["jev_route"], item["url"]),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - storage must never block scoring
        log.warning("Failed to persist jev columns for %s: %s", item.get("url"), exc)