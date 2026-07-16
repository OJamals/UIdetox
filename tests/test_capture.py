"""Deterministic characterization tests for screenshot capture and visual diffs."""

from __future__ import annotations

import builtins
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from uidetox.commands import capture


def _save_changed_image(path: Path, size: tuple[int, int], changed: int) -> None:
    image = Image.new("RGB", size, (0, 0, 0))
    pixels = image.load()
    for index in range(changed):
        pixels[index % size[0], index // size[0]] = (31, 0, 0)
    image.save(path)


@pytest.mark.parametrize(
    ("changed", "percentage", "severity"),
    [
        (1, 0.05, "none"),
        (2, 0.1, "minor"),
        (99, 4.95, "minor"),
        (100, 5.0, "moderate"),
        (399, 19.95, "moderate"),
        (400, 20.0, "major"),
        (999, 49.95, "major"),
        (1000, 50.0, "complete_redesign"),
    ],
)
def test_visual_diff_severity_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: int,
    percentage: float,
    severity: str,
) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _save_changed_image(before, (100, 20), 0)
    _save_changed_image(after, (100, 20), changed)
    monkeypatch.setattr(capture, "now_iso", lambda: "2026-07-16T00:00:00Z")

    result = capture._generate_visual_diff(before, after)

    assert result == {
        "before": str(before),
        "after": str(after),
        "timestamp": "2026-07-16T00:00:00Z",
        "diff_image": str(tmp_path / "diff_before_after.png"),
        "change_percentage": percentage,
        "pixels_changed": changed,
        "total_pixels": 2000,
        "severity": severity,
    }
    assert Path(result["diff_image"]).is_file()


def test_visual_diff_identical_images_and_amplified_output(tmp_path: Path) -> None:
    before = tmp_path / "same-before.png"
    after = tmp_path / "same-after.png"
    Image.new("RGB", (2, 1), (0, 0, 0)).save(before)
    changed = Image.new("RGB", (2, 1), (0, 0, 0))
    changed.putpixel((1, 0), (20, 20, 0))
    changed.save(after)

    result = capture._generate_visual_diff(before, before)
    assert result["change_percentage"] == 0
    assert result["pixels_changed"] == 0
    assert result["severity"] == "none"

    changed_result = capture._generate_visual_diff(before, after)
    assert changed_result["change_percentage"] == 50.0
    assert changed_result["pixels_changed"] == 1
    with Image.open(changed_result["diff_image"]) as diff:
        assert diff.getpixel((1, 0)) == (160, 160, 0)


