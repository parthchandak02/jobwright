"""Propose a user's match_criteria from their resume, stated preferences and past decisions.

Used by onboarding (resume + preferences only) and by "refine from my ratings"
(adds every labeled job and the user's own rationale). The output is a
proposal: the user reviews and saves it in the dashboard.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from jobwright.labels import EvalItem
from jobwright.llm import get_client, llm_purpose
from jobwright.llm_json import parse_json_object
from jobwright.scoring.criteria import MatchCriteria, parse_criteria

log = logging.getLogger(__name__)

MINER_SCHEMA = {
    "name": "match_criteria",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "dealbreakers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["id", "label", "description"],
                    "additionalProperties": False,
                },
            },
            "must_haves": {"type": "array", "items": {"type": "string"}},
            "nice_to_haves": {"type": "array", "items": {"type": "string"}},
            "locations_ok": {"type": "array", "items": {"type": "string"}},
            "locations_not_ok": {"type": "array", "items": {"type": "string"}},
            "seniority": {"type": "string"},
            "min_salary": {"type": ["number", "null"]},
        },
        "required": [
            "summary", "dealbreakers", "must_haves", "nice_to_haves",
            "locations_ok", "locations_not_ok", "seniority", "min_salary",
        ],
        "additionalProperties": False,
    },
}

MINER_PROMPT = """You write the screening rules a job-matching assistant will use for ONE candidate.
Rules must describe the candidate's real taste precisely enough that a screener can say yes/no to a posting.

Write:
- summary: 2-4 sentences, plain words, what roles they want and why they fit.
- dealbreakers: 3-8 rules. Each is a thing that makes a posting a clear NO when it is the job's PRIMARY function or a hard requirement they cannot meet. Short snake_case id, a 2-4 word label, and a one-sentence description. Only include rules supported by the evidence (stated exclusions, repeated rejections with the same reason). If the candidate applied to roles that break a stated rule, narrow the rule so it matches their behavior.
- must_haves: the role types that are a good fit (4-8 items).
- nice_to_haves: things that make a good posting better.
- locations_ok / locations_not_ok: from stated preferences and location-based rejections.
- seniority: one or two sentences on the right level, grounded in their experience and what they applied to.
- min_salary: annual USD floor if stated, else null.

=== RESUME ===
{resume}

=== STATED PREFERENCES (profile) ===
{prefs}

=== PAST DECISIONS ({n_labels} rated or acted on) ===
{decisions}

Return ONLY the JSON object."""


def _prefs_block(profile: dict[str, Any] | None) -> str:
    profile = profile or {}
    keep = {k: profile.get(k) for k in ("experience", "job_preferences", "compensation", "work_authorization")}
    return json.dumps({k: v for k, v in keep.items() if v}, indent=1)[:6000]


def _decisions_block(items: list[EvalItem], limit: int = 160) -> str:
    if not items:
        return "(none yet)"
    ordered = sorted(items, key=lambda i: (i.label, bool(i.rationale)), reverse=True)[:limit]
    lines = []
    for it in ordered:
        verdict = "WANTED/APPLIED" if it.label else "REJECTED"
        rated = f" rated {it.label_score}/10" if it.label_score else ""
        why = f' — "{it.rationale.strip()[:140]}"' if it.rationale.strip() else ""
        where = f" ({it.location})" if it.location else ""
        lines.append(f"- {verdict}{rated}: {it.title} @ {it.company or '?'}{where}{why}")
    return "\n".join(lines)


def suggest_criteria(
    *,
    resume_text: str,
    profile: dict[str, Any] | None,
    decisions: list[EvalItem] | None = None,
    client=None,
) -> MatchCriteria:
    prompt = MINER_PROMPT.format(
        resume=(resume_text or "")[:7000],
        prefs=_prefs_block(profile),
        n_labels=len(decisions or []),
        decisions=_decisions_block(decisions or []),
    )
    client = client or get_client()
    with llm_purpose("criteria"):
        text = client.chat_structured(
            [{"role": "user", "content": prompt}], MINER_SCHEMA, max_tokens=6000, temperature=0.2,
            reasoning_effort="medium",
        )
    raw = parse_json_object(text, json_mode=False)
    criteria = parse_criteria(raw)
    threshold = (profile or {}).get("match_criteria", {}).get("notify_threshold") if profile else None
    if threshold:
        criteria.notify_threshold = int(threshold)
    return criteria
