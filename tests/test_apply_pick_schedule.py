"""Settings → Claude: when the daily apply picks arrive (hermes_cron.apply_pick_schedule)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from jobwright import hermes_cron


def _scripts() -> Path:
    path = Path(os.environ["JOBWRIGHT_HERMES_SCRIPTS_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _install(user_id: str, expr: str | None, **job) -> None:
    name = hermes_cron.apply_pick_script_name(user_id)
    (_scripts() / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    if expr is None:
        return
    jobs_file = _scripts().parent / "cron" / "jobs.json"
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {"name": f"jobwright-apply-pick-{user_id}", "script": name, "enabled": True,
             "schedule": {"kind": "cron", "expr": expr}, **job}
    jobs_file.write_text(json.dumps({"jobs": [{"name": "other", "script": "x.sh"}, entry]}), encoding="utf-8")


MORNING = datetime(2026, 11, 9, 6, 0).astimezone()  # a Monday, before the pick


def test_no_script_means_not_scheduled():
    out = hermes_cron.apply_pick_schedule("alex", 180, now=MORNING)
    assert out == {"scheduled": False, "time": None, "days": None, "next_at": None, "apply_at": None,
                   "veto_minutes": 180}


def test_script_without_a_known_time_is_scheduled_without_times():
    _install("alex", None)
    out = hermes_cron.apply_pick_schedule("alex", 180, now=MORNING)
    assert out["scheduled"] is True and out["time"] is None and out["next_at"] is None


def test_daily_time_and_veto_window():
    _install("alex", "30 7 * * *")
    out = hermes_cron.apply_pick_schedule("alex", 180, now=MORNING)
    assert out["scheduled"] and out["time"] == "07:30" and out["days"] == "daily"
    assert datetime.fromisoformat(out["next_at"]).replace(tzinfo=None) == datetime(2026, 11, 9, 7, 30)
    assert datetime.fromisoformat(out["apply_at"]).replace(tzinfo=None) == datetime(2026, 11, 9, 10, 30)


def test_after_todays_pick_the_next_one_is_tomorrow_and_weekdays_skip_the_weekend():
    _install("alex", "0 8 * * 1-5")
    friday_noon = datetime(2026, 11, 13, 12, 0).astimezone()
    out = hermes_cron.apply_pick_schedule("alex", 60, now=friday_noon)
    assert out["days"] == "weekdays"
    assert datetime.fromisoformat(out["next_at"]).replace(tzinfo=None) == datetime(2026, 11, 16, 8, 0)
    assert datetime.fromisoformat(out["apply_at"]).replace(tzinfo=None) == datetime(2026, 11, 16, 9, 0)


def test_paused_or_odd_schedules_give_no_time():
    _install("alex", "30 7 * * *", enabled=False)
    assert hermes_cron.apply_pick_schedule("alex", 180, now=MORNING)["time"] is None
    _install("alex", "*/30 * * * *")
    out = hermes_cron.apply_pick_schedule("alex", 180, now=MORNING)
    assert out["scheduled"] and out["time"] is None


def test_other_profiles_script_does_not_count():
    _install("blake", "30 7 * * *")
    assert hermes_cron.apply_pick_schedule("alex", 180, now=MORNING)["scheduled"] is False
