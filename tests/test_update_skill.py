from pathlib import Path

import pytest

from uidetox.commands import update_skill


def _skill_data(root: Path) -> Path:
    data = root / "data"
    (data / "commands").mkdir(parents=True)
    (data / "reference").mkdir()
    (data / "SKILL.md").write_text("---\nname: uidetox\n---\n", encoding="utf-8")
    (data / "AGENTS.md").write_text("uidetox agents", encoding="utf-8")
    (data / "commands" / "audit.md").write_text("audit", encoding="utf-8")
    (data / "reference" / "rules.md").write_text("rules", encoding="utf-8")
    return data


@pytest.mark.parametrize(
    ("installer", "destination"),
    (
        (update_skill._install_cursor, ".cursor/skills/uidetox"),
        (update_skill._install_gemini, ".gemini/skills/uidetox"),
        (update_skill._install_windsurf, ".windsurf/skills/uidetox"),
        (update_skill._install_copilot, ".github/skills/uidetox"),
    ),
)
def test_project_installers_preserve_root_files_and_use_namespace(
    tmp_path, installer, destination
):
    data = _skill_data(tmp_path)
    project = tmp_path / "project"
    (project / "commands").mkdir(parents=True)
    (project / "reference").mkdir()
    (project / "SKILL.md").write_text("project skill", encoding="utf-8")
    (project / "AGENTS.md").write_text("project agents", encoding="utf-8")
    (project / "commands" / "owned.md").write_text("keep command", encoding="utf-8")
    (project / "reference" / "owned.md").write_text("keep reference", encoding="utf-8")

    installer(data, project)

    assert (project / "SKILL.md").read_text(encoding="utf-8") == "project skill"
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == "project agents"
    assert (project / "commands" / "owned.md").read_text(
        encoding="utf-8"
    ) == "keep command"
    assert (project / "reference" / "owned.md").read_text(
        encoding="utf-8"
    ) == "keep reference"
    namespaced = project / destination
    assert (namespaced / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert (namespaced / "AGENTS.md").read_text(encoding="utf-8") == "uidetox agents"
    assert (namespaced / "commands" / "audit.md").read_text(encoding="utf-8") == "audit"


def test_namespaced_update_preserves_unrelated_files(tmp_path):
    data = _skill_data(tmp_path)
    project = tmp_path / "project"
    destination = project / ".cursor" / "skills" / "uidetox"
    destination.mkdir(parents=True)
    unrelated = destination / "user-notes.md"
    unrelated.write_text("keep me", encoding="utf-8")

    update_skill._install_cursor(data, project)

    assert unrelated.read_text(encoding="utf-8") == "keep me"
