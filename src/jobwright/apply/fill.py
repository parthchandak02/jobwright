"""Form-filler interface shared by deterministic ATS fillers and the agent.

A deterministic filler (Greenhouse / Lever / Ashby, in ``apply/ats/``) knows
one ATS family's form. The launcher (``apply/runner.py``) asks the registry
for a filler for the job's ATS family first and only falls back to the LLM
agent (``apply/agent.py``) when there is none, or when the filler says it
could not finish (``FillResult.handled is False``).

Contract for a filler::

    class GreenhouseFiller:
        family = "greenhouse"

        def fill(self, page, job, answers, materials) -> FillResult: ...

    register_filler(GreenhouseFiller())

Rules every filler must follow (the runner enforces the important ones again):

- Fill the form only. Never click the final submit button: the runner does
  that (live only) after the pre-submit screenshot and the attestation check.
  Set ``ready_to_submit=True`` and ``submit_selector`` when the form is
  complete.
- Attestations (``answers.is_attestation``) come ONLY from ``answers``. If a
  required one is missing, do not guess: add a ``Need(kind="answer")`` with the
  question text and return ``ready_to_submit=False``.
- Never create an account, never type a password (use the runner's
  ``SecretStore`` through ``FillContext.fill_secret`` if a filler must log in;
  dry runs never may).
- CAPTCHA on the page: return ``Need(kind="captcha")``; never solve it.
- Every field you touch goes into ``fields`` with its label, the value you
  typed (or ``"[file] name.pdf"`` for uploads) and a ``source`` from
  ``FIELD_SOURCES``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Where a field value came from (recorded in submissions.fields_json).
FIELD_SOURCES = (
    "answer_bank",  # the person's saved application answers
    "profile",  # profile.json personal details
    "resume_ai",  # open question written by the model from the resume
    "materials",  # resume / cover letter upload
    "human",  # typed in by the person through a pending input
    "secret",  # value injected from the SecretStore (never logged)
    "filler",  # deterministic filler default (e.g. a checkbox it must tick)
)

NEED_KINDS = ("answer", "captcha", "email_code")


@dataclass
class FieldRecord:
    label: str
    value: str
    source: str
    key: str | None = None  # answer-bank key when source == answer_bank
    attestation: bool = False
    selector: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Need:
    kind: str  # answer | captcha | email_code
    prompt: str  # question text / what the person should do
    key: str | None = None  # answer-bank key the answer belongs to (if known)
    category: str | None = None  # attestation category (work_authorization, ...)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FillResult:
    fields: list[FieldRecord] = field(default_factory=list)
    needs: list[Need] = field(default_factory=list)
    ready_to_submit: bool = False
    # CSS selector of the final submit control (runner clicks it, live only).
    submit_selector: str | None = None
    # False = "not my form after all": the runner falls back to the agent.
    handled: bool = True
    notes: str = ""


@dataclass
class Materials:
    """Files and text the filler may use. Paths are absolute and must exist."""

    resume_path: Path | None = None
    cover_letter_path: Path | None = None
    resume_text: str = ""
    cover_letter_text: str = ""


@runtime_checkable
class FormFiller(Protocol):
    family: str

    def fill(self, page: Any, job: dict, answers: "Any", materials: Materials) -> FillResult:
        """Fill the application form on ``page`` (a Playwright Page)."""
        ...


_REGISTRY: dict[str, FormFiller] = {}


def register_filler(filler: FormFiller) -> FormFiller:
    """Register a deterministic filler for its ``family`` (last one wins)."""
    family = (getattr(filler, "family", "") or "").strip().lower()
    if not family:
        raise ValueError("A FormFiller needs a non-empty `family`")
    _REGISTRY[family] = filler
    return filler


def unregister_filler(family: str) -> None:
    _REGISTRY.pop((family or "").lower(), None)


def get_filler(family: str | None) -> FormFiller | None:
    if not family:
        return None
    _load_builtin_fillers()
    return _REGISTRY.get(family.lower())


def registered_families() -> list[str]:
    _load_builtin_fillers()
    return sorted(_REGISTRY)


_builtins_loaded = False


def _load_builtin_fillers() -> None:
    """Import ``apply.ats.fillers`` once if it exists (owned by the ATS work).

    That module registers its fillers on import. Missing module = no
    deterministic fillers yet; the agent handles every form.
    """
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    import importlib
    import logging

    try:
        importlib.import_module("jobwright.apply.ats.fillers")
    except ModuleNotFoundError:
        pass
    except Exception:  # noqa: BLE001 - a broken filler must not break apply
        logging.getLogger(__name__).exception("Loading deterministic ATS fillers failed")
