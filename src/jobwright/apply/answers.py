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
start date, relocation, on-site, located in the country, travel, previous
employment at the employer) are answered ONLY from this bank. Missing = the
job is skipped and the question is reported; nothing is inferred from the
resume or defaulted.

Three kinds of form questions (``ANSWER_POLICY``, handed to the person's
Claude in every application packet): saved answers only (attestations and
contact facts), from the resume truthfully (education, years of experience,
people managed, budgets, sectors, employers), and open writing.
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
SOURCES = ("settings", "cli", "whatsapp", "profile", "api", "connector", "resume", "told_claude")


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
    AnswerSpec("currently_in_country", "Currently located in the country of the job", "location", True,
               choices=_YES_NO, hint="Forms ask \"Are you currently located in the US?\""),
    AnswerSpec("willing_to_travel", "Willing to travel for work (how much)", "travel", True,
               hint="e.g. Up to 25%, or No"),
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
    AnswerSpec("privacy_consent", "OK to accept a candidate privacy notice / data-transfer consent", "consent",
               True, choices=_YES_NO, hint="Many forms require ticking it to apply. Yes lets jobwright tick it."),
    # --- Common fields (AI may not invent these either; they are facts) ----
    AnswerSpec("phone", "Phone", "common", False),
    AnswerSpec("address_line", "Street address", "common", False),
    AnswerSpec("city", "City", "common", False),
    AnswerSpec("state", "State / province", "common", False),
    AnswerSpec("postal_code", "Postal code / ZIP", "common", False),
    AnswerSpec("country", "Country", "common", False),
    AnswerSpec("linkedin_url", "LinkedIn URL", "common", False, required=False),
    AnswerSpec("github_url", "GitHub URL", "common", False, required=False),
    AnswerSpec("portfolio_url", "Portfolio / website URL", "common", False, required=False),
    AnswerSpec("education_highest", "Highest education (degree, school, year)", "common", False, required=False,
               hint="Optional: your Claude can take it from your resume"),
    AnswerSpec("how_heard", "How did you hear about us", "common", False,
               hint="Your default when a form asks, e.g. Company website"),
    # Experience as numbers, so "how many years of ..." range questions are exact, not judgment calls.
    AnswerSpec("years_experience", "Years of relevant work experience (number)", "common", False, required=False,
               hint="A number, e.g. 9. Your Claude can take it from your resume"),
    AnswerSpec("years_leadership", "Years in leadership roles (number)", "common", False, required=False,
               hint="A number, e.g. 6"),
    AnswerSpec("years_managing", "Years managing or supervising people (number)", "common", False,
               required=False, hint="A number, e.g. 5"),
    AnswerSpec("largest_team", "Most people you have managed at once (number)", "common", False,
               required=False, hint="A number, e.g. 8"),
    AnswerSpec("referral", "Referred by an employee", "common", False, required=False, choices=_YES_NO),
    AnswerSpec("notice_period", "Notice period", "common", False, required=False),
    AnswerSpec("pronouns", "Pronouns (optional)", "common", False, required=False),
    AnswerSpec("preferred_name", "Preferred name (optional)", "common", False, required=False),
)

SPEC_BY_KEY: dict[str, AnswerSpec] = {s.key: s for s in SPECS}
ATTESTATION_KEYS = tuple(s.key for s in SPECS if s.attestation)
ATTESTATION_CATEGORIES = tuple(dict.fromkeys(s.category for s in SPECS if s.attestation))

# Contact keys live in ``profile.json`` ``personal`` (the fields Settings → About you shows), never as a
# second copy in the bank: the bank keeps only their provenance (source, updated_at, previous value).
CONTACT_FIELDS: dict[str, str] = {
    "phone": "phone",
    "address_line": "address",
    "city": "city",
    "state": "province_state",
    "postal_code": "postal_code",
    "country": "country",
    "linkedin_url": "linkedin_url",
    "github_url": "github_url",
    "portfolio_url": "portfolio_url",
    "preferred_name": "preferred_name",
}
_PROFILE_SEED = {k: ("personal", f) for k, f in CONTACT_FIELDS.items()}  # legacy name