def test_visual_diff_rounds_percentage_to_two_decimals(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _save_changed_image(before, (20, 15), 0)
    _save_changed_image(after, (20, 15), 1)

    result = capture._generate_visual_diff(before, after)

    assert result["pixels_changed"] == 1
    assert result["total_pixels"] == 300
    assert result["change_percentage"] == 0.33


def test_visual_diff_resizes_mismatched_dimensions(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (2, 1), (0, 0, 0)).save(before)
    Image.new("RGB", (1, 2), (0, 0, 0)).save(after)

    result = capture._generate_visual_diff(before, after)

    assert result["total_pixels"] == 4
    assert result["pixels_changed"] == 0
    with Image.open(result["diff_image"]) as diff:
        assert diff.size == (2, 2)


class _FakePage:
    def __init__(self, events: list[tuple], fail_navigation: bool = False) -> None:
        self.events = events
        self.fail_navigation = fail_navigation

    def goto(self, url: str, **kwargs: object) -> None:
        self.events.append(("goto", url, kwargs))
        if self.fail_navigation:
            raise RuntimeError("navigation failed")

    def wait_for_timeout(self, timeout: int) -> None:
        self.events.append(("wait_for_timeout", timeout))

    def screenshot(self, **kwargs: object) -> None:
        self.events.append(("screenshot", kwargs))


class _FakeBrowser:
    def __init__(self, events: list[tuple], fail_navigation: bool = False) -> None:
        self.events = events
        self.page = _FakePage(events, fail_navigation)

    def new_page(self, **kwargs: object) -> _FakePage:
        self.events.append(("new_page", kwargs))
        return self.page

    def close(self) -> None:
        self.events.append(("close",))


class _FakeChromium:
    def __init__(
        self,
        events: list[tuple],
        *,
        launch_error: Exception | None = None,
        fail_navigation: bool = False,
    ) -> None:
        self.events = events
        self.launch_error = launch_error
        self.fail_navigation = fail_navigation

    def launch(self, **kwargs: object) -> _FakeBrowser:
        self.events.append(("launch", kwargs))
        if self.launch_error:
            raise self.launch_error
        return _FakeBrowser(self.events, self.fail_navigation)


class _FakePlaywrightContext:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium

    def __enter__(self) -> SimpleNamespace:
        return SimpleNamespace(chromium=self.chromium)

    def __exit__(self, *args: object) -> None:
        return None


def _install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    events: list[tuple],
    *,
    launch_error: Exception | None = None,
    fail_navigation: bool = False,
) -> None:
    chromium = _FakeChromium(
        events,
        launch_error=launch_error,
        fail_navigation=fail_navigation,
    )
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: _FakePlaywrightContext(chromium)  # type: ignore[attr-defined]
    package = types.ModuleType("playwright")
    package.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_capture_screenshot_missing_package_is_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_import = builtins.__import__

    def missing_playwright(name: str, *args: object, **kwargs: object) -> object:
        if name == "playwright.sync_api":
            raise ImportError("missing for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_playwright)
    out_path = tmp_path / "missing.png"

    assert capture._capture_screenshot("https://example.invalid", out_path) is False
    stderr = capsys.readouterr().err
    assert "Playwright Python package is not installed" in stderr
    assert "pip install 'uidetox[capture]'" in stderr
    assert "python -m playwright install chromium" in stderr
    assert not out_path.exists()


def test_capture_screenshot_missing_chromium_is_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[tuple] = []
    error = RuntimeError("Executable doesn't exist at /tmp/chromium")
    _install_fake_playwright(monkeypatch, events, launch_error=error)
    out_path = tmp_path / "missing-browser.png"

    assert capture._capture_screenshot("https://example.invalid", out_path) is False
    stderr = capsys.readouterr().err
    assert "Failed to capture screenshot: Executable doesn't exist at /tmp/chromium" in stderr
    assert "pip install 'uidetox[capture]'" in stderr
    assert "python -m playwright install chromium" in stderr
    assert events == [("launch", {"headless": True})]
    assert not out_path.exists()


def test_capture_screenshot_navigation_failure_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[tuple] = []
    _install_fake_playwright(monkeypatch, events, fail_navigation=True)
    out_path = tmp_path / "navigation-failure.png"

    assert capture._capture_screenshot("https://example.invalid", out_path) is False
    stderr = capsys.readouterr().err
    assert "Failed to capture screenshot: navigation failed" in stderr
    assert "uidetox[capture]" not in stderr
    assert not any(event[0] == "screenshot" for event in events)
    assert not out_path.exists()


def test_capture_screenshot_forwards_arguments_and_closes_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple] = []
    _install_fake_playwright(monkeypatch, events)
    out_path = tmp_path / "success.png"
    viewport = {"width": 375, "height": 812}

    assert capture._capture_screenshot(
        "https://example.invalid/page",
        out_path,
        full_page=False,
        viewport=viewport,
    ) is True
    assert events == [
        ("launch", {"headless": True}),
        ("new_page", {"viewport": viewport}),
        (
            "goto",
            "https://example.invalid/page",
            {"wait_until": "networkidle", "timeout": 15000},
        ),
        ("wait_for_timeout", 1000),
        ("screenshot", {"path": str(out_path), "full_page": False}),
        ("close",),
    ]


def test_capture_multi_viewport_returns_only_successes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    calls: list[tuple[str, Path, dict[str, int]]] = []

    def fake_capture(url: str, path: Path, **kwargs: object) -> bool:
        viewport = kwargs["viewport"]
        assert isinstance(viewport, dict)
        calls.append((url, path, viewport))
        return path.stem in {"before_mobile", "before_desktop"}

    monkeypatch.setattr(capture, "_snapshots_dir", lambda: snapshots)
    monkeypatch.setattr(capture, "_capture_screenshot", fake_capture)

    result = capture._capture_multi_viewport("https://example.invalid", "before")

    assert result == [snapshots / "before_mobile.png", snapshots / "before_desktop.png"]
    assert calls == [
        ("https://example.invalid", snapshots / "before_mobile.png", {"width": 375, "height": 812}),
        ("https://example.invalid", snapshots / "before_tablet.png", {"width": 768, "height": 1024}),
        ("https://example.invalid", snapshots / "before_desktop.png", {"width": 1280, "height": 800}),
        ("https://example.invalid", snapshots / "before_wide.png", {"width": 1920, "height": 1080}),
    ]
    assert list(snapshots.iterdir()) == []


def _args(stage: str | None, *, responsive: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        url="https://example.invalid",
        stage=stage,
        responsive=responsive,
    )


def _isolate_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    monkeypatch.setattr(capture, "load_config", lambda: {})
    monkeypatch.setattr(capture, "_snapshots_dir", lambda: snapshots)
    monkeypatch.setattr(capture, "_server_is_reachable", lambda _url: True)
    return snapshots


