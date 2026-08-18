"""Derive employer visa sponsorship stance from job description text.

Two-tier classifier:
  1. High-precision regex (free, instant) handles the explicit cases and is the
     only path used by the web API and the per-connection DB backfill.
  2. A cheap LLM tie-breaker (`classify_sponsorship`) fires only when the text
     has sponsorship/eligibility signal but the regex could not classify it, so
     LLM calls stay near-zero for the common "not mentioned" case.

Status values (candidate-eligibility view):
  required     -> employer offers / will provide visa sponsorship        (amber)
  not_required -> no sponsorship, or US citizen / green card required     (red / ineligible)
  not_found    -> sponsorship not mentioned                              (grey / unknown)
"""

from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

SPONSORSHIP_STATUSES = ("required", "not_required", "not_found")

# Tokens that gate the (relatively expensive) regex scan and the LLM tie-breaker.
# If none appear, the posting says nothing about sponsorship or eligibility.
_SIGNAL_TOKENS = (
    "sponsor",
    "h-1b",
    "h1b",
    "immigration",
    "green card",
    "permanent resident",
    "citizen",
    "work authorization",
    "authorized to work",
    "work permit",
    "visa",
)

# High-precision negative phrases seen on employer portals and aggregators.
# "not_required" = candidate needing sponsorship is ineligible / employer won't sponsor.
_NOT_REQUIRED = re.compile(
    r"(?:"
    r"no\s+(?:visa\s+)?sponsorship|"
    r"not\s+eligible\s+for(?:\s+[\w-]+){0,6}\s+(?:visa|immigration)\s+sponsorship|"
    r"not\s+eligible\s+for\s+(?:visa|immigration)\s+sponsorship|"
    r"(?:work\s+permit|immigration)\s+sponsorship\s+is\s+not\s+available|"
    r"unable\s+to\s+provide\s+sponsorship|"
    r"(?:unable|cannot|can't|will\s+not|won't|do\s+not|does\s+not)\s+(?:to\s+)?"
    r"(?:provide|offer)\s+(?:visa\s+)?sponsorship|"
    r"sponsorship\s+(?:is\s+)?not\s+(?:available|provided|offered|possible)|"
    r"without\s+(?:the\s+need\s+for\s+)?(?:current\s+or\s+future\s+)?(?:visa\s+)?sponsorship|"
    r"authorized\s+to\s+work[^.\n]{0,120}without[^.\n]{0,80}sponsorship|"
    r"legally\s+authorized\s+to\s+work[^.\n]{0,120}without[^.\n]{0,80}sponsorship|"
    r"no\s+(?:h-?1b|visa)\s+sponsorship|"
    # Citizenship / permanent-residency requirements => candidate ineligible.
    r"must\s+be\s+(?:a\s+)?(?:u\.?\s?s\.?\s+)?citizen|"
    r"(?:u\.?\s?s\.?\s+)?citizenship\s+(?:is\s+)?required|"
    r"citizens?\s+or\s+(?:lawful\s+)?permanent\s+residents?\s+(?:only|required)|"
    r"(?:u\.?\s?s\.?\s+)?citizens?\s+or\s+green\s+card\s+holders?\s+(?:only|required)?|"
    r"(?:green\s+card|permanent\s+resident)\s+(?:holders?\s+)?(?:only|required)|"
    r"must\s+be\s+(?:a\s+)?(?:u\.?\s?s\.?\s+)?(?:permanent\s+resident|green\s+card\s+holder)"
    r")",
    re.IGNORECASE,
)

# High-precision positive phrases (qualified offers included).
_REQUIRED = re.compile(
    r"(?:"
    r"we\s+do\s+sponsor\s+visas|"
    r"(?:visa|h-?1b|immigration)\s+sponsorship\s*:\s*we\s+do\s+sponsor|"
    r"(?:visa|h-?1b|immigration)\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)|"
    r"sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)|"
    r"(?:we\s+)?(?:will\s+)?(?:provide|offer)\s+(?:visa\s+)?sponsorship|"
    r"open\s+to\s+(?:visa\s+)?sponsorship"
    r")",
    re.IGNORECASE,
)

_IMMIGRATION_SPONSORSHIP = re.compile(
    r"(?:visa|immigration|h-?1b)\s+sponsorship",
    re.IGNORECASE,
)


