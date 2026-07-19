"""Regression tests for optional capability packaging and fallbacks."""

from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path

import pytest

from uidetox.commands import capture
from uidetox.visual_evidence import (
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    build_visual_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_EXTRA_COMMAND = "pip install 'uidetox[capture]'"
CHROMIUM_COMMAND = "python -m playwright install chromium"
VISUAL_EXTRA_COMMAND = "pip install 'uidetox[visual]'"


def _project_metadata() -> dict:
    import tomllib

    with (PROJECT_ROOT / "pyproject.toml").open("rb") as project_file:
        return tomllib.load(project_file)["project"]


def _block_imports(monkeypatch: pytest.MonkeyPatch, blocked: set[str]) -> None:
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split(".", 1)[0] in blocked:
            raise ImportError(f"blocked optional dependency: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def test_optional_dependency_metadata_keeps_core_minimal() -> None:
    project = _project_metadata()
    base = set(project["dependencies"])
    extras = {
        name: set(requirements)
        for name, requirements in project["optional-dependencies"].items()
    }

    assert set(extras) == {"dev", "visual", "capture", "all"}
    assert extras["visual"] == {"Pillow>=12.3.0"}
    assert extras["capture"] == {"Pillow>=12.3.0", "playwright>=1.42.0"}
    assert extras["all"] == extras["capture"]
    assert extras["dev"] == {"pytest>=8.0,<9.0", "Pillow>=12.3.0"}
    assert not base & extras["all"]
    assert {
        "PyYAML>=6.0",
        "tree-sitter>=0.21.0",
        "tree-sitter-javascript>=0.21.0",
        "tree-sitter-typescript>=0.21.0",
        "tree-sitter-css>=0.21.0",
    } <= base


def test_core_imports_work_without_optional_dependencies() -> None:
    script = """
import builtins

real_import = builtins.__import__
blocked = {"PIL", "playwright"}

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".", 1)[0] in blocked:
        raise ImportError(f"blocked optional dependency: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
import uidetox
import uidetox.analyzer
import uidetox.cli
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_missing_playwright_explains_capture_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _block_imports(monkeypatch, {"playwright"})

    assert not capture._capture_screenshot("http://localhost", tmp_path / "shot.png")
    error = capsys.readouterr().err
    assert CAPTURE_EXTRA_COMMAND in error
    assert CHROMIUM_COMMAND in error


def test_missing_pillow_explains_capture_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _block_imports(monkeypatch, {"PIL"})

    result = capture._generate_visual_diff(
        tmp_path / "before.png", tmp_path / "after.png"
    )

    assert CAPTURE_EXTRA_COMMAND in result["note"]
    assert CHROMIUM_COMMAND in result["note"]


def test_missing_pillow_explains_visual_extra(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _block_imports(monkeypatch, {"PIL"})
    request = VisualEvidenceRequest(
        comparisons=(
            VisualEvidenceCase(
                case_id="missing-pillow",
                before_path=tmp_path / "before.png",
                after_path=tmp_path / "after.png",
            ),
        ),
        output_dir=tmp_path,
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence(request)

    assert captured.value.code == "missing_dependency"
    assert VISUAL_EXTRA_COMMAND in str(captured.value)


def test_missing_browser_executable_preserves_error_and_explains_setup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    original_error = "Executable doesn't exist at /tmp/chromium"
    monkeypatch.setattr(
        capture,
        "observe_frontend",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(original_error)),
    )

    assert not capture._capture_screenshot("http://localhost", tmp_path / "shot.png")
    error = capsys.readouterr().err
    assert original_error in error
    assert CAPTURE_EXTRA_COMMAND in error
    assert CHROMIUM_COMMAND in error


def test_unrelated_capture_failure_preserves_error_without_install_advice(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    original_error = "page navigation failed"
    monkeypatch.setattr(
        capture,
        "observe_frontend",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(original_error)),
    )

    assert not capture._capture_screenshot("http://localhost", tmp_path / "shot.png")
    error = capsys.readouterr().err
    assert original_error in error
    assert CAPTURE_EXTRA_COMMAND not in error
    assert CHROMIUM_COMMAND not in error


def test_optional_capability_docs_and_package_mirrors_are_synchronized() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Optional Capabilities" in readme
    assert CAPTURE_EXTRA_COMMAND in readme
    assert CHROMIUM_COMMAND in readme
    assert "pip install 'uidetox[all]'" in readme

    root_docs = sorted((PROJECT_ROOT / "docs").glob("*.md"))
    assert root_docs
    for root_doc in root_docs:
        bundled_doc = PROJECT_ROOT / "uidetox" / "data" / "docs" / root_doc.name
        assert bundled_doc.read_bytes() == root_doc.read_bytes(), root_doc.name
        if "uidetox capture" in root_doc.read_text(encoding="utf-8"):
            contents = root_doc.read_text(encoding="utf-8")
            assert CAPTURE_EXTRA_COMMAND in contents, root_doc.name
            assert CHROMIUM_COMMAND in contents, root_doc.name