# Settings → About you → Application details: sections in display order ("other" also holds the
# questions forms asked, the custom answers).
SECTIONS: tuple[tuple[str, str], ...] = (
    ("contact", "Contact and address"),
    ("education", "Education"),
    ("eligibility", "Work eligibility"),
    ("experience", "Experience"),
    ("pay_start", "Pay and start date"),
    ("diversity", "Diversity questions (optional)"),
    ("other", "Other questions forms asked"),
)
_SECTION_OF: dict[str, str] = {
    **{k: "contact" for k in CONTACT_FIELDS}, "pronouns": "contact",
    "education_highest": "education",
    **{k: "eligibility" for k in ("work_authorized", "requires_sponsorship", "currently_in_country", "relocation",
                                  "onsite", "willing_to_travel", "criminal_record", "background_check",
                                  "age_18_plus", "certify", "previously_worked_here", "privacy_consent")},
    **{k: "experience" for k in ("years_experience", "years_leadership", "years_managing", "largest_team")},
    **{k: "pay_start" for k in ("salary_expectation", "start_date", "notice_period")},
    **{s.key: "diversity" for s in SPECS if s.category == "eeo"},
    "how_heard": "other", "referral": "other",
}


def section_of(key: str) -> str:
    return _SECTION_OF.get(key, "other")


# Where a saved value came from (shown as a small label next to each answer).
CLAUDE_SOURCES = ("resume", "told_claude", "connector")
RECENT_DAYS = 14


def source_label(source: str | None) -> str:
    if source == "resume":
        return "From your resume"
    if source in ("told_claude", "connector"):
        return "You told Claude"
    return "You entered"


# ---------------------------------------------------------------------------
# Question classification (keyword layer; the agent adds its own judgment)
# ---------------------------------------------------------------------------

# Order matters: the first matching category wins ("require sponsorship to
# work" is sponsorship, not work authorization).
_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("consent", re.compile(
        r"privacy (notice|policy|statement)|data[- ](transfer|processing|protection)|candidate privacy|"
        r"consent to (the )?(processing|transfer|collection)|\bgdpr\b|i (accept|agree)\b.{0,60}"
        r"(privacy|personal data|data)", re.I)),
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
        r"salary|compensation (expectation|requirement)s?|expected (pay|compensation)|desired (pay|salary|"
        r"compensation|wage|rate)|pay (expectation|requirement)s?|expected base|rate expectation|"
        r"(hourly|base) (rate|pay) (expect|requir)", re.I)),
    ("start_date", re.compile(
        r"start date|when can you start|available to start|earliest (start|date)|availability to (begin|start)|"
        r"date (you are |you're )?available|availability date|notice before starting", re.I)),
    # "Are you currently located in the US?" (before relocation: "located in or relocating to ...")
    ("location", re.compile(
        r"\b(currently |presently )?(located|reside|residing|live|living|based) in\b", re.I)),
    ("travel", re.compile(
        r"\b(willing|able|open|comfortable|available)\b.{0,40}\btravel|\btravel\b.{0,40}"
        r"(%|percent|required|requirement|willing|able)", re.I)),
    ("relocation", re.compile(r"relocat|\b(on-?site|in[- ]office|in[- ]person|hybrid)\b.{0,40}\b(work|able|willing|days?)\b|"
                              r"\bcommut", re.I)),
    ("previous_employment", re.compile(
        r"previously (worked|been employed)|former employee|worked (here|for us|for this company|at \w+) "
        r"(before|previously)|ever (been )?(employed|worked) (by|for|at)|current or former employee|"
        r"have you (ever )?worked (for|at)", re.I)),
)

_WH_QUESTION = re.compile(r"^\W*(what|which|where|list|enter|city|state|country|zip|postal)\b", re.I)

_EEO_KEYS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"hispanic|latin[oax]", re.I), "eeo_hispanic"),
    (re.compile(r"sexual orientation|lgbt", re.I), "eeo_lgbtq"),
    (re.compile(r"\bgender\b|\bsex\b|transgender", re.I), "eeo_gender"),
    (re.compile(r"\brace\b|ethnicit", re.I), "eeo_race"),
    (re.compile(r"veteran", re.I), "eeo_veteran"),
    (re.compile(r"disabilit|disabled", re.I), "eeo_disability"),
)