def _has_signal(lower: str) -> bool:
    return any(token in lower for token in _SIGNAL_TOKENS)


def derive_sponsorship_status(description: str | None) -> str:
    """Regex-only classification. Deterministic, no network. Returns a status."""
    if not description or not description.strip():
        return "not_found"

    text = description
    lower = text.lower()
    if not _has_signal(lower):
        return "not_found"

    if _NOT_REQUIRED.search(text):
        return "not_required"
    if _REQUIRED.search(text):
        return "required"
    return "not_found"


# ── LLM tie-breaker ────────────────────────────────────────────────────────

_LLM_LABEL_MAP = {
    "offers_sponsorship": "required",
    "no_sponsorship": "not_required",
    "not_mentioned": "not_found",
}

_LLM_SYSTEM = (
    "You classify a US job posting by the employer's visa sponsorship stance, "
    "from the perspective of a candidate who needs work-visa sponsorship. "
    "Return ONLY JSON: {\"status\": \"offers_sponsorship\" | \"no_sponsorship\" | \"not_mentioned\"}.\n"
    "- offers_sponsorship: the employer states it provides / is open to visa or H-1B sponsorship.\n"
    "- no_sponsorship: the posting says sponsorship is NOT available, the candidate must already be "
    "authorized to work without sponsorship, or requires US citizenship / green card / permanent residency.\n"
    "- not_mentioned: the posting does not address sponsorship or work-authorization eligibility.\n"
    "Watch negation: 'will sponsor' vs 'will not sponsor'; 'no sponsorship required' means the applicant "
    "must not need it (that is no_sponsorship, not an offer)."
)


def _llm_enabled() -> bool:
    """LLM tie-breaker on by default when a provider is configured; SPONSORSHIP_LLM=0 disables."""
    flag = os.environ.get("SPONSORSHIP_LLM", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return any(
        os.environ.get(k)
        for k in ("FIREWORKS_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL")
    )


def _excerpt(text: str, limit: int = 6000) -> str:
    """Keep head + tail so sponsorship lines (often in EEO boilerplate at the end) survive."""
    text = text.strip()
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n...\n{text[-half:]}"


def _classify_llm(description: str) -> str | None:
    """Ask the LLM for a stance. Returns a status or None on any failure."""
    try:
        from jobwright.llm import get_client
        from jobwright.llm_json import chat_json_object

        client = get_client()
        data = chat_json_object(
            client,
            [
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": f"JOB POSTING:\n{_excerpt(description)}"},
            ],
            max_tokens=64,
            temperature=0.0,
            max_parse_retries=1,
        )
        label = str(data.get("status") or "").strip().lower()
        return _LLM_LABEL_MAP.get(label)
    except Exception as exc:  # noqa: BLE001 - tie-breaker is best-effort
        log.debug("Sponsorship LLM classification failed: %s", exc)
        return None


def classify_sponsorship(description: str | None, *, use_llm: bool | None = None) -> str:
    """Two-tier classification.

    Regex first (high precision, free). When regex is decisive, return it. When
    regex is `not_found` but the text carries sponsorship/eligibility signal, ask
    a cheap LLM to break the tie. Falls back to the regex result on any error or
    when the LLM tier is disabled/unavailable.
    """
    regex_status = derive_sponsorship_status(description)
    if regex_status != "not_found":
        return regex_status

    if not description or not _has_signal(description.lower()):
        return "not_found"

    if use_llm is None:
        use_llm = _llm_enabled()
    if not use_llm:
        return "not_found"

    return _classify_llm(description) or "not_found"


def backfill_sponsorship_status(conn) -> int:
    """Populate sponsorship_status for rows that are still NULL (regex only)."""
    rows = conn.execute(
        """
        SELECT url, full_description, description
        FROM jobs
        WHERE sponsorship_status IS NULL
        """
    ).fetchall()
    updated = 0
    for row in rows:
        text = row["full_description"] or row["description"]
        status = derive_sponsorship_status(text)
        conn.execute(
            "UPDATE jobs SET sponsorship_status = ? WHERE url = ?",
            (status, row["url"]),
        )
        updated += 1
    if updated:
        conn.commit()
    return updated
