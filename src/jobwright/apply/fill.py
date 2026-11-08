"""Form-filler protocol shared by the deterministic ATS fillers (apply/ats/) and the agent.

Minimal on purpose: the apply core (``apply/runner.py``) owns the browser, the
answer bank and the human-in-the-loop; a filler only fills one open
application page and reports what it did and what it still needs. A filler
never submits from ``fill`` (``BaseFiller.submit`` / ``verify`` are separate,
and the runner calls them only for live runs, after the pre-submit
screenshot and its own attestation re-check).

The runner picks ``apply.ats.fillers.filler_for(application_url, cb)`` first
and falls back to the Claude agent (``apply/agent.py``) when there is none,
when the filler raises, or when it needs something only the agent can do
(an email code, an account).

The optional fields after the filler's own (``key``, ``attestation``,
``selector`` on FieldRecord; ``key``, ``category`` on Need) are filled by the
agent's tools and default to empty, so fillers can ignore them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

# Filler sources: answer_bank | resume (contact from the profile) | ai (open
# question from the resume) | file (upload). The agent's tools also record
# profile | resume_ai | materials | secret.
FieldSource = Literal["answer_bank", "resume", "ai", "file", "profile", "resume_ai", "materials", "secret"]
NeedKind = Literal["answer", "captcha", "email_code", "account"]


@dataclass
class FieldRecord:
    label: str
    value: str
    source: str
    required: bool = False
    key: str | None = None  # answer-bank key when source == answer_bank
    attestation: bool = False
    selector: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Need:
    kind: str  # NeedKind
    # "<answer key|question|field|form|cv/cover>: <label>" from fillers; the
    # agent's tools put the bare question text here.
    detail: str
    key: str | None = None
    category: str | None = None

    @property
    def question(self) -> str:
        """The human-readable part (the question / field label)."""
        head, sep, rest = self.detail.partition(": ")
        return rest if sep and head and " " not in head.strip() else self.detail

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["question"] = self.question
        return d


@dataclass
class FillResult:
    fields: list[FieldRecord] = field(default_factory=list)
    needs: list[Need] = field(default_factory=list)
    ready_to_submit: bool = False


class FormFiller(Protocol):
    def fill(self, page: Any, job: dict, answers: dict, materials: dict) -> FillResult: ...
