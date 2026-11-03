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
esac
exit 0
"""


def _run(tmp_path: Path, preflight_rc: int, user: str | None = None) -> tuple[int, str, list[str]]:
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
    py.write_text(FAKE_PY.format(calls=calls, preflight_rc=preflight_rc))
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
