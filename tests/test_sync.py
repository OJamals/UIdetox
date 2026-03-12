"""Tests for asset sync between root files and uidetox/data/."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_sync_data_check_passes():
    """The sync_data.py --check must pass (root and data/ in sync)."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_data.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        f"Asset sync check failed — root and uidetox/data/ are out of sync.\n"
        f"Run: python scripts/sync_data.py\n{result.stdout}\n{result.stderr}"
    )


def test_all_root_commands_mirrored():
    """Every *.md in root commands/ must exist in uidetox/data/commands/."""
    root_cmds = ROOT / "commands"
    data_cmds = ROOT / "uidetox" / "data" / "commands"
    if not root_cmds.is_dir():
        return  # Nothing to test
    missing = []
    for md in sorted(root_cmds.glob("*.md")):
        if not (data_cmds / md.name).exists():
            missing.append(md.name)
    assert not missing, f"Root commands/ files missing from data/commands/: {missing}"


def test_all_root_references_mirrored():
    """Every *.md in root reference/ must exist in uidetox/data/reference/."""
    root_refs = ROOT / "reference"
    data_refs = ROOT / "uidetox" / "data" / "reference"
    if not root_refs.is_dir():
        return
    missing = []
    for md in sorted(root_refs.glob("*.md")):
        if not (data_refs / md.name).exists():
            missing.append(md.name)
    assert not missing, f"Root reference/ files missing from data/reference/: {missing}"


def test_all_root_docs_mirrored():
    """Every *.md in root docs/ must exist in uidetox/data/docs/."""
    root_docs = ROOT / "docs"
    data_docs = ROOT / "uidetox" / "data" / "docs"
    if not root_docs.is_dir():
        return
    missing = []
    for md in sorted(root_docs.glob("*.md")):
        if not (data_docs / md.name).exists():
            missing.append(md.name)
    assert not missing, f"Root docs/ files missing from data/docs/: {missing}"


def test_skill_and_agents_mirrored():
    """SKILL.md and AGENTS.md must be identical in root and data/."""
    for fname in ("SKILL.md", "AGENTS.md"):
        root_file = ROOT / fname
        data_file = ROOT / "uidetox" / "data" / fname
        if not root_file.exists():
            continue
        assert data_file.exists(), f"{fname} missing from uidetox/data/"
        assert root_file.read_bytes() == data_file.read_bytes(), (
            f"{fname} differs between root and uidetox/data/. "
            f"Run: python scripts/sync_data.py"
        )


def test_transforms_dir_exists():
    """uidetox/data/transforms/ must exist with JS transform files."""
    transforms = ROOT / "uidetox" / "data" / "transforms"
    assert transforms.is_dir(), "uidetox/data/transforms/ directory missing"
    js_files = list(transforms.glob("*.js"))
    assert len(js_files) >= 1, "No .js files in uidetox/data/transforms/"