_CATEGORY_KEY = {
    "consent": "privacy_consent",
    "work_authorization": "work_authorized",
    "sponsorship": "requires_sponsorship",
    "age": "age_18_plus",
    "certification": "certify",
    "salary": "salary_expectation",
    "start_date": "start_date",
    "relocation": "relocation",
    "previous_employment": "previously_worked_here",
    "travel": "willing_to_travel",
}

# "located in the United States / the US / the country": the standard key. A
# question naming states or cities ("located in or relocating to California")
# stays a custom attestation the person answers once.
_COUNTRY_WORDS = re.compile(
    r"\b(u\.?s\.?a?|united states|america|the country|this country|country of)\b|"
    r"\bin the (uk|united kingdom|eu|european union)\b|\bcanada\b|\bindia\b", re.I)
_PLACE_WORDS = re.compile(
    r"\b(state|city|county|province|area|region|california|alaska|hawaii|new york|texas|washington)\b|"
    r"\b(or|and) relocat", re.I)

_COMMON_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"phone|mobile|telephone", re.I), "phone"),
    (re.compile(r"linkedin", re.I), "linkedin_url"),
    (re.compile(r"github", re.I), "github_url"),
    (re.compile(r"portfolio|personal (web)?site|website", re.I), "portfolio_url"),
    (re.compile(r"\breferr(ed|al)\b(?!.*source)", re.I), "referral"),
    (re.compile(r"how did you (hear|find|learn)|where did you (hear|find)|referral source|source of application",
                re.I), "how_heard"),
    (re.compile(r"notice period", re.I), "notice_period"),
    (re.compile(r"(how many|largest|number of)\b.{0,30}\b(people|direct reports|employees|team members|staff)"
                r"\b.{0,30}\b(manag|supervis|lead)|team size", re.I), "largest_team"),
    (re.compile(r"years?\b.{0,40}\b(manag|supervis)\w*\b.{0,20}\b(people|staff|team|others|employees|"
                r"direct reports)|years?\b.{0,30}\b(people management|supervisory)", re.I), "years_managing"),
    (re.compile(r"years?\b.{0,40}\b(leadership|leading|senior leader|executive)", re.I), "years_leadership"),
    (re.compile(r"years? of (relevant |professional |related |work )?experience|how many years", re.I),
     "years_experience"),
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
            if category == "location" and _WH_QUESTION.search(t):
                continue  # "What city do you live in?" is a contact fact, not a yes/no attestation
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
    if category == "location":
        if _COUNTRY_WORDS.search(t) and not _PLACE_WORDS.search(t):
            return "currently_in_country"
        return None
    if category:
        return _CATEGORY_KEY.get(category)
    for pattern, key in _COMMON_PATTERNS:
        if pattern.search(t):
            return key
    return None


# Questions the resume answers (Claude answers them truthfully from it, source "resume").
_RESUME_PATTERNS = re.compile(
    r"\byears? (of|supervising|managing|leading|working|in)\b|\bhow many years\b|\bexperience (in|with|working)\b|"
    r"\bhighest (level|degree)\b|\b(degree|education|school|university|college|gpa|major|graduat)|"
    r"\b(supervis|managed|direct reports?|people manager|team size|led a team)|\bbudget|\bstrategic planning\b|"
    r"\b(non-?profit|government|public sector)s?\b|\b(most recent|current|previous) (employer|job title|title|"
    r"position)\b|\bemployment history\b|\blanguages? (do you )?speak\b|\bproficien", re.I)


def question_kind(text: str, model_category: str | None = None) -> str:
    """Who answers a form question: ``saved`` (attestation: the person's saved answer only), ``contact``
    (saved contact fact), ``resume`` (Claude, truthfully from the resume) or ``open`` (Claude writes it)."""
    if is_attestation(text, model_category):
        return "saved"
    key = key_for_question(text)
    if key == "education_highest" or _RESUME_PATTERNS.search(" ".join((text or "").split())):
        return "resume"
    if key:
        return "contact"
    return "open"


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