def test_run_before_capture_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)
    calls: list[tuple[str, Path]] = []

    def fake_capture(url: str, path: Path, **_kwargs: object) -> bool:
        calls.append((url, path))
        path.write_bytes(b"before")
        return True

    monkeypatch.setattr(capture, "_capture_screenshot", fake_capture)

    capture.run(_args("before"))

    assert calls == [("https://example.invalid", snapshots / "before.png")]
    assert (snapshots / "before.png").read_bytes() == b"before"
    assert sorted(path.name for path in snapshots.iterdir()) == ["before.png"]


def test_run_after_with_baseline_writes_metadata_and_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)
    before = snapshots / "before.png"
    before.write_bytes(b"before")
    diff_path = snapshots / "diff_before_after.png"
    diff_path.write_bytes(b"diff")
    diff_result = {
        "before": str(before),
        "after": str(snapshots / "after.png"),
        "diff_image": str(diff_path),
        "change_percentage": 5.0,
        "severity": "moderate",
    }
    diff_calls: list[tuple[Path, Path]] = []

    def fake_capture(_url: str, path: Path, **_kwargs: object) -> bool:
        path.write_bytes(b"after")
        return True

    def fake_diff(before_path: Path, after_path: Path) -> dict:
        diff_calls.append((before_path, after_path))
        return diff_result

    monkeypatch.setattr(capture, "_capture_screenshot", fake_capture)
    monkeypatch.setattr(capture, "_generate_visual_diff", fake_diff)

    capture.run(_args("after"))

    after = snapshots / "after.png"
    assert diff_calls == [(before, after)]
    assert json.loads((snapshots / "diff_meta.json").read_text()) == diff_result
    assert (snapshots / "latest.png").read_bytes() == b"after"
    assert after.read_bytes() == b"after"


def test_run_after_without_baseline_skips_diff_and_writes_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)

    def fake_capture(_url: str, path: Path, **_kwargs: object) -> bool:
        path.write_bytes(b"after")
        return True

    def unexpected_diff(*_args: object) -> dict:
        pytest.fail("visual diff must not run without baseline")

    monkeypatch.setattr(capture, "_capture_screenshot", fake_capture)
    monkeypatch.setattr(capture, "_generate_visual_diff", unexpected_diff)

    capture.run(_args("after"))

    assert "No BEFORE screenshot found" in capsys.readouterr().out
    assert not (snapshots / "diff_meta.json").exists()
    assert (snapshots / "latest.png").read_bytes() == b"after"
    assert sorted(path.name for path in snapshots.iterdir()) == ["after.png", "latest.png"]


def test_run_responsive_after_accepts_partial_viewport_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)
    before_mobile = snapshots / "before_mobile.png"
    after_mobile = snapshots / "after_mobile.png"
    before_mobile.write_bytes(b"before")
    after_mobile.write_bytes(b"after")
    multi_calls: list[tuple[str, str]] = []
    diff_calls: list[tuple[Path, Path]] = []

    def fake_multi(url: str, prefix: str) -> list[Path]:
        multi_calls.append((url, prefix))
        return [after_mobile]

    def fake_diff(before_path: Path, after_path: Path) -> dict:
        diff_calls.append((before_path, after_path))
        return {"change_percentage": 1.0, "severity": "minor"}

    monkeypatch.setattr(capture, "_capture_multi_viewport", fake_multi)
    monkeypatch.setattr(capture, "_generate_visual_diff", fake_diff)

    capture.run(_args("after", responsive=True))

    assert multi_calls == [("https://example.invalid", "after")]
    assert diff_calls == [(before_mobile, after_mobile)]
    assert not (snapshots / "latest.png").exists()
    assert not (snapshots / "diff_meta.json").exists()


@pytest.mark.parametrize(
    ("reachable", "stage", "responsive", "capture_result", "multi_result"),
    [
        (False, "before", False, True, [Path("unused")]),
        (True, "before", False, False, [Path("unused")]),
        (True, "before", True, True, []),
        (True, "after", True, True, []),
        (True, None, False, False, [Path("unused")]),
    ],
)
def test_run_failure_branches_exit_one_without_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reachable: bool,
    stage: str | None,
    responsive: bool,
    capture_result: bool,
    multi_result: list[Path],
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)
    monkeypatch.setattr(capture, "_server_is_reachable", lambda _url: reachable)
    monkeypatch.setattr(
        capture,
        "_capture_screenshot",
        lambda *_args, **_kwargs: capture_result,
    )
    monkeypatch.setattr(
        capture,
        "_capture_multi_viewport",
        lambda *_args, **_kwargs: multi_result,
    )

    with pytest.raises(SystemExit) as exc_info:
        capture.run(_args(stage, responsive=responsive))

    assert exc_info.value.code == 1
    assert list(snapshots.iterdir()) == []
