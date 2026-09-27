"""New-profile onboarding: create a user, draft their setup from a resume, save it.

Flow (dashboard):
  1. create_profile()          registry entry bound to the login email
  2. draft_from_resume()       LLM drafts profile + job preferences + searches
                               + match criteria from the uploaded resume
  3. user reviews / edits      nothing is written until they confirm
  4. apply_draft()             writes profile.json, searches.yaml
  5. WhatsApp + schedule       (whatsapp.py, hermes_cron.ensure_brief_cron)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

import jobwright.config as config
from jobwright.llm import get_client, llm_purpose
from jobwright.llm_json import parse_json_object
from jobwright.scoring.criteria_miner import suggest_criteria
from jobwright.users import add_user, get_user, validate_user_id

DRAFT_SCHEMA = {
    "name": "onboarding_draft",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "personal": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in (
                    "full_name", "preferred_name", "email", "phone", "city", "province_state", "country", "linkedin_url",
                )},
                "required": ["full_name", "preferred_name", "email", "phone", "city", "province_state", "country",
                             "linkedin_url"],
                "additionalProperties": False,
            },
            "experience": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in (
                    "years_of_experience_total", "education_level", "current_job_title", "current_company", "target_role",
                )},
                "required": ["years_of_experience_total", "education_level", "current_job_title", "current_company",
                             "target_role"],
                "additionalProperties": False,
            },
            "ideal_roles": {"type": "array", "items": {"type": "string"}},
            "avoid_roles": {"type": "array", "items": {"type": "string"}},
            "search_queries": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "open_to_remote": {"type": "boolean"},
            "min_salary": {"type": ["number", "null"]},
        },
        "required": ["personal", "experience", "ideal_roles", "avoid_roles", "search_queries", "locations",
                     "open_to_remote", "min_salary"],
        "additionalProperties": False,
    },
}

DRAFT_PROMPT = """Set up a daily job search for the person whose resume is below.

Fill every field from the resume (use "" when unknown; never invent contact details).
- target_role: 1-3 sentences describing the roles they should be matched to, in plain words.
- ideal_roles: 4-8 role types that fit their background and stated goals.
- avoid_roles: roles they would not want or could not get (only when the resume or hints suggest it).
- search_queries: 8-15 short job-board search phrases (2-5 words each) that would find ideal roles.
  Mix exact titles ("program officer") with functional phrases ("social impact strategy").
- locations: cities/regions they can work in (from the resume address and hints). Use "City, ST" form.
- open_to_remote: true unless hints say otherwise.
- min_salary: annual USD floor only if hints state one, else null.

HINTS FROM THE USER (take precedence over the resume):
{hints}

=== RESUME ===
{resume}