def _previous(raw: Any) -> dict | None:
    if isinstance(raw, dict) and str(raw.get("value") or "").strip():
        return {"value": str(raw["value"]).strip(), "source": str(raw.get("source") or "settings"),
                "updated_at": str(raw.get("updated_at") or "")}
    return None


def _clean_bank(raw: Any) -> dict:
    bank = _empty_bank()
    if not isinstance(raw, dict):
        return bank
    for key, entry in (raw.get("answers") or {}).items():
        if key not in SPEC_BY_KEY or not isinstance(entry, dict):
            continue
        value = str(entry.get("value") or "").strip()
        if not value and not (key in CONTACT_FIELDS and entry.get("in_profile")):
            continue
        clean = {"source": str(entry.get("source") or "settings"), "updated_at": str(entry.get("updated_at") or "")}
        if key in CONTACT_FIELDS and entry.get("in_profile"):
            clean["in_profile"] = True
        else:
            clean["value"] = value
        if "previous" in entry:
            clean["previous"] = _previous(entry.get("previous"))
        bank["answers"][key] = clean
    for norm, entry in (raw.get("custom") or {}).items():
        if isinstance(entry, dict) and str(entry.get("value") or "").strip():
            clean = {
                "question": str(entry.get("question") or norm),
                "value": str(entry["value"]).strip(),
                "source": str(entry.get("source") or "whatsapp"),
                "updated_at": str(entry.get("updated_at") or ""),
            }
            if "previous" in entry:
                clean["previous"] = _previous(entry.get("previous"))
            bank["custom"][str(norm)] = clean
    return bank


def _personal_value(profile: dict, key: str) -> str | None:
    value = str(((profile or {}).get("personal") or {}).get(CONTACT_FIELDS[key]) or "").strip()
    if not value and key == "portfolio_url":
        value = str(((profile or {}).get("personal") or {}).get("website_url") or "").strip()
    return value or None


class AnswerBank:
    """In-memory view of one person's answers (load with ``load_answers``).

    Contact keys (``CONTACT_FIELDS``) read through to ``profile.personal``; an old bank copy is only a
    fallback until the next write moves it there.
    """

    def __init__(self, data: dict | None = None, profile: dict | None = None) -> None:
        self.data = _clean_bank(data)
        self.profile = profile or {}

    # -- reads --------------------------------------------------------------
    def get(self, key: str) -> str | None:
        entry = self.data["answers"].get(key)
        if key in CONTACT_FIELDS:
            return _personal_value(self.profile, key) or (entry.get("value") if entry else None)
        return entry["value"] if entry else None

    def entry(self, key: str) -> dict | None:
        value = self.get(key)
        if value is None:
            return None
        meta = self.data["answers"].get(key) or {"source": "settings", "updated_at": ""}
        return {**{k: v for k, v in meta.items() if k != "in_profile"}, "value": value}

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

    def answers_view(self) -> dict[str, dict]:
        """Every saved standard answer, ``{key: {value, source, updated_at, previous?}}``."""
        out: dict[str, dict] = {}
        for spec in SPECS:
            entry = self.entry(spec.key)
            if entry:
                out[spec.key] = entry
        return out

    def as_filler_dict(self) -> dict:
        """The ``answers`` dict the deterministic ATS fillers take (apply/ats/forms.py)."""
        out: dict = {k: e["value"] for k, e in self.answers_view().items()}
        out["questions"] = {e["question"]: e["value"] for e in self.data["custom"].values()}
        return out

    def recent_by_claude(self, days: int = RECENT_DAYS) -> list[dict]:
        """Values the person's Claude saved in the last ``days`` days, newest first (with Undo info)."""
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        out: list[dict] = []
        for key, entry in self.answers_view().items():
            if entry.get("source") in CLAUDE_SOURCES and entry.get("updated_at", "") >= since:
                prev = entry.get("previous")
                out.append({"key": key, "label": SPEC_BY_KEY[key].label, "value": entry["value"],
                            "source": entry["source"], "updated_at": entry["updated_at"],
                            "previous_value": prev["value"] if prev else None})
        for norm, entry in self.data["custom"].items():
            if entry.get("source") in CLAUDE_SOURCES and entry.get("updated_at", "") >= since:
                prev = entry.get("previous")
                out.append({"question": entry["question"], "label": entry["question"], "value": entry["value"],
                            "source": entry["source"], "updated_at": entry["updated_at"],
                            "previous_value": prev["value"] if prev else None})
        return sorted(out, key=lambda r: r["updated_at"], reverse=True)

    def as_public_dict(self) -> dict:
        answers = self.answers_view()
        return {
            "version": SCHEMA_VERSION,
            "answers": {k: {**e, "source_label": source_label(e.get("source"))} for k, e in answers.items()},
            "custom": {n: {**e, "source_label": source_label(e.get("source"))}
                       for n, e in self.data["custom"].items()},
            "fields": [
                {"key": s.key, "label": s.label, "category": s.category, "attestation": s.attestation,
                 "required": s.required, "hint": s.hint, "choices": list(s.choices), "section": section_of(s.key)}
                for s in SPECS
            ],
            "sections": [{"id": sid, "title": title} for sid, title in SECTIONS],
            "missing": [s.key for s in self.missing()],
            "recent": self.recent_by_claude(),
        }


