import re
import tomllib
from pathlib import Path
from zipfile import ZipFile

import yaml


def test_publish_workflow_is_release_gated_and_collision_visible(
    publish_workflow: str,
) -> None:
    workflow = publish_workflow
    assert "  release:\n    types: [published]\n" in workflow
    assert "\n  push:\n" not in workflow
    assert "skip-existing:" not in workflow


def test_publish_workflow_validates_tag_and_distributions(
    publish_workflow: str,
) -> None:
    workflow = publish_workflow
    assert "python -m pytest -q -W error" in workflow
    assert 'python-version: "3.13"' in workflow
    assert "Verify release commit belongs to default branch" in workflow
    assert (
        'git merge-base --is-ancestor "${GITHUB_SHA}" "origin/${DEFAULT_BRANCH}"'
        in workflow
    )
    assert "Verify release tag matches package version" in workflow
    assert 'EXPECTED_TAG="v${PACKAGE_VERSION}"' in workflow
    assert "python -m twine check dist/*" in workflow


def test_publish_workflow_qualifies_windows_without_duplicate_job_body(
    publish_workflow: str,
) -> None:
    assert "runs-on: ${{ matrix.os }}" in publish_workflow
    assert "ubuntu-latest" in publish_workflow
    assert "windows-latest" in publish_workflow
    assert publish_workflow.count("name: Run tests") == 1


def test_publish_workflow_uses_one_authentication_mode(
    publish_workflow: str,
) -> None:
    workflow = publish_workflow
    assert "password: ${{ secrets.PYPI_API_TOKEN }}" in workflow
    assert "id-token: write" not in workflow


def test_publish_workflow_pins_actions_and_avoids_release_cache_risks(
    publish_workflow: str,
) -> None:
    workflow = publish_workflow
    action_refs = re.findall(r"^\s*uses:\s+([^#\s]+)", workflow, flags=re.MULTILINE)

    assert action_refs
    assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", ref) for ref in action_refs)
    assert workflow.count("persist-credentials: false") == 2
    assert "cache: pip" not in workflow


def test_publish_workflow_is_valid_yaml(publish_workflow: str) -> None:
    parsed = yaml.load(publish_workflow, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    assert "jobs" in parsed


def test_publish_workflow_runs_strict_dependency_audit(
    publish_workflow: str,
) -> None:
    assert "python -m pip_audit --strict --desc" in publish_workflow
    assert '"pip>=26.1.2"' in publish_workflow
    assert "--ignore-vuln" not in publish_workflow


def test_dev_dependencies_include_audit_and_exclude_known_advisory_ranges(
    project_root: Path,
) -> None:
    metadata = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    extras = metadata["project"]["optional-dependencies"]

    assert any(requirement.startswith("pip-audit") for requirement in extras["dev"])
    assert "pytest>=9.0.3,<10.0" in extras["dev"]


def test_built_wheel_contains_all_canonical_assets(
    built_wheel: Path,
    packaged_asset_pairs: tuple[tuple[Path, Path], ...],
) -> None:
    with ZipFile(built_wheel) as archive:
        names = set(archive.namelist())

    for _canonical, bundled in packaged_asset_pairs:
        package_name = bundled.as_posix().split("/uidetox/", maxsplit=1)[1]
        assert f"uidetox/{package_name}" in names


def test_installed_wheel_cli_runs_outside_checkout(
    installed_wheel_cli_output: str,
) -> None:
    assert installed_wheel_cli_output.startswith("uidetox ")


def test_qualification_documentation_matches_executable_gates(
    project_root: Path,
    publish_workflow: str,
) -> None:
    qualification = (project_root / "docs" / "qualification.md").read_text(
        encoding="utf-8"
    )
    readme = (project_root / "README.md").read_text(encoding="utf-8")
    commands = (
        "python -m pytest -q -W error",
        "python -m pytest -q -W error tests/test_calibration_matrix.py",
        "python -m pytest -q -W error -m browser",
        "python -m pytest -q -W error tests/test_release_readiness.py tests/test_update_skill.py",
        "python -m pip_audit --strict --desc",
    )

    assert all(command in qualification for command in commands)
    assert commands[0] in publish_workflow
    assert commands[-1] in publish_workflow
    assert "[qualification guide](docs/qualification.md)" in readme
