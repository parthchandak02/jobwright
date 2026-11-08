"""The person's saved application answers (the "answer bank").

Stored in the user's ``profile.json`` under ``application_answers``::

    "application_answers": {
      "version": 1,
      "answers": {
        "work_authorized": {"value": "Yes", "source": "settings", "updated_at": "2026-11-08T10:00:00+00:00"},
        ...
      },
      "custom": {
        "<normalized question>": {"question": "Do you hold a CPA license?", "value": "No", "source": "whatsapp", "updated_at": "..."}
      }
    }

Why profile.json and not a DB table: the answers are a small, per-person,
human-edited document (like the rest of profile.json), they belong with the
profile when it is backed up, restored or deleted, they need no queries or
history, and every profile.json writer already round-trips unknown keys.

Owner rule: ATTESTATIONS (work authorization, sponsorship, criminal history /
background check, EEO / demographics, age, "I certify", salary expectation,
start date, relocation, previous employment at the employer) are answered ONLY
from this bank. Missing = the job is skipped and the question is reported;
nothing is inferred from the resume or defaulted.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from jobwright import config

SCHEMA_VERSION = 1
SOURCES = ("settings", "cli", "whatsapp", "profile", "api", "connector")


@dataclass(frozen=True)
class AnswerSpec:
    key: str
    label: str
    category: str  # attestation category, or "common"
    attestation: bool
    required: bool = True  # counted by `answers missing`
    hint: str = ""
    choices: tuple[str, ...] = ()


_YES_NO = ("Yes", "No")

SPECS: tuple[AnswerSpec, ...] = (
    # --- Attestations: only ever answered from here -----------------------
    AnswerSpec("work_authorized", "Legally authorized to work in the country of the job", "work_authorization", True,
               choices=_YES_NO),
    AnswerSpec("requires_sponsorship", "Will need visa sponsorship now or in the future", "sponsorship", True,
               choices=_YES_NO),
    AnswerSpec("criminal_record", "Ever convicted of a felony / crime (as asked by forms)", "criminal_background", True,
               choices=_YES_NO),
    AnswerSpec("background_check", "Willing to undergo a background check", "criminal_background", True,
               choices=_YES_NO),
    AnswerSpec("age_18_plus", "At least 18 years old", "age", True, choices=_YES_NO),
    AnswerSpec("certify", "Allowed to tick \"I certify the information is true\"", "certification", True,
               choices=_YES_NO, hint="Yes lets jobwright tick the certification box on your behalf."),
    AnswerSpec("salary_expectation", "Salary expectation (as you want it written)", "salary", True,
               hint="e.g. 120,000 USD per year, or \"Open to discussing\""),
    AnswerSpec("start_date", "Earliest start date / availability", "start_date", True,
               hint="e.g. Two weeks after an offer"),
    AnswerSpec("relocation", "Willing to relocate", "relocation", True, choices=_YES_NO),
    AnswerSpec("previously_worked_here", "Worked for this employer before (most people: No)",
               "previous_employment", True, choices=_YES_NO,
               hint="Jobs at an employer you worked for are better applied to by hand."),
    AnswerSpec("onsite", "Able to work on-site / hybrid when the job asks", "relocation", True,
               choices=_YES_NO),
    AnswerSpec("eeo_gender", "Gender (EEO, voluntary)", "eeo", True,
               hint="Write exactly what to select, or \"Decline to self-identify\""),
    AnswerSpec("eeo_race", "Race / ethnicity (EEO, voluntary)", "eeo", True,
               hint="Write exactly what to select, or \"Decline to self-identify\""),
    AnswerSpec("eeo_hispanic", "Hispanic or Latino (EEO, voluntary)", "eeo", True,
               hint="Yes / No / Decline to self-identify"),
    AnswerSpec("eeo_veteran", "Veteran status (EEO, voluntary)", "eeo", True,
               hint="e.g. I am not a protected veteran / Decline to self-identify"),
    AnswerSpec("eeo_disability", "Disability status (EEO, voluntary)", "eeo", True,
               hint="e.g. No, I do not have a disability / I do not want to answer"),
    AnswerSpec("eeo_lgbtq", "Sexual orientation (EEO, voluntary)", "eeo", True,
               required=False, hint="Only some forms ask; leave empty to skip those jobs"),
    # --- Common fields (AI may not invent these either; they are facts) ----
    AnswerSpec("phone", "Phone", "common", False),
    AnswerSpec("address_line", "Street address", "common", False, required=False),
    AnswerSpec("city", "City", "common", False),
    AnswerSpec("state", "State / province", "common", False),
    AnswerSpec("postal_code", "Postal code", "common", False, required=False),
    AnswerSpec("country", "Country", "common", False),
    AnswerSpec("linkedin_url", "LinkedIn URL", "common", False, required=False),
    AnswerSpec("github_url", "GitHub URL", "common", False, required=False),
    AnswerSpec("portfolio_url", "Portfolio / website URL", "common", False, required=False),
    AnswerSpec("education_highest", "Highest education (degree, school, year)", "common", False),
    AnswerSpec("how_heard", "How did you hear about us", "common", False, hint="e.g. Company website"),
    AnswerSpec("referral", "Referred by an employee", "common", False, required=False, choices=_YES_NO),
    AnswerSpec("notice_period", "Notice period", "common", False, required=False),
    AnswerSpec("pronouns", "Pronouns (optional)", "common", False, required=False),
    AnswerSpec("preferred_name", "Preferred name (optional)", "common", False, required=False),
)

SPEC_BY_KEY: dict[str, AnswerSpec] = {s.key: s for s in SPECS}
ATTESTATION_KEYS = tuple(s.key for s in SPECS if s.attestation)
ATTESTATION_CATEGORIES = tuple(dict.fromkeys(s.category for s in SPECS if s.attestation))

# Profile fields that can seed common answers (`answers import-profile`).
_PROFILE_SEED = {
    "phone": ("personal", "phone"),
    "address_line": ("personal", "address"),
    "city": ("personal", "city"),
    "state": ("personal", "province_state"),
    "postal_code": ("personal", "postal_code"),
    "country": ("personal", "country"),
    "linkedin_url": ("personal", "linkedin_url"),
    "github_url": ("personal", "github_url"),
    "portfolio_url": ("personal", "portfolio_url"),
}


# ---------------------------------------------------------------------------
# Question classification (keyword layer; the agent adds its own judgment)
# ---------------------------------------------------------------------------

# Order matters: the first matching category wins ("require sponsorship to
# work" is sponsorship, not work authorization).
_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("certification", re.compile(
        r"\bi (hereby )?(certify|attest|affirm)\b|\bcertify that\b|\binformation (provided |given )?"
        r"(is|are) (true|accurate|complete)", re.I)),
    ("sponsorship", re.compile(r"sponsor|\bvisa\b|h-?1b|immigration (status|support)", re.I)),
    ("work_authorization", re.compile(
        r"authori[sz](ed|ation) to work|legally (eligible|authori[sz]ed|permitted)|right to work|"
        r"work permit|eligible to work|work authori[sz]ation|employment eligibility", re.I)),
    ("criminal_background", re.compile(
        r"felony|convicted|conviction|criminal|misdemeanou?r|background (check|screen)|pending charges", re.I)),
    ("eeo", re.compile(
        r"\bgender\b|\bsex\b|\brace\b|ethnicit|hispanic|latin[oax]|veteran|disabilit|disabled|"
        r"sexual orientation|transgender|lgbt|self[- ]identify|demographic", re.I)),
    ("age", re.compile(r"\b18\b.*\b(years|older|age)\b|age of 18|\bover 18\b|date of birth|\bhow old\b|"
                       r"\bat least 18\b|legal age", re.I)),
    ("salary", re.compile(
        r"salary|compensation (expectation|requirement)|expected (pay|compensation)|desired (pay|salary|"
        r"compensation)|pay expectation|expected base|rate expectation", re.I)),
    ("start_date", re.compile(
        r"start date|when can you start|available to start|earliest (start|date)|availability to (begin|start)|"
        r"date available|notice before starting", re.I)),
    ("relocation", re.compile(r"relocat|\b(on-?site|in[- ]office|in[- ]person|hybrid)\b.{0,40}\b(work|able|willing|days?)\b|"
                              r"\bcommut", re.I)),
    ("previous_employment", re.compile(
        r"previously (worked|been employed)|former employee|worked (here|for us|for this company|at \w+) "
        r"(before|previously)|ever (been )?(employed|worked) (by|for|at)|current or former employee|"
        r"have you (ever )?worked (for|at)", re.I)),
)

_EEO_KEYS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"hispanic|latin[oax]", re.I), "eeo_hispanic"),
    (re.compile(r"sexual orientation|lgbt", re.I), "eeo_lgbtq"),
    (re.compile(r"\bgender\b|\bsex\b|transgender", re.I), "eeo_gender"),
    (re.compile(r"\brace\b|ethnicit", re.I), "eeo_race"),
    (re.compile(r"veteran", re.I), "eeo_veteran"),
    (re.compile(r"disabilit|disabled", re.I), "eeo_disability"),
)

_CATEGORY_KEY = {
    "work_authorization": "work_authorized",
    "sponsorship": "requires_sponsorship",
    "age": "age_18_plus",
    "certification": "certify",
    "salary": "salary_expectation",
    "start_date": "start_date",
    "relocation": "relocation",
    "previous_employment": "previously_worked_here",
}

_COMMON_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"phone|mobile|telephone", re.I), "phone"),
    (re.compile(r"linkedin", re.I), "linkedin_url"),
    (re.compile(r"github", re.I), "github_url"),
    (re.compile(r"portfolio|personal (web)?site|website", re.I), "portfolio_url"),
    (re.compile(r"\breferr(ed|al)\b(?!.*source)", re.I), "referral"),
    (re.compile(r"how did you (hear|find|learn)|where did you (hear|find)|referral source|source of application",
                re.I), "how_heard"),
    (re.compile(r"notice period", re.I), "notice_period"),
    (re.compile(r"pronoun", re.I), "pronouns"),
    (re.compile(r"preferred (first )?name", re.I), "preferred_name"),
    (re.compile(r"(street )?address( line)?\b(?!.*email)", re.I), "address_line"),
    (re.compile(r"\bcity\b", re.I), "city"),
    (re.compile(r"\bstate\b|province|region", re.I), "state"),
    (re.compile(r"zip|postal", re.I), "postal_code"),
    (re.compile(r"\bcountry\b", re.I), "country"),
    (re.compile(r"(highest )?(level of )?education|degree|university|school", re.I), "education_highest"),
)


def classify_question(text: str) -> str | None:
    """Attestation category for a question/label, or None (keyword layer)."""
    t = " ".join((text or "").split())
    if not t:
        return None
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(t):
            return category
    return None


def key_for_question(text: str, category: str | None = None) -> str | None:
    """Answer-bank key a question maps to (attestation or common field)."""
    t = " ".join((text or "").split())
    category = category or classify_question(t)
    if category == "eeo":
        for pattern, key in _EEO_KEYS:
            if pattern.search(t):
                return key
        return None
    if category == "criminal_background":
        if re.search(r"background (check|screen)", t, re.I) and not re.search(
                r"felony|convicted|conviction|criminal record|charges", t, re.I):
            return "background_check"
        return "criminal_record"
    if category == "relocation" and not re.search(r"relocat", t, re.I):
        return "onsite"
    if category:
        return _CATEGORY_KEY.get(category)
    for pattern, key in _COMMON_PATTERNS:
        if pattern.search(t):
            return key
    return None


def is_attestation(text: str, model_category: str | None = None) -> bool:
    """True when either the keyword list or the model calls it an attestation."""
    if model_category and model_category in ATTESTATION_CATEGORIES:
        return True
    return classify_question(text) is not None


def normalize_question(text: str) -> str:
    t = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    return " ".join(t.split())[:300]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _profile_path() -> Path:
    return Path(config.PROFILE_PATH)


@contextmanager
def _profile_lock() -> Iterator[None]:
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".json.lock"), "a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _read_profile() -> dict:
    path = _profile_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_profile(profile: dict) -> None:
    path = _profile_path()
    fd, tmp = tempfile.mkstemp(prefix=".profile.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _empty_bank() -> dict:
    return {"version": SCHEMA_VERSION, "answers": {}, "custom": {}}


def _clean_bank(raw: Any) -> dict:
    bank = _empty_bank()
    if not isinstance(raw, dict):
        return bank
    for key, entry in (raw.get("answers") or {}).items():
        if key in SPEC_BY_KEY and isinstance(entry, dict) and str(entry.get("value") or "").strip():
            bank["answers"][key] = {
                "value": str(entry["value"]).strip(),
                "source": str(entry.get("source") or "settings"),
                "updated_at": str(entry.get("updated_at") or ""),
            }
    for norm, entry in (raw.get("custom") or {}).items():
        if isinstance(entry, dict) and str(entry.get("value") or "").strip():
            bank["custom"][str(norm)] = {
                "question": str(entry.get("question") or norm),
                "value": str(entry["value"]).strip(),
                "source": str(entry.get("source") or "whatsapp"),
                "updated_at": str(entry.get("updated_at") or ""),
            }
    return bank


class AnswerBank:
    """In-memory view of one person's answers (load with ``load_answers``)."""

    def __init__(self, data: dict | None = None, profile: dict | None = None) -> None:
        self.data = _clean_bank(data)
        self.profile = profile or {}

    # -- reads --------------------------------------------------------------
    def get(self, key: str) -> str | None:
        entry = self.data["answers"].get(key)
        return entry["value"] if entry else None

    def entry(self, key: str) -> dict | None:
        return self.data["answers"].get(key)

    def custom(self, question: str) -> str | None:
        entry = self.data["custom"].get(normalize_question(question))
        return entry["value"] if entry else None

    def lookup(self, question: str, company: str = "", model_category: str | None = None) -> tuple[str | None, str | None]:
        """(key, value) for a form question; value None = not in the bank.

        A custom answer saved for this exact question wins.
        """
        custom = self.custom(question)
        if custom is not None:
            return f"custom:{normalize_question(question)}", custom
        category = model_category if model_category in ATTESTATION_CATEGORIES else None
        key = key_for_question(question, category)
        if key is None:
            return None, None
        return key, self.get(key)

    def missing(self, include_optional: bool = False) -> list[AnswerSpec]:
        return [s for s in SPECS if (s.required or include_optional) and self.get(s.key) is None]

    def missing_attestations(self) -> list[AnswerSpec]:
        return [s for s in SPECS if s.attestation and s.required and self.get(s.key) is None]

    def summary_for_prompt(self) -> str:
        """Plain list for the agent prompt. Contains answers, never secrets."""
        lines = []
        for spec in SPECS:
            value = self.get(spec.key)
            tag = "ATTESTATION" if spec.attestation else "field"
            lines.append(f"- {spec.key} [{tag}] {spec.label}: {value if value is not None else '(NOT SAVED)'}")
        for entry in self.data["custom"].values():
            lines.append(f"- custom [saved answer] {entry['question']}: {entry['value']}")
        return "\n".join(lines)

    def as_filler_dict(self) -> dict:
        """The ``answers`` dict the deterministic ATS fillers take (apply/ats/forms.py)."""
        out: dict = {k: v["value"] for k, v in self.data["answers"].items()}
        out["questions"] = {e["question"]: e["value"] for e in self.data["custom"].values()}
        return out

    def as_public_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "answers": self.data["answers"],
            "custom": self.data["custom"],
            "fields": [
                {"key": s.key, "label": s.label, "category": s.category, "attestation": s.attestation,
                 "required": s.required, "hint": s.hint, "choices": list(s.choices)}
                for s in SPECS
            ],
            "missing": [s.key for s in self.missing()],
        }


