"""Per-user Hermes WhatsApp group instructions (hermes_channels)."""

from __future__ import annotations

import difflib
import os
import stat

import pytest
from ruamel.yaml import YAML

from jobwright import hermes_channels as hc
from jobwright.users import save_registry

RICHA = "120363999999999902@g.us"
NEW = "120363400000000001@g.us"
OTHER = "120363999999999904@g.us"

CONFIG = f"""# Hermes config
model:
  default: some-model  # trailing comment
  provider: fireworks
fallback_providers:
  - provider: gemini
    model: gemini-flash
# before whatsapp
whatsapp:
  channel_skill_bindings:
    - id: {RICHA}
      skills:
        - pp-job-apply
        - hermes-cron-jobs
        - graphify
        - cursor-agent
  channel_overrides:
    {RICHA}:
      system_prompt: "You are the Hermes operator for jobwright (user: richa).\\nBrief LLM: JOBWRIGHT_LLM_MODEL=deepseek-v4-flash-0731 (stale)\\n"
  channel_prompts:
    {OTHER}: 'I am Parth''s morning briefing assistant. Tone: warm.

      '
    {RICHA}: 'jobwright group (richa). stale'
  require_mention: true  # keep
  observe_unmentioned_group_messages: true
  group_allow_from:
    - {OTHER}
    - {RICHA}
  extra:
    group_policy: open
telegram:
  enabled: false
# end
"""


def _users(*extra):
    users = [{"user_id": "richa", "name": "Example Person 2", "whatsapp_target": f"whatsapp:{RICHA}",
              "human_gate": True, "apply_enabled": False}]
    users += list(extra)
    save_registry({"users": users})


