"""Deterministic characterization tests for screenshot capture and visual diffs."""

from __future__ import annotations

import builtins
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from uidetox.commands import capture
from uidetox.runtime_observer import (
    RuntimeObservation,
    RuntimePage,
    RuntimeViewport,
)


def _save_changed_image(path: Path, size: tuple[int, int], changed: int) -> None:
    image = Image.new("RGB", size, (0, 0, 0))
    pixels = image.load()
    for index in range(changed):
        pixels[index % size[0], index // size[0]] = (31, 0, 0)
    image.save(path)


def _observation(
    url: str,
    screenshots: list[tuple[str, Path]],
    *,
    errors: tuple[str, ...] = (),
) -> RuntimeObservation:
    pages = tuple(
        RuntimePage(
            url=url,
            title=name,
            viewport=RuntimeViewport(name, 1280, 800),
            elements=(),
            screenshot=str(path.resolve()),
        )
        for name, path in screenshots
    )
    return RuntimeObservation(
        generated_at="2026-07-19T00:00:00Z",
        requested_urls=(url,),
        pages=pages,
        errors=errors,
    )


@pytest.mark.parametrize(
    ("changed", "percentage", "coverage_band"),
    [
        (1, 0.05, "trace"),
        (2, 0.1, "localized"),
        (99, 4.95, "localized"),
        (100, 5.0, "noticeable"),
        (399, 19.95, "noticeable"),
        (400, 20.0, "broad"),
        (999, 49.95, "broad"),
        (1000, 50.0, "extensive"),
    ],
)
def test_visual_diff_coverage_band_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: int,
    percentage: float,
    coverage_band: str,
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
        "coverage_band": coverage_band,
    }
    assert Path(result["diff_image"]).is_file()


def test_visual_diff_identical_images_and_amplified_output(tmp_path: Path) -> None:
    before = tmp_path / "same-before.png"
    after = tmp_path / "same-after.png"
    Image.new("RGB", (2, 1), (0, 0, 0)).save(before)
    changed = Image.new("RGB", (2, 1), (0, 0, 0))
    changed.putpixel((1, 0), (20, 20, 0))
    changed.save(after)

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        result = capture._generate_visual_diff(before, before)
        changed_result = capture._generate_visual_diff(before, after)

    assert result["change_percentage"] == 0
    assert result["pixels_changed"] == 0
    assert result["coverage_band"] == "trace"

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


def test_visual_diff_rejects_mismatched_dimensions(tmp_path: Path) -> None:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (2, 1), (0, 0, 0)).save(before)
    Image.new("RGB", (1, 2), (0, 0, 0)).save(after)

    result = capture._generate_visual_diff(before, after)

    assert result["error_code"] == "dimension_mismatch"
    assert "2x1" in result["error"]
    assert "1x2" in result["error"]


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
    assert "Playwright unavailable" in stderr
    assert "pip install 'uidetox[capture]'" in stderr
    assert "python -m playwright install chromium" in stderr
    assert not out_path.exists()