def load_answers() -> AnswerBank:
    profile = _read_profile()
    return AnswerBank(profile.get("application_answers"), profile=profile)


def set_answers(values: dict[str, str | None], source: str = "settings") -> AnswerBank:
    """Set (or with ``None`` / empty string, clear) bank keys. Unknown keys raise."""
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}")
    for key in values:
        if key not in SPEC_BY_KEY:
            raise ValueError(f"Unknown answer key {key!r}")
    with _profile_lock():
        profile = _read_profile()
        bank = _clean_bank(profile.get("application_answers"))
        now = _now()
        for key, value in values.items():
            text = "" if value is None else str(value).strip()
            if len(text) > 2000:
                raise ValueError(f"{key}: answer is too long")
            if not text:
                bank["answers"].pop(key, None)
            else:
                bank["answers"][key] = {"value": text, "source": source, "updated_at": now}
        profile["application_answers"] = bank
        _write_profile(profile)
    return AnswerBank(bank, profile=profile)


def set_custom_answer(question: str, value: str, source: str = "whatsapp") -> AnswerBank:
    """Save an answer to one specific form question (e.g. from a pending input)."""
    norm = normalize_question(question)
    if not norm:
        raise ValueError("Empty question")
    with _profile_lock():
        profile = _read_profile()
        bank = _clean_bank(profile.get("application_answers"))
        text = (value or "").strip()
        if text:
            bank["custom"][norm] = {"question": question.strip()[:500], "value": text[:2000],
                                    "source": source, "updated_at": _now()}
        else:
            bank["custom"].pop(norm, None)
        profile["application_answers"] = bank
        _write_profile(profile)
    return AnswerBank(bank, profile=profile)