@pytest.fixture()
def cfg(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    os.chmod(path, 0o640)
    return path


def _load(path):
    return YAML().load(path.read_text(encoding="utf-8"))


def _write(cfg):
    return hc.apply(cfg)


def test_render_system_prompt_is_per_user():
    _users()
    from jobwright.users import get_user

    text = hc.render_system_prompt(get_user("richa"))
    assert hc.MARKER in text
    assert "belongs ONLY to Example Person 2" in text
    assert "jobwright --user richa notify" in text
    assert "jobwright-brief-richa" in text
    assert "JOBWRIGHT_USER=richa bash ~/.hermes/scripts/jobwright_brief.sh" in text
    assert "apply_enabled: false" in text
    assert "https://jobwright.parthchandak.info" in text
    assert "deepseek" not in text and "JOBWRIGHT_LLM_MODEL" not in text
    assert "never use gpt-oss" in text


def test_replaces_stale_override_and_preserves_everything_else(cfg):
    _users()
    out = _write(cfg)
    assert out["written"] and out["update"] == ["richa"]
    new = cfg.read_text(encoding="utf-8")
    old_lines = [ln for ln in CONFIG.splitlines() if RICHA + ":" not in ln and "user: richa" not in ln]
    matcher = difflib.SequenceMatcher(a=old_lines, b=new.splitlines(), autojunk=False)
    assert sum(b.size for b in matcher.get_matching_blocks()) == len(old_lines)
    assert new.startswith(CONFIG.split("  channel_overrides:")[0])
    assert new.endswith(CONFIG.split("group_allow_from:")[1])
    assert new.count("#") == CONFIG.count("#") + 1
    wa = _load(cfg)["whatsapp"]
    prompt = wa["channel_overrides"][RICHA]["system_prompt"]
    assert hc.MARKER in prompt and "deepseek" not in prompt
    assert wa["channel_prompts"][RICHA].startswith("jobwright group (richa). Auto-loaded skills")
    assert wa["channel_prompts"][OTHER] == "I am Parth's morning briefing assistant. Tone: warm.\n"
    assert wa["require_mention"] is True and wa["extra"] == {"group_policy": "open"}
    assert list(wa["group_allow_from"]).count(RICHA) == 1


def test_new_user_added_to_all_four_structures(cfg):
    _users({"user_id": "neha", "name": "Neha", "whatsapp_target": f"whatsapp:{NEW}"})
    p = hc.plan(cfg)
    assert p.ids("add") == ["neha"]
    assert "neha" in p.diff
    _write(cfg)
    wa = _load(cfg)["whatsapp"]
    assert "belongs ONLY to Neha" in wa["channel_overrides"][NEW]["system_prompt"]
    assert "(neha)" in wa["channel_prompts"][NEW]
    assert {"id": NEW, "skills": hc.SKILLS} in [dict(b) for b in wa["channel_skill_bindings"]]
    assert NEW in wa["group_allow_from"]


def test_dm_and_empty_targets_skipped(cfg):
    _users({"user_id": "dm", "name": "Dm", "whatsapp_target": "whatsapp:15551234567@s.whatsapp.net"},
           {"user_id": "none", "name": "None"})
    p = hc.plan(cfg)
    assert [s["user_id"] for s in p.skipped] == ["dm", "none"]
    assert [e["user_id"] for e in p.entries] == ["richa"]
    assert "15551234567" not in p.new_text


def test_orphan_reported_and_pruned_only_on_request(cfg):
    _users({"user_id": "neha", "name": "Neha", "whatsapp_target": f"whatsapp:{NEW}"})
    _write(cfg)
    _users()
    p = hc.plan(cfg)
    assert p.orphans == [NEW]
    assert not p.changed
    assert NEW in cfg.read_text(encoding="utf-8")
    out = hc.apply(cfg, prune=True)
    assert out["written"]
    wa = _load(cfg)["whatsapp"]
    assert NEW not in wa["channel_overrides"] and NEW not in wa["channel_prompts"]
    assert NEW not in wa["group_allow_from"]
    assert all(b["id"] != NEW for b in wa["channel_skill_bindings"])
    assert OTHER in wa["channel_prompts"] and RICHA in wa["channel_overrides"]


def test_unmanaged_jids_are_never_orphans(cfg):
    _users()
    p = hc.plan(cfg, prune=True)
    assert p.orphans == []
    assert OTHER in p.new_text


def test_idempotent(cfg):
    _users({"user_id": "neha", "name": "Neha", "whatsapp_target": f"whatsapp:{NEW}"})
    _write(cfg)
    once = cfg.read_text(encoding="utf-8")
    out = hc.apply(cfg)
    assert not out["changed"] and not out["written"] and out["backup"] is None
    assert out["unchanged"] == ["richa", "neha"]
    assert cfg.read_text(encoding="utf-8") == once


def test_dry_run_never_writes(cfg, monkeypatch):
    _users()
    monkeypatch.setenv("JOBWRIGHT_HERMES_DRY_RUN", "1")
    out = hc.apply(cfg)
    assert out["changed"] and out["dry_run"] and not out["written"]
    assert cfg.read_text(encoding="utf-8") == CONFIG
    assert not list(cfg.parent.glob("*.bak-jobwright-*"))


def test_backup_created_and_mode_kept(cfg):
    _users()
    out = _write(cfg)
    backups = list(cfg.parent.glob("config.yaml.bak-jobwright-*"))
    assert [str(b) for b in backups] == [out["backup"]]
    assert backups[0].read_text(encoding="utf-8") == CONFIG
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o640
    assert not list(cfg.parent.glob(".config.yaml.*"))


def test_cli_prints_diff_and_respects_config_env(cfg, monkeypatch):
    from typer.testing import CliRunner

    from jobwright.cli import app

    _users()
    monkeypatch.setenv("HERMES_CONFIG", str(cfg))
    res = CliRunner().invoke(app, ["hermes", "channels"])
    assert res.exit_code == 0, res.output
    assert "update" in res.output and "--apply" in res.output
    assert cfg.read_text(encoding="utf-8") == CONFIG
    res = CliRunner().invoke(app, ["hermes", "channels", "--apply", "--config", str(cfg)])
    assert res.exit_code == 0, res.output
    assert "hermes gateway restart" in res.output
    assert hc.MARKER in cfg.read_text(encoding="utf-8")


def test_admin_api(cfg, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from jobwright.web import session as session_mod
    from jobwright.web.app import app

    _users()
    monkeypatch.setenv("HERMES_CONFIG", str(cfg))
    session_mod.forget_initialized()
    with TestClient(app) as client:
        plan = client.get("/api/admin/hermes-channels").json()
        assert plan["update"] == ["richa"] and plan["changed"]
        out = client.post("/api/admin/hermes-channels/apply", json={}).json()
        assert out["written"] and out["backup"]
        assert client.get("/api/admin/hermes-channels").json()["unchanged"] == ["richa"]
