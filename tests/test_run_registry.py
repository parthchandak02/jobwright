"""CLI/web run registry: one run_id per process."""

from __future__ import annotations

from pathlib import Path


def test_register_pipeline_run_writes_registry(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.run_registry import load_registry, register_pipeline_run

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(config, "LOG_DIR", log_dir)
    monkeypatch.setattr(config, "ACTIVE_USER_ID", "richa")
    monkeypatch.delenv("JOBWRIGHT_WEB_RUN_ID", raising=False)

    run_id = register_pipeline_run(["discover", "enrich"])
    entries = load_registry()
    assert len(entries) == 1
    assert entries[0]["run_id"] == run_id
    assert entries[0]["stages"] == ["discover", "enrich"]
    assert entries[0]["user"] == "richa"


def test_register_pipeline_run_skips_when_web_already_registered(tmp_path: Path, monkeypatch):
    import jobwright.config as config
    from jobwright.run_registry import load_registry, register_pipeline_run

    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setenv("JOBWRIGHT_WEB_RUN_ID", "abc123web")
    assert register_pipeline_run(["discover"]) == "abc123web"
    assert load_registry() == []
