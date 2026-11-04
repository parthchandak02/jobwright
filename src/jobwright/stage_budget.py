"""Soft time budgets for pipeline stages.

The pipeline sets a deadline before each stage (``JOBWRIGHT_STAGE_BUDGET_<STAGE>``
seconds; enrich defaults to 45 minutes, other stages have none). Long loops
call ``exceeded()`` between items and stop early, logging what they skipped,
so one slow stage cannot eat the whole brief (run_daily_brief.sh still has a
hard overall deadline, JOBWRIGHT_BRIEF_TIMEOUT).
"""

from __future__ import annotations

import os
import time

DEFAULT_BUDGETS = {"enrich": 45 * 60}

_deadline: float | None = None
_stage: str | None = None


def budget_seconds(stage: str) -> float | None:
    raw = os.environ.get(f"JOBWRIGHT_STAGE_BUDGET_{stage.upper()}", "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            return DEFAULT_BUDGETS.get(stage)
        return value if value > 0 else None
    return DEFAULT_BUDGETS.get(stage)


def start(stage: str) -> float | None:
    """Arm the budget for ``stage``; returns the budget in seconds (None = unlimited)."""
    global _deadline, _stage
    budget = budget_seconds(stage)
    _stage = stage
    _deadline = time.monotonic() + budget if budget else None
    return budget


def clear() -> None:
    global _deadline, _stage
    _deadline = None
    _stage = None


def exceeded() -> bool:
    return _deadline is not None and time.monotonic() >= _deadline


def current_stage() -> str | None:
    return _stage
