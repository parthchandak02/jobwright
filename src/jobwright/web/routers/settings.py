"""Editable user settings surfaced to the dashboard.

Reads and writes the same files the daily pipeline consumes:
- ``profile.json`` (identity + scoring guidance)
- ``searches.yaml`` (discover queries / locations / filters)
- ``resume/base.txt`` (base resume text)

Edits here take effect on the next pipeline run for the active user.
"""

from __future__ import annotations

import json
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from jobwright import config
from jobwright.users import get_user
from jobwright.web.session import resolve_dashboard_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Whitelisted profile fields (avoids surfacing secrets like password / eeo data).
_PERSONAL = [
    "full_name",
    "preferred_name",
    "email",
    "phone",
    "city",
    "province_state",
    "country",
    "linkedin_url",
]
_COMPENSATION = ["salary_expectation", "salary_range_min", "salary_range_max", "salary_currency"]
_EXPERIENCE = [
    "years_of_experience_total",
    "education_level",
    "current_job_title",
    "current_company",
    "target_role",
]
_PREFERENCES = ["ideal_roles", "seek", "avoid_roles", "company_types"]

_PROFILE_SECTIONS = (
    ("personal", _PERSONAL),
    ("compensation", _COMPENSATION),
    ("experience", _EXPERIENCE),
    ("job_preferences", _PREFERENCES),
)


def _load_profile() -> dict:
    if config.PROFILE_PATH.exists():
        try:
            return json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(500, f"profile.json is not valid JSON: {exc}") from exc
    return {}


def _load_searches() -> dict:
    if config.SEARCH_CONFIG_PATH.exists():
        try:
            return yaml.safe_load(config.SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(500, f"searches.yaml is not valid YAML: {exc}") from exc
    return {}


def _pick(src: dict, keys: list[str]) -> dict:
    return {k: src.get(k) for k in keys}


def _write_json(data: dict) -> None:
    path = config.PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)  # PII — mirror CLI file permissions
    except OSError:
        pass


def _write_searches(data: dict) -> None:
    path = config.SEARCH_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


@router.get("")
def get_settings(request: Request) -> dict:
    user_id = resolve_dashboard_user(request)
    user = get_user(user_id)
    profile = _load_profile()
    searches = _load_searches()
    defaults = searches.get("defaults") or {}

    resume_text = ""
    if config.RESUME_PATH.exists():
        resume_text = config.RESUME_PATH.read_text(encoding="utf-8")

    display_name = (
        (user.name if user else None)
        or (profile.get("personal") or {}).get("full_name")
        or user_id
    )

    return {
        "user_id": user_id,
        "name": display_name,
        "profile": {
            section: _pick(profile.get(section) or {}, keys)
            for section, keys in _PROFILE_SECTIONS
        },
        "searches": {
            "queries": searches.get("queries") or [],
            "locations": searches.get("locations") or [],
            "boards": searches.get("boards") or [],
            "exclude_titles": searches.get("exclude_titles") or [],
            "min_salary": searches.get("min_salary"),
            "hours_old": defaults.get("hours_old"),
            "results_per_site": defaults.get("results_per_site"),
        },
        "resume": resume_text,
    }


class ProfileSettings(BaseModel):
    personal: dict[str, Any] | None = None
    compensation: dict[str, Any] | None = None
    experience: dict[str, Any] | None = None
    job_preferences: dict[str, Any] | None = None


@router.put("/profile")
def put_profile(body: ProfileSettings) -> dict:
    profile = _load_profile()
    incoming = body.model_dump(exclude_none=True)
    for section, allowed in _PROFILE_SECTIONS:
        data = incoming.get(section)
        if not data:
            continue
        current = profile.setdefault(section, {})
        for key in allowed:
            if key in data:
                current[key] = data[key]
    _write_json(profile)
    return {"ok": True}


class SearchSettings(BaseModel):
    queries: list[dict[str, Any]] | None = None
    locations: list[dict[str, Any]] | None = None
    boards: list[str] | None = None
    exclude_titles: list[str] | None = None
    min_salary: int | None = None
    hours_old: int | None = None
    results_per_site: int | None = None


@router.put("/searches")
def put_searches(body: SearchSettings) -> dict:
    searches = _load_searches()
    incoming = body.model_dump(exclude_unset=True)
    for key in ("queries", "locations", "boards", "exclude_titles", "min_salary"):
        if key in incoming:
            searches[key] = incoming[key]
    defaults = searches.setdefault("defaults", {})
    for key in ("hours_old", "results_per_site"):
        if incoming.get(key) is not None:
            defaults[key] = incoming[key]
    _write_searches(searches)
    return {"ok": True}


class ResumeSettings(BaseModel):
    text: str


@router.put("/resume")
def put_resume(body: ResumeSettings) -> dict:
    path = config.RESUME_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.text, encoding="utf-8")
    return {"ok": True}