Return ONLY the JSON object."""

_DEFAULT_BOARDS = ["linkedin", "indeed"]


def slug_user_id(name: str, email: str = "") -> str:
    base = (name or email.split("@")[0] or "user").lower()
    base = re.sub(r"[^a-z0-9]+", "", base.split()[0] if " " in base else base) or "user"
    if not base[0].isalpha():
        base = "u" + base
    candidate = base[:24]
    n = 2
    while get_user(candidate) is not None:
        candidate = f"{base[:22]}{n}"
        n += 1
    return candidate


def create_profile(*, name: str, email: str, user_id: str | None = None, schedule: str = "0 7 * * *") -> str:
    uid = (user_id or slug_user_id(name, email)).strip().lower()
    validate_user_id(uid)
    add_user(
        uid, name=name.strip() or uid, emails=[email] if email else [], schedule=schedule,
        digest_schedule=schedule, human_gate=True, brief_top_n=10,
    )
    return uid


def draft_from_resume(resume_text: str, hints: dict[str, Any] | None = None, client=None) -> dict[str, Any]:
    """Draft profile + preferences + searches + criteria. Pure: writes nothing."""
    hints = {k: v for k, v in (hints or {}).items() if v}
    client = client or get_client()
    with llm_purpose("onboarding"):
        text = client.chat_structured(
            [{"role": "user", "content": DRAFT_PROMPT.format(
                hints=json.dumps(hints, indent=1) if hints else "(none)", resume=resume_text[:9000],
            )}],
            DRAFT_SCHEMA, max_tokens=5000, temperature=0.2, reasoning_effort="medium",
        )
    raw = parse_json_object(text, json_mode=False)
    profile = {
        "personal": raw.get("personal") or {},
        "experience": raw.get("experience") or {},
        "job_preferences": {
            "ideal_roles": raw.get("ideal_roles") or [],
            "avoid_roles": raw.get("avoid_roles") or [],
            "seek": "",
            "company_types": "",
        },
        "compensation": {
            "salary_expectation": str(int(raw["min_salary"])) if raw.get("min_salary") else "",
            "salary_range_min": str(int(raw["min_salary"])) if raw.get("min_salary") else "",
            "salary_currency": "USD",
        },
    }
    criteria = suggest_criteria(resume_text=resume_text, profile=profile, decisions=[], client=client)
    locations = [{"location": loc, "remote": False} for loc in (raw.get("locations") or [])][:6]
    if raw.get("open_to_remote", True):
        locations.append({"location": "Remote", "remote": True})
    searches = {
        "queries": [{"query": q, "tier": 1 if i < 8 else 2} for i, q in enumerate(raw.get("search_queries") or [])],
        "locations": locations,
        "boards": list(_DEFAULT_BOARDS),
        "min_salary": int(raw["min_salary"]) if raw.get("min_salary") else None,
    }
    return {"profile": profile, "criteria": criteria.to_dict(), "searches": searches}


def _merge(base: dict, updates: dict) -> dict:
    out = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _accept_patterns(locations: list[dict]) -> list[str]:
    patterns: list[str] = []
    for loc in locations:
        name = str(loc.get("location") or "").strip()
        if not name:
            continue
        if name.lower() == "remote":
            patterns.append("Remote")
            continue
        city = name.split(",")[0].strip()
        patterns.append(city)
        if "," in name:
            patterns.append(name.split(",")[1].strip())
    seen: list[str] = []
    for p in patterns:
        if p and p not in seen:
            seen.append(p)
    return seen


def apply_draft(draft: dict[str, Any]) -> None:
    """Write the confirmed draft into the active user's profile.json + searches.yaml."""
    profile_path = Path(config.PROFILE_PATH)
    current = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
    profile = _merge(current, draft.get("profile") or {})
    if draft.get("criteria"):
        profile["match_criteria"] = draft["criteria"]
    profile.setdefault("tailor_mode", "subtle")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = profile_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(profile_path)

    example = config.CONFIG_DIR / "searches.example.yaml"
    base = yaml.safe_load(example.read_text(encoding="utf-8")) if example.exists() else {}
    search_path = Path(config.SEARCH_CONFIG_PATH)
    existing = yaml.safe_load(search_path.read_text(encoding="utf-8")) if search_path.exists() else None
    searches = dict(existing or base or {})
    incoming = draft.get("searches") or {}
    for key in ("queries", "locations", "boards", "min_salary"):
        if key in incoming and incoming[key] is not None:
            searches[key] = incoming[key]
    if incoming.get("locations"):
        searches["location"] = {
            "accept_patterns": _accept_patterns(incoming["locations"]),
            "reject_patterns": (searches.get("location") or {}).get("reject_patterns") or [],
        }
    search_path.write_text(yaml.safe_dump(searches, sort_keys=False, allow_unicode=True), encoding="utf-8")


def is_set_up(user_id: str) -> bool:
    """Resume and profile present: the brief has what it needs to run."""
    with config.user_context(user_id):
        steps = onboarding_status()["steps"]
    return bool(steps.get("resume") and steps.get("profile"))


def onboarding_status() -> dict[str, Any]:
    """Which setup steps the active profile has completed."""
    from jobwright.users import get_user as _get_user

    uid = config.get_active_user_id()
    user = _get_user(uid) if uid else None
    profile = {}
    if Path(config.PROFILE_PATH).exists():
        try:
            profile = json.loads(Path(config.PROFILE_PATH).read_text(encoding="utf-8"))
        except ValueError:
            profile = {}
    searches = {}
    if Path(config.SEARCH_CONFIG_PATH).exists():
        searches = yaml.safe_load(Path(config.SEARCH_CONFIG_PATH).read_text(encoding="utf-8")) or {}
    covers = list(Path(config.COVER_LETTER_EXAMPLES_DIR).glob("*.pdf")) if Path(
        config.COVER_LETTER_EXAMPLES_DIR).is_dir() else []
    steps = {
        "resume": Path(config.RESUME_PDF_PATH).exists(),
        "profile": bool((profile.get("experience") or {}).get("target_role")),
        "criteria": bool(profile.get("match_criteria")),
        "searches": bool(searches.get("queries")),
        "cover_letters": bool(covers),
        "whatsapp": bool(user and user.whatsapp_target),
        "schedule": bool(user and user.schedule),
        "first_run": (Path(config.LOG_DIR) / "last_run.json").exists(),
    }
    required = ("resume", "profile", "searches")
    return {"user_id": uid, "steps": steps, "complete": all(steps[k] for k in required)}
