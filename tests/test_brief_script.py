"""scripts/run_daily_brief.sh: a preflight failure exits non-zero but still reports."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

FAKE_PY = """#!/usr/bin/env bash
echo "$*" >> "{calls}"
case "$*" in
  *preflight*) exit {preflight_rc} ;;
  *" run "*) {run_cmd} ;;
esac
exit 0
"""


def _run(tmp_path: Path, preflight_rc: int, user: str | None = None, run_cmd: str = "exit 0",
         extra_env: dict | None = None) -> tuple[int, str, list[str]]:
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    fake = tmp_path / "repo"
    (fake / "scripts").mkdir(parents=True)
    (fake / "pyproject.toml").write_text("[project]\nname='fake'\n")
    for name in ("run_daily_brief.sh", "_jobwright_repo.sh"):
        shutil.copy(REPO / "scripts" / name, fake / "scripts" / name)
    calls = tmp_path / "calls.txt"
    py = fake / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.write_text(FAKE_PY.format(calls=calls, preflight_rc=preflight_rc, run_cmd=run_cmd))
    py.chmod(0o755)
    data = tmp_path / "data"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "JOBWRIGHT_REPO": str(fake),
        "JOBWRIGHT_DIR": str(data),
        "JOBWRIGHT_ENV": str(tmp_path / "missing.env"),
        "JOBWRIGHT_HERMES_DRY_RUN": "1",
    }
    if user:
        env["JOBWRIGHT_USER"] = user
    env.update(extra_env or {})
    res = subprocess.run(
        ["bash", str(fake / "scripts" / "run_daily_brief.sh")],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    status_files = list(data.glob("BRIEF_STATUS_*"))
    status = status_files[0].read_text() if status_files else ""
    return res.returncode, status, calls.read_text().splitlines() if calls.exists() else []


@pytest.mark.parametrize("user", [None, "user1"])
def test_preflight_failure_exits_nonzero_and_still_reports(tmp_path, user):
    rc, status, calls = _run(tmp_path, preflight_rc=1, user=user)
    assert rc == 2
    assert "preflight_failed" in status
    assert status.strip().splitlines()[-1] == "done RC=2"
    assert any("ops brief-report" in c and "--status-file" in c for c in calls)
    assert not any(" run " in f" {c} " for c in calls)
    if user:
        assert all(f"--user {user}" in c for c in calls)


def test_brief_success_exits_zero(tmp_path):
    rc, status, calls = _run(tmp_path, preflight_rc=0)
    assert rc == 0
    assert "done RC=0" in status
    assert any("notify" in c for c in calls)
    assert any("ops brief-report" in c for c in calls)


def test_status_records_start_time(tmp_path):
    _, status, _ = _run(tmp_path, preflight_rc=0)
    first = status.splitlines()[0]
    assert first.startswith("brief_started at=20") and "timeout=10800s" in first


def test_nonzero_pipeline_rc_is_recorded(tmp_path):
    rc, status, calls = _run(tmp_path, preflight_rc=0, run_cmd="exit 3")
    assert "pipeline_rc=3" in status and status.strip().endswith("done RC=3")
    assert any("notify" in c for c in calls)


def test_locked_pipeline_is_recorded_as_locked(tmp_path):
    rc, status, _ = _run(tmp_path, preflight_rc=0, run_cmd="exit 75")
    assert "pipeline_locked" in status and "pipeline_rc" not in status


def test_deadline_kills_the_pipeline_and_still_notifies_and_reports(tmp_path):
    import time

    pid_file = tmp_path / "sleeper.pid"
    t0 = time.time()
    rc, status, calls = _run(
        tmp_path, preflight_rc=0, run_cmd=f"sleep 60 & echo $! > {pid_file}; wait",
        extra_env={"JOBWRIGHT_BRIEF_TIMEOUT": "2"},
    )
    assert time.time() - t0 < 25
    assert rc == 124 and "timeout after" in status and "in pipeline" in status
    assert status.strip().endswith("done RC=124")
    assert any("notify" in c for c in calls) and any("ops brief-report" in c for c in calls)
    sleeper = int(pid_file.read_text())
    time.sleep(0.2)
    try:
        os.kill(sleeper, 0)
        alive = subprocess.run(["ps", "-p", str(sleeper), "-o", "stat="], capture_output=True, text=True).stdout
        assert not alive.strip() or alive.strip().startswith("Z"), "pipeline's child survived the deadline"
    except ProcessLookupError:
        pass