_MONEY = re.compile(r"([$£€₹]|usd|eur|gbp|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|K|thousand)?", re.I)
_CURRENCY = {"$": "USD", "usd": "USD", "£": "GBP", "gbp": "GBP", "€": "EUR", "eur": "EUR", "₹": "INR", "inr": "INR"}


def structured_salary(text: str) -> dict | None:
    """Numbers forms need from a pay answer: {"min", "max", "number", "currency", "period"} (None = no number).
    "number" is what to type in a single numeric box: the range midpoint, or the floor for "above X"."""
    t = (text or "").strip()
    nums: list[float] = []
    currency = None
    for sym, num, k in _MONEY.findall(t):
        value = float(num.replace(",", ""))
        if k:
            value *= 1000
        if value < 1000 and not re.search(r"hour|/hr|\bhr\b", t, re.I):
            continue
        nums.append(value)
        currency = currency or _CURRENCY.get(sym.lower()) if sym else currency
    if not nums:
        return None
    period = "hour" if re.search(r"hour|/hr|\bhr\b", t, re.I) else "year"
    lo, hi = min(nums), max(nums)
    above = re.search(r"\b(above|over|at least|minimum|min|from|\+)", t, re.I) and len(nums) == 1
    out = {"min": int(lo), "max": None if above else int(hi), "currency": currency or "USD", "period": period}
    if above or lo == hi:
        out["number"] = int(lo)
    else:
        # Annual midpoints read better rounded to the nearest 1000; an hourly rate rounded that way
        # would collapse to 0, so keep it to the dollar.
        midpoint = (lo + hi) / 2
        out["number"] = int(round(midpoint, -3)) if period == "year" else int(round(midpoint))
    return out


_WEEKS = re.compile(r"(\d+|one|two|three|four|six|eight)\s*(week|wk)s?", re.I)
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "eight": 8}


def structured_start(text: str, today: datetime | None = None) -> dict | None:
    """A start-date answer as {"date": ISO or None, "rule": ...}: forms with a date picker get a date."""
    from datetime import timedelta

    t = (text or "").strip()
    if not t:
        return None
    today = (today or datetime.now(timezone.utc)).date()
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        return {"date": m.group(0), "rule": "fixed date"}
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d %B %Y"):
        try:
            return {"date": datetime.strptime(t, fmt).date().isoformat(), "rule": "fixed date"}
        except ValueError:
            pass
    if re.search(r"\b(immediately|asap|right away|now)\b", t, re.I):
        return {"date": (today + timedelta(days=7)).isoformat(), "rule": "immediately (date = a week from today)"}
    w = _WEEKS.search(t)
    if w:
        n = int(w.group(1)) if w.group(1).isdigit() else _WORD_NUM[w.group(1).lower()]
        return {"date": (today + timedelta(weeks=n)).isoformat(),
                "rule": f"{n} weeks after an offer (date = {n} weeks from today)"}
    return {"date": None, "rule": t}


