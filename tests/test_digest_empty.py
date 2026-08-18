"""Tests for digest writing: empty states and health footer."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobwright.apply.launcher import write_morning_digest_and_manifest


def test_empty_digest_has_no_materials_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
  """Zero ready jobs should not tell users to reply materials 1."""
  digest = tmp_path / "DIGEST_test"
  manifest = tmp_path / "MANIFEST_test"

  monkeypatch.setattr(
      "jobwright.apply.launcher.list_ready_jobs",
      lambda **kwargs: [],
  )
  monkeypatch.setattr(
      "jobwright.network.per_job.load_job_contacts",
      lambda: None,
  )

  n = write_morning_digest_and_manifest(
      digest,
      manifest,
      min_score=7,
      limit=5,
      apply_enabled=True,
      pipeline_rc=1,
      health={
          "total_jobs": 3,
          "scored": 2,
          "ready_materials": 0,
          "pending_score": 1,
          "pipeline_rc": 1,
      },
  )
  assert n == 0
  text = digest.read_text(encoding="utf-8")
  assert "No matching roles" in text
  assert "find jobs now" in text
  assert 'Reply "materials 1"' not in text
  assert "pipeline exit 1" in text
  assert manifest.read_text(encoding="utf-8") == ""
