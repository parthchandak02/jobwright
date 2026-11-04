"""Per-run circuit breaker for job boards that block us, plus a short cooldown.

A board that answers every query with HTTP 403 ("forbidden") or keeps
rate-limiting wastes a whole run of requests and fills the brief report with
the same error. ``SiteBreaker`` counts consecutive blocked responses per site;
after ``threshold`` in a row it opens and the remaining queries for that site
are skipped this run.

A site that was blocked for the whole run (no successful response at all,
403-style ``blocked`` only; rate limits are transient) goes into a cooldown
stored in the user's ``logs/site_cooldown.json``: it is skipped entirely for
``cooldown_days``, then probed once (threshold 1). A probe that works clears
the cooldown; a blocked probe renews it.

``summary()`` feeds the discovery source health: ``{"status": "blocked" |
"cooldown" | "rate_limited", "blocked_responses", "skipped", "until"}``.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3
DEFAULT_COOLDOWN_DAYS = 3

# JobSpy logs (it does not raise) when a board refuses a page.
BLOCKED_RE = re.compile(r"\b(403|429)\b|forbidden|blocked by|too many requests", re.IGNORECASE)
JOBSPY_LOGGERS = {
    "JobSpy:ZipRecruiter": "zip_recruiter",
    "JobSpy:Indeed": "indeed",
    "JobSpy:Glassdoor": "glassdoor",
    "JobSpy:Google": "google",
    "JobSpy:LinkedIn": "linkedin",
}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat()


class SiteBreaker:
    def __init__(
        self,
        state_path: Path | None = None,
        *,
        threshold: int = DEFAULT_THRESHOLD,
        cooldown_days: float = DEFAULT_COOLDOWN_DAYS,
        clock=time.time,
    ) -> None:
        self.state_path = Path(state_path) if state_path else None
        self.threshold = max(1, int(threshold))
        self.cooldown_days = cooldown_days
        self._clock = clock
        self._lock = threading.Lock()
        self._streak: dict[str, int] = {}
        self._blocked: dict[str, int] = {}
        self._ok: dict[str, int] = {}
        self._skipped: dict[str, int] = {}
        self._open: dict[str, str] = {}  # site -> "blocked" | "rate_limited"
        self._cooldown: dict[str, float] = {}  # site -> until (epoch), still active
        self._probing: set[str] = set()
        self._state: dict[str, dict] = self._load()
        now = self._clock()
        for site, entry in self._state.items():
            until = float(entry.get("until") or 0)
            if until > now:
                self._cooldown[site] = until
            else:
                self._probing.add(site)

    # -- state file ---------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        if self.state_path is None or not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}
        sites = data.get("sites") if isinstance(data, dict) else None
        return {k: v for k, v in (sites or {}).items() if isinstance(v, dict)}

    def save(self) -> None:
        """Persist cooldowns: start/renew for fully blocked sites, clear for working ones."""
        if self.state_path is None:
            return
        now = self._clock()
        with self._lock:
            state = dict(self._state)
            for site, kind in self._open.items():
                if kind == "blocked" and not self._ok.get(site):
                    until = now + self.cooldown_days * 86400
                    state[site] = {"until": until, "until_iso": _iso(until), "since": _iso(now),
                                   "blocked_responses": self._blocked.get(site, 0)}
            for site, n in self._ok.items():
                if n and site in state and site not in self._cooldown:
                    state.pop(site, None)
            self._state = state
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            if state:
                self.state_path.write_text(json.dumps({"sites": state}, indent=2))
            elif self.state_path.exists():
                self.state_path.unlink()
        except OSError as e:
            log.warning("Could not write %s: %s", self.state_path, e)

    # -- per-run accounting -------------------------------------------------

    def in_cooldown(self, site: str) -> bool:
        return site in self._cooldown

    def is_open(self, site: str) -> bool:
        """True when queries for ``site`` should be skipped (tripped or cooling down)."""
        with self._lock:
            return site in self._open or site in self._cooldown

    def skip(self, site: str) -> None:
        with self._lock:
            self._skipped[site] = self._skipped.get(site, 0) + 1

    def record_blocked(self, site: str, kind: str = "blocked") -> bool:
        """Count one blocked response. True when this one opened the breaker."""
        with self._lock:
            self._blocked[site] = self._blocked.get(site, 0) + 1
            self._streak[site] = self._streak.get(site, 0) + 1
            limit = 1 if site in self._probing else self.threshold
            if site in self._open or self._streak[site] < limit:
                return False
            self._open[site] = kind
        log.warning("%s: %d blocked responses in a row; skipping it for the rest of this run",
                    site, self._streak[site])
        return True

    def record_ok(self, site: str) -> None:
        with self._lock:
            self._ok[site] = self._ok.get(site, 0) + 1
            self._streak[site] = 0
            self._probing.discard(site)

    def summary(self) -> dict[str, dict]:
        with self._lock:
            out: dict[str, dict] = {}
            for site, until in self._cooldown.items():
                out[site] = {"status": "cooldown", "skipped": self._skipped.get(site, 0),
                             "until": _iso(until)}
            for site, kind in self._open.items():
                entry = {"status": kind, "blocked_responses": self._blocked.get(site, 0),
                         "skipped": self._skipped.get(site, 0)}
                if kind == "blocked" and not self._ok.get(site):
                    entry["until"] = _iso(self._clock() + self.cooldown_days * 86400)
                out[site] = entry
            return out


class JobSpyBlockHandler(logging.Handler):
    """Turns JobSpy's 'status code 403' / '429 ... blocked' log lines into breaker events."""

    def __init__(self, breaker: SiteBreaker) -> None:
        super().__init__(level=logging.WARNING)
        self.breaker = breaker

    def emit(self, record: logging.LogRecord) -> None:
        site = JOBSPY_LOGGERS.get(record.name)
        if site is None:
            return
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - logging must never raise
            return
        if BLOCKED_RE.search(msg):
            kind = "rate_limited" if re.search(r"\b429\b|too many", msg, re.IGNORECASE) else "blocked"
            self.breaker.record_blocked(site, kind)


class watch_jobspy_logs:  # noqa: N801 - used as a context manager
    """Attach a JobSpyBlockHandler to every JobSpy site logger for the block."""

    def __init__(self, breaker: SiteBreaker) -> None:
        self.handler = JobSpyBlockHandler(breaker)

    def __enter__(self) -> JobSpyBlockHandler:
        for name in JOBSPY_LOGGERS:
            logging.getLogger(name).addHandler(self.handler)
        return self.handler

    def __exit__(self, *exc) -> None:
        for name in JOBSPY_LOGGERS:
            logging.getLogger(name).removeHandler(self.handler)