def test_capture_screenshot_missing_chromium_is_actionable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = RuntimeError("Executable doesn't exist at /tmp/chromium")
    monkeypatch.setattr(
        capture,
        "observe_frontend",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    out_path = tmp_path / "missing-browser.png"

    assert capture._capture_screenshot("https://example.invalid", out_path) is False
    stderr = capsys.readouterr().err
    assert "Failed to capture screenshot: Executable doesn't exist at /tmp/chromium" in stderr
    assert "pip install 'uidetox[capture]'" in stderr
    assert "python -m playwright install chromium" in stderr
    assert not out_path.exists()


def test_capture_screenshot_navigation_failure_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_path = tmp_path / "navigation-failure.png"
    monkeypatch.setattr(
        capture,
        "observe_frontend",
        lambda *_args, **_kwargs: _observation(
            "https://example.invalid",
            [],
            errors=("desktop: navigation failed",),
        ),
    )

    assert capture._capture_screenshot("https://example.invalid", out_path) is False
    stderr = capsys.readouterr().err
    assert "Failed to capture screenshot: desktop: navigation failed" in stderr
    assert "uidetox[capture]" not in stderr
    assert not out_path.exists()


def test_capture_screenshot_forwards_arguments_and_closes_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_path = tmp_path / "success.png"
    viewport = {"width": 375, "height": 812}
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_observe(*args: object, **kwargs: object) -> RuntimeObservation:
        calls.append((args, kwargs))
        return _observation(
            "https://example.invalid/page",
            [("desktop", out_path)],
        )

    monkeypatch.setattr(capture, "observe_frontend", fake_observe)

    assert capture._capture_screenshot(
        "https://example.invalid/page",
        out_path,
        full_page=False,
        viewport=viewport,
    ) is True
    assert len(calls) == 1
    assert calls[0][0] == ("https://example.invalid/page",)
    assert calls[0][1]["viewports"] == (
        RuntimeViewport("desktop", 375, 812),
    )
    assert calls[0][1]["screenshots_dir"] == tmp_path.resolve()
    assert calls[0][1]["full_page"] is False


def test_capture_multi_viewport_returns_only_successes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_observe(*args: object, **kwargs: object) -> RuntimeObservation:
        calls.append((args, kwargs))
        return _observation(
            "https://example.invalid",
            [
                ("mobile", snapshots / "before_mobile.png"),
                ("desktop", snapshots / "before_desktop.png"),
            ],
        )

    monkeypatch.setattr(capture, "_snapshots_dir", lambda: snapshots)
    monkeypatch.setattr(capture, "observe_frontend", fake_observe)

    result = capture._capture_multi_viewport("https://example.invalid", "before")

    assert result == [snapshots / "before_mobile.png", snapshots / "before_desktop.png"]
    assert len(calls) == 1
    assert [viewport.name for viewport in calls[0][1]["viewports"]] == [
        "mobile",
        "tablet",
        "desktop",
        "wide",
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
    calls: list[tuple[str, str, bool]] = []

    def fake_stage(
        url: str,
        prefix: str,
        *,
        responsive: bool,
    ) -> tuple[list[Path], RuntimeObservation]:
        calls.append((url, prefix, responsive))
        path = snapshots / "before.png"
        path.write_bytes(b"before")
        return [path], _observation(url, [("desktop", path)])

    monkeypatch.setattr(capture, "_capture_named_stage", fake_stage)

    capture.run(_args("before"))

    assert calls == [("https://example.invalid", "before", False)]
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
        "coverage_band": "noticeable",
        "viewport": "desktop",
    }
    diff_calls: list[tuple[list[tuple[str, Path, Path]], Path]] = []

    def fake_stage(
        url: str,
        _prefix: str,
        *,
        responsive: bool,
    ) -> tuple[list[Path], RuntimeObservation]:
        assert not responsive
        path = snapshots / "after.png"
        path.write_bytes(b"after")
        return [path], _observation(url, [("desktop", path)])

    def fake_evidence(
        comparisons: list[tuple[str, Path, Path]],
        output_dir: Path,
        **_kwargs: object,
    ) -> list[dict]:
        diff_calls.append((comparisons, output_dir))
        return [diff_result]

    monkeypatch.setattr(capture, "_capture_named_stage", fake_stage)
    monkeypatch.setattr(capture, "_build_capture_evidence", fake_evidence)

    capture.run(_args("after"))

    after = snapshots / "after.png"
    assert diff_calls == [([("desktop", before, after)], snapshots)]
    assert json.loads((snapshots / "diff_meta.json").read_text()) == diff_result
    assert (snapshots / "latest.png").read_bytes() == b"after"
    assert after.read_bytes() == b"after"


def test_run_after_without_baseline_skips_diff_and_writes_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)

    def fake_stage(
        url: str,
        _prefix: str,
        *,
        responsive: bool,
    ) -> tuple[list[Path], RuntimeObservation]:
        assert not responsive
        path = snapshots / "after.png"
        path.write_bytes(b"after")
        return [path], _observation(url, [("desktop", path)])

    def unexpected_diff(*_args: object) -> list[dict]:
        pytest.fail("visual diff must not run without baseline")

    monkeypatch.setattr(capture, "_capture_named_stage", fake_stage)
    monkeypatch.setattr(capture, "_build_capture_evidence", unexpected_diff)

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
    (snapshots / "after_desktop.png").write_bytes(b"stale-desktop")
    (snapshots / "latest.png").write_bytes(b"stale-latest")
    multi_calls: list[tuple[str, str, bool]] = []
    diff_calls: list[tuple[list[tuple[str, Path, Path]], Path]] = []

    def fake_stage(
        url: str,
        prefix: str,
        *,
        responsive: bool,
    ) -> tuple[list[Path], RuntimeObservation]:
        multi_calls.append((url, prefix, responsive))
        after_mobile.write_bytes(b"after")
        return [after_mobile], _observation(url, [("mobile", after_mobile)])

    def fake_evidence(
        comparisons: list[tuple[str, Path, Path]],
        output_dir: Path,
        **_kwargs: object,
    ) -> list[dict]:
        diff_calls.append((comparisons, output_dir))
        return [
            {
                "change_percentage": 1.0,
                "coverage_band": "localized",
                "viewport": "mobile",
            }
        ]

    monkeypatch.setattr(capture, "_capture_named_stage", fake_stage)
    monkeypatch.setattr(capture, "_build_capture_evidence", fake_evidence)

    capture.run(_args("after", responsive=True))

    assert multi_calls == [("https://example.invalid", "after", True)]
    assert diff_calls == [
        ([("mobile", before_mobile, after_mobile)], snapshots)
    ]
    assert not (snapshots / "latest.png").exists()
    assert json.loads((snapshots / "diff_meta.json").read_text()) == {
        "schema_version": 1,
        "comparisons": [
            {
                "change_percentage": 1.0,
                "coverage_band": "localized",
                "viewport": "mobile",
            }
        ],
    }


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
    def fake_stage(
        url: str,
        _prefix: str,
        *,
        responsive: bool,
    ) -> tuple[list[Path], RuntimeObservation]:
        captured = multi_result if responsive else (
            [snapshots / "captured.png"] if capture_result else []
        )
        pages = [
            ("mobile" if responsive else "desktop", path)
            for path in captured
        ]
        return captured, _observation(url, pages)

    monkeypatch.setattr(capture, "_capture_named_stage", fake_stage)

    with pytest.raises(SystemExit) as exc_info:
        capture.run(_args(stage, responsive=responsive))

    assert exc_info.value.code == 1
    assert list(snapshots.iterdir()) == []
