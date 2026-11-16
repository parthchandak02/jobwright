"""GitHub Actions pins must be the node24 releases.

Actions that declare runs.using node20 make every CI job print
"Node.js 20 is deprecated". These SHAs are the newest patch of the
first node24 major for each action, checked against that tag's action.yml.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# sha -> action@tag. Each tag's action.yml says `using: node24`.
NODE24 = {
    "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09": "actions/checkout@v5.1.0",
    "37802adc94f370d6bfd71619e3f0bf239e1f3b78": "astral-sh/setup-uv@v7.6.0",
    "fc06bc1257f339d1d5d8b3a19a8cae5388b55320": "pnpm/action-setup@v5.0.0",
    "a0853c24544627f65ddf259abe73b1d18a591444": "actions/setup-node@v5.0.0",
    "ece7cb06caefa5fff74198d8649806c4678c61a1": "actions/setup-python@v6.3.0",
}


def _uses_refs() -> list[str]:
    refs = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if "uses:" not in stripped:
                continue
            ref = stripped.split("uses:", 1)[1].strip().split()[0]
            refs.append(ref)
    return refs


def test_workflow_actions_are_node24_pins():
    refs = _uses_refs()
    assert refs
    for ref in refs:
        owner_repo, _, sha = ref.partition("@")
        assert sha in NODE24, ref
        assert NODE24[sha].startswith(owner_repo)


def test_setup_node_keeps_the_explicit_pnpm_cache():
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "cache: pnpm" in text
    assert "package-manager-cache: false" in text