def structured_value(key: str, value: str | None) -> dict | None:
    """Machine-friendly form of a saved answer, for numeric / date / choice fields."""
    if not value:
        return None
    if key == "salary_expectation":
        return structured_salary(value)
    if key == "start_date":
        return structured_start(value)
    if key in ("years_experience", "years_leadership", "years_managing", "largest_team"):
        m = re.search(r"\d+(?:\.\d+)?", value)
        return {"number": float(m.group(0)) if "." in m.group(0) else int(m.group(0))} if m else None
    return None


def load_answers() -> AnswerBank:
    profile = _read_profile()
    return AnswerBank(profile.get("application_answers"), profile=profile)


def clean_value(key: str, text: str) -> str:
    """A saved value as forms need it: a choice question keeps just the choice ("No, never" -> "No")."""
    text = " ".join((text or "").split())
    spec = SPEC_BY_KEY.get(key)
    if text and spec and spec.choices:
        hit = match_option(text, list(spec.choices))
        if hit:
            return hit
    return text


def _store_value(profile: dict, bank: dict, key: str, text: str, source: str, now: str) -> None:
    """Write one standard answer (``text`` empty clears it), keeping the value it replaced for Undo."""
    text = clean_value(key, text)
    old_view = AnswerBank(bank, profile=profile)
    old_value = old_view.get(key)
    old_meta = bank["answers"].get(key) or {}
    if key in CONTACT_FIELDS:
        personal = profile.setdefault("personal", {})
        if text:
            personal[CONTACT_FIELDS[key]] = text
        else:
            personal.pop(CONTACT_FIELDS[key], None)
    if not text:
        bank["answers"].pop(key, None)
        return
    if old_value == text and old_meta:
        return  # same value: keep its provenance and Undo state
    entry: dict = {"source": source, "updated_at": now}
    entry["previous"] = ({"value": old_value, "source": old_meta.get("source") or "settings",
                          "updated_at": old_meta.get("updated_at") or ""} if old_value else None)
    if key in CONTACT_FIELDS:
        entry["in_profile"] = True
    else:
        entry["value"] = text
    bank["answers"][key] = entry


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
            _store_value(profile, bank, key, text, source, now)
        profile["application_answers"] = bank
        _write_profile(profile)
    return AnswerBank(bank, profile=profile)


def set_custom_answer(question: str, value: str, source: str = "whatsapp") -> AnswerBank:
    """Save an answer to one specific form question (e.g. from a pending input). One entry per normalized
    question: the same question in other words updates it, never adds a second."""
    norm = normalize_question(question)
    if not norm:
        raise ValueError("Empty question")
    with _profile_lock():
        profile = _read_profile()
        bank = _clean_bank(profile.get("application_answers"))
        text = (value or "").strip()
        old = bank["custom"].get(norm)
        if text:
            if not (old and old["value"] == text[:2000]):
                bank["custom"][norm] = {"question": question.strip()[:500], "value": text[:2000],
                                        "source": source, "updated_at": _now(), "previous": _previous(old)}
        else:
            bank["custom"].pop(norm, None)
        profile["application_answers"] = bank
        _write_profile(profile)
    return AnswerBank(bank, profile=profile)


def note_profile_edit(personal_keys: list[str]) -> None:
    """Settings → About you changed these ``personal`` fields: their answers now say "You entered"."""
    keys = [k for k, f in CONTACT_FIELDS.items() if f in personal_keys]
    if not keys:
        return
    with _profile_lock():
        profile = _read_profile()
        bank = _clean_bank(profile.get("application_answers"))
        changed = False
        for key in keys:
            entry = bank["answers"].get(key)
            if entry and entry.get("source") != "settings":
                entry.update({"source": "settings", "updated_at": _now(), "previous": None})
                changed = True
        if changed:
            profile["application_answers"] = bank
            _write_profile(profile)


