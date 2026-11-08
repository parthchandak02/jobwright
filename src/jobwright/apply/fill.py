"""Form-filler protocol shared by the deterministic ATS fillers (apply/ats/).

Minimal on purpose: the apply core owns the browser, the answer bank and the
human-in-the-loop; a filler only fills one open application page and reports
what it did and what it still needs. A filler never submits from ``fill``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

FieldSource = Literal["answer_bank", "resume", "ai", "file"]
NeedKind = Literal["answer", "captcha", "email_code", "account"]


@dataclass
class FieldRecord:
    label: str
    value: str
    source: FieldSource
    required: bool


@dataclass
class Need:
    kind: NeedKind
    detail: str


@dataclass
class FillResult:
    fields: list[FieldRecord] = field(default_factory=list)
    needs: list[Need] = field(default_factory=list)
    ready_to_submit: bool = False


class FormFiller(Protocol):
    def fill(self, page: Any, job: dict, answers: dict, materials: dict) -> FillResult: ...
