"""uv only resolves dependency versions that are at least 7 days old."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_excludes_versions_newer_than_seven_days():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["tool"]["uv"]["exclude-newer"] == "7 days"


def test_lockfile_records_seven_day_span():
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    assert lock["options"]["exclude-newer-span"] == "P7D"