def undo_answer(*, key: str | None = None, question: str | None = None) -> AnswerBank:
    """Put back the value an answer replaced (or remove it when it replaced nothing)."""
    if bool(key) == bool(question):
        raise ValueError("Give key or question")
    if key and key not in SPEC_BY_KEY:
        raise ValueError(f"Unknown answer key {key!r}")
    with _profile_lock():
        profile = _read_profile()
        bank = _clean_bank(profile.get("application_answers"))
        if key:
            entry = bank["answers"].get(key)
            if entry is None:
                raise LookupError("Nothing to undo for that answer")
            prev = entry.get("previous")
            if key in CONTACT_FIELDS:
                personal = profile.setdefault("personal", {})
                if prev:
                    personal[CONTACT_FIELDS[key]] = prev["value"]
                else:
                    personal.pop(CONTACT_FIELDS[key], None)
            if prev:
                restored = {"source": prev["source"], "updated_at": prev["updated_at"], "previous": None}
                if key in CONTACT_FIELDS:
                    restored["in_profile"] = True
                else:
                    restored["value"] = prev["value"]
                bank["answers"][key] = restored
            else:
                bank["answers"].pop(key, None)
        else:
            norm = normalize_question(question or "")
            entry = bank["custom"].get(norm)
            if entry is None:
                raise LookupError("Nothing to undo for that question")
            prev = entry.get("previous")
            if prev:
                bank["custom"][norm] = {"question": entry["question"], "value": prev["value"],
                                        "source": prev["source"], "updated_at": prev["updated_at"], "previous": None}
            else:
                bank["custom"].pop(norm, None)
        profile["application_answers"] = bank
        _write_profile(profile)
    return AnswerBank(bank, profile=profile)


def seed_from_profile() -> dict[str, str]:
    """Move contact facts an older version kept in the bank into ``profile.personal`` (never attestations).

    Contact keys read from ``personal`` directly now, so there is nothing to copy the other way.
    """
    profile = _read_profile()
    raw = (profile.get("application_answers") or {}).get("answers") or {}
    moved = {k: str(e.get("value") or "").strip() for k, e in raw.items()
             if k in CONTACT_FIELDS and isinstance(e, dict) and str(e.get("value") or "").strip()
             and not _personal_value(profile, k)}
    if moved:
        set_answers(moved, source="profile")
    return moved


JOB_SPECIFIC = re.compile(
    r"\bwhy (do you|are you|would you|this|our|us|here|join|work|apply|the)\b|\bwhat (interests|excites|draws|"
    r"attracts) you\b|\binterest(ed)? in (this|our|the) (role|company|position|team|job)\b|\bcover letter\b|"
    r"\btell us (about|why)\b|\bdescribe (a|an|your|how|the|one)\b|\bwhat would you\b|\bhow would you\b|"
    r"\bwhy should we\b|\banything else\b|\badditional information\b", re.I)


def is_job_specific(text: str) -> bool:
    """An open question written for one employer ("why this company"): never saved as a general answer."""
    return bool(JOB_SPECIFIC.search(" ".join((text or "").split())))


# Different wordings of the same answer across forms (EEO and consent wording varies by ATS).
_SAME_MEANING: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("decline", re.compile(r"\b(decline|prefer not|do not wish|don ?t wish|do not want|don ?t want|choose not|"
                           r"rather not|not to (say|answer|disclose|identify)|wish not)\b", re.I)),
    ("not_veteran", re.compile(r"\b(not a (protected )?veteran|i am not a( protected)? veteran|non[- ]?veteran|"
                               r"not (a )?protected veteran|no military)\b", re.I)),
    ("veteran", re.compile(r"^(?!.*\bnot\b).*\b(protected veteran|identify as (one or more|a) .*veteran|"
                           r"i am a veteran)\b", re.I)),
    ("no_disability", re.compile(r"\bno\b.{0,30}\b(do not|don ?t) have a disability|"
                                 r"\bnot (have )?(a )?disab|^no disability", re.I)),
    ("disability", re.compile(r"^(?!.*\b(no|not|don ?t|do not)\b).*\b(yes\b.{0,30}disabilit|"
                              r"i have a disability|have had one)", re.I)),
    ("not_hispanic", re.compile(r"\bnot hispanic|\bno\b.{0,20}\bhispanic|non[- ]hispanic", re.I)),
    ("male", re.compile(r"^(male|man|cisgender man|cis man)$", re.I)),
    ("female", re.compile(r"^(female|woman|cisgender woman|cis woman)$", re.I)),
)