def seed_from_profile() -> dict[str, str]:
    """Copy common, non-attestation facts from profile.personal (never attestations)."""
    profile = _read_profile()
    bank = AnswerBank(profile.get("application_answers"), profile=profile)
    seeded: dict[str, str] = {}
    for key, (section, field_name) in _PROFILE_SEED.items():
        value = str((profile.get(section) or {}).get(field_name) or "").strip()
        if value and bank.get(key) is None:
            seeded[key] = value
    if seeded:
        set_answers(seeded, source="profile")
    return seeded


def match_option(answer: str, options: list[str]) -> str | None:
    """The option that says the same thing as ``answer`` (None = no safe match)."""
    if not answer:
        return None
    a = normalize_question(answer)
    norm = [(o, normalize_question(o)) for o in options if o and normalize_question(o)]
    for o, n in norm:
        if n == a:
            return o
    yes_no = {"yes": "yes", "y": "yes", "true": "yes", "no": "no", "n": "no", "false": "no"}
    if a in yes_no:
        want = yes_no[a]
        hits = [o for o, n in norm if n.split()[:1] == [want]]
        if len(hits) == 1:
            return hits[0]
    hits = [o for o, n in norm if a and (n.startswith(a) or a.startswith(n))]
    if len(hits) == 1:
        return hits[0]
    hits = [o for o, n in norm if len(a) > 3 and a in n]
    if len(hits) == 1:
        return hits[0]
    return None


def value_agrees(answer: str, typed: str) -> bool:
    """Whether a typed/selected value faithfully carries the saved answer."""
    a, t = normalize_question(answer), normalize_question(typed)
    if not a or not t:
        return False
    if a == t:
        return True
    return match_option(answer, [typed]) == typed
