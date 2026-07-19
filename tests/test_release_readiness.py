import re
from pathlib import Path


WORKFLOW = Path(".github/workflows/python-publish.yml")


def test_publish_workflow_is_release_gated_and_collision_visible() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "  release:\n    types: [published]\n" in workflow
    assert "\n  push:\n" not in workflow
    assert "skip-existing:" not in workflow


def test_publish_workflow_validates_tag_and_distributions() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

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


def test_publish_workflow_uses_one_authentication_mode() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "password: ${{ secrets.PYPI_API_TOKEN }}" in workflow
    assert "id-token: write" not in workflow


def test_publish_workflow_pins_actions_and_avoids_release_cache_risks() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    action_refs = re.findall(r"^\s*uses:\s+([^#\s]+)", workflow, flags=re.MULTILINE)

    assert action_refs
    assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", ref) for ref in action_refs)
    assert workflow.count("persist-credentials: false") == 2
    assert "cache: pip" not in workflow
