"""Greenhouse hybrid helpers: public Job Board API schema + dossier validation."""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

log = logging.getLogger(__name__)

_BOARDS_API = "https://boards-api.greenhouse.io/v1/boards"

_STANDARD_PATH_RE = re.compile(
    r"^/(?P<board>[a-zA-Z0-9_\-]+)/jobs/(?P<job_id>\d+)",
    re.I,
)

_STANDARD_FIELD_NAMES = frozenset({
    "first name", "last name", "email", "phone", "resume", "cv",
    "resume/cv", "cover letter", "linkedin profile", "website",
})


def resolve_greenhouse_redirect(url: str, timeout: float = 3.0) -> str:
    """Resolve grnh.se short links to canonical Greenhouse URLs."""
    if "grnh.se" not in url.lower():
        return url
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.head(url)
            return str(resp.url)
    except Exception as exc:
        log.debug("Could not resolve short URL %s: %s", url, exc)
        return url


def parse_greenhouse_url(url: str) -> tuple[str, str] | None:
    """Extract (board_token, job_id) from a Greenhouse application URL."""
    if not url:
        return None

    if "grnh.se" in url.lower():
        url = resolve_greenhouse_redirect(url)

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    hostname = (parsed.hostname or "").lower()
    path = parsed.path
    query = parse_qs(parsed.query)

    if "greenhouse.io" in hostname:
        match = _STANDARD_PATH_RE.match(path)
        if match:
            return match.group("board"), match.group("job_id")

    board_param = query.get("for") or query.get("board")
    token_param = query.get("token") or query.get("job_id") or query.get("gh_jid") or query.get("id")
    if board_param and token_param:
        board = board_param[0].strip()
        job_id = "".join(c for c in token_param[0] if c.isdigit())
        if board and job_id:
            return board, job_id

    if "greenhouse.io" in hostname and token_param:
        parts = [p for p in path.split("/") if p]
        if parts and parts[0] not in ("embed", "jobs"):
            job_id = "".join(c for c in token_param[0] if c.isdigit())
            if job_id:
                return parts[0], job_id

    return None


def fetch_greenhouse_schema(
    board_token: str,
    job_id: str,
    timeout: float = 8.0,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Fetch job + questions schema from public boards-api with retries."""
    api_url = f"{_BOARDS_API}/{board_token}/jobs/{job_id}?questions=true"
    client_timeout = httpx.Timeout(timeout, connect=3.0, read=5.0)

    with httpx.Client(timeout=client_timeout, follow_redirects=True) as client:
        for attempt in range(max_retries + 1):
            try:
                resp = client.get(api_url)
                if resp.status_code == 404:
                    log.info("Greenhouse job %s/%s not found (closed or private)", board_token, job_id)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    time.sleep((attempt + 1) * 1.0)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError):
                if attempt < max_retries:
                    time.sleep(1.0)
                    continue
                raise
    raise RuntimeError("Greenhouse schema fetch failed")


def _required_question_labels(schema: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for q in schema.get("questions") or []:
        if q.get("required"):
            labels.append((q.get("label") or "unknown").strip().replace("\n", " "))
    for block in schema.get("compliance") or []:
        if isinstance(block, dict):
            for q in block.get("questions") or []:
                if q.get("required"):
                    labels.append((q.get("label") or "compliance").strip().replace("\n", " "))
    demo = schema.get("demographic_questions")
    if isinstance(demo, dict):
        for q in demo.get("questions") or []:
            if q.get("required"):
                labels.append((q.get("label") or "demographic").strip().replace("\n", " "))
    return labels


def validate_schema_against_profile(schema: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    """Return warnings for missing standard fields the schema likely needs."""
    warnings: list[str] = []
    personal = profile.get("personal") or {}
    full_name = personal.get("full_name") or ""
    checks = {
        "first name": bool(full_name),
        "last name": bool(full_name.split()[-1] if " " in full_name else full_name),
        "email": bool(personal.get("email")),
        "phone": bool(personal.get("phone")),
    }
    for label in _required_question_labels(schema):
        ll = label.lower()
        if "first name" in ll and not checks["first name"]:
            warnings.append(f"Missing first name for required field: {label}")
        if "last name" in ll and not checks["last name"]:
            warnings.append(f"Missing last name for required field: {label}")
        if "email" in ll and not checks["email"]:
            warnings.append(f"Missing email for required field: {label}")
        if "phone" in ll and not checks["phone"]:
            warnings.append(f"Missing phone for required field: {label}")
    return warnings


def summarize_schema_for_prompt(schema: dict[str, Any], max_questions: int = 20) -> str:
    """Compact schema summary for the apply agent prompt."""
    custom_items: list[str] = []

    for q in schema.get("questions") or []:
        if not q.get("required"):
            continue
        label = (q.get("label") or "?").strip().replace("\n", " ")
        if label.lower() in _STANDARD_FIELD_NAMES:
            continue
        fields = q.get("fields") or []
        ftype = fields[0].get("type", "input") if fields else "input"
        values = fields[0].get("values", []) if fields else []
        if values and len(values) <= 4:
            choices = ", ".join(str(v.get("label", "")) for v in values if v.get("label"))
            custom_items.append(f"  - {label} ({ftype}: [{choices}])")
        else:
            custom_items.append(f"  - {label} ({ftype})")
        if len(custom_items) >= max_questions:
            custom_items.append("  ... (additional questions in browser)")
            break

    for block in schema.get("compliance") or []:
        if isinstance(block, dict) and len(custom_items) < max_questions:
            for q in block.get("questions") or []:
                if q.get("required"):
                    label = (q.get("label") or "Compliance").strip().replace("\n", " ")
                    custom_items.append(f"  - [Compliance] {label}")
                    if len(custom_items) >= max_questions:
                        break

    lines = ["== GREENHOUSE FORM SCHEMA (pre-fetched via boards-api) =="]
    if custom_items:
        lines.append("Required employer screening questions:")
        lines.extend(custom_items)
    else:
        lines.append("Required custom questions: (standard identity/resume fields only)")
    lines.append("")
    lines.append(
        "Note: Submit requires browser (reCAPTCHA + client fingerprint). "
        "Use schema to plan answers; output RESULT:DRYRUN or RESULT:APPLIED after filling."
    )
    return "\n".join(lines)