def same_meaning(text: str) -> str | None:
    """Which shared meaning a value or option has (None = none known)."""
    t = " ".join((text or "").replace("’", "").replace("'", "").split())
    for name, pattern in _SAME_MEANING:
        if pattern.search(t):
            return name
    return None


def match_option(answer: str, options: list[str]) -> str | None:
    """The option that says the same thing as ``answer`` (None = no safe match)."""
    if not answer:
        return None
    a = normalize_question(answer)
    norm = [(o, normalize_question(o)) for o in options if o and normalize_question(o)]
    for o, n in norm:
        if n == a:
            return o
    meaning = same_meaning(answer)
    if meaning:
        hits = [o for o, _n in norm if same_meaning(o) == meaning]
        if len(hits) == 1:
            return hits[0]
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


# ---------------------------------------------------------------------------
# Facts the person's Claude records (connector save_profile_facts)
# ---------------------------------------------------------------------------

CLAUDE_FACT_SOURCES = ("resume", "told_claude")
_SPECIFIC_MOVE = re.compile(r"\brelocat\w* to\b|\bcommut\w* to\b", re.I)


def fact_key(question: str | None, key: str | None = None) -> str | None:
    """Standard key a fact belongs to: the one Claude named, else the classifier's. A question tied to one
    place ("relocate to Boston?") never lands on the general key."""
    if key:
        if key not in SPEC_BY_KEY:
            raise ValueError(f"Unknown answer key {key!r}")
        return key
    text = " ".join((question or "").split())
    found = key_for_question(text)
    if found and SPEC_BY_KEY[found].attestation and (_PLACE_WORDS.search(text) or _SPECIFIC_MOVE.search(text)):
        return None
    return found


def save_facts(facts: list[dict], *, person_confirmed: bool) -> list[dict]:
    """Save facts from the person's Claude: standard key first, else one "other question" per normalized
    question. Job-specific open answers are refused; attestations need ``person_confirmed`` and never come
    from the resume. Validates everything before writing anything."""
    plan: list[tuple[int, str | None, str, str, str]] = []
    results: list[dict] = [{} for _ in facts]
    blocked: list[str] = []
    for i, f in enumerate(facts):
        question = " ".join(str(f.get("question") or "").split())[:500]
        value = str(f.get("value") or "").strip()
        source = str(f.get("source") or "told_claude")
        if source not in CLAUDE_FACT_SOURCES:
            raise ValueError(f"source must be one of {', '.join(CLAUDE_FACT_SOURCES)}")
        if not value:
            raise ValueError("Every fact needs a value")
        if len(value) > 2000:
            raise ValueError("A value is longer than 2000 characters")
        key = fact_key(question, f.get("key") or None)
        if key is None and len(question) < 3:
            raise ValueError("Give the form's question (or a standard key) for every fact")
        label = question or SPEC_BY_KEY[key].label  # type: ignore[index]
        if key is None and is_job_specific(question):
            results[i] = {"question": label, "status": "not_saved",
                          "reason": "written for one employer; answer it on each form, never as a general answer"}
            continue
        attest = bool(key and SPEC_BY_KEY[key].attestation) or (key is None and is_attestation(question))
        if attest and source == "resume":
            blocked.append(f"{label}: attestations never come from the resume")
        elif attest and not person_confirmed:
            blocked.append(f"{label}: an attestation")
        plan.append((i, key, question, value, source))
    if blocked:
        raise ValueError("Not saved: " + "; ".join(blocked) + ". Ask the person and save their own words with "
                         "person_confirmed=true only after they state it in this conversation (or use ask_person "
                         "when they are not here). Nothing was saved.")
    for i, key, question, value, source in plan:
        if key:
            before = load_answers().get(key)
            set_answers({key: value}, source=source)
            results[i] = {"question": question or SPEC_BY_KEY[key].label, "saved_to": key,
                          "status": "unchanged" if before == value else "saved", "source": source}
        else:
            before = load_answers().custom(question)
            set_custom_answer(question, value, source=source)
            results[i] = {"question": question, "saved_to": "other question",
                          "status": "unchanged" if before == value else "saved", "source": source}
    return results
