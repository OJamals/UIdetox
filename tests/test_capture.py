"""Deterministic characterization tests for screenshot capture and visual diffs."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox.commands import capture
from uidetox.runtime_observer import (
    RuntimeObservation,
    RuntimePage,
    RuntimeViewport,
)


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
    assert (
        "Failed to capture screenshot: Executable doesn't exist at /tmp/chromium"
        in stderr
    )
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

    assert (
        capture._capture_screenshot(
            "https://example.invalid/page",
            out_path,
            full_page=False,
            viewport=viewport,
        )
        is True
    )
    assert len(calls) == 1
    assert calls[0][0] == ("https://example.invalid/page",)
    assert calls[0][1]["viewports"] == (RuntimeViewport("desktop", 375, 812),)
    assert calls[0][1]["screenshots_dir"] == tmp_path.resolve()
    assert calls[0][1]["full_page"] is False


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


def test_responsive_capture_uses_source_boundary_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = _isolate_run(tmp_path, monkeypatch)
    (tmp_path / "responsive.css").write_text(
        "@media (max-width: 640px) { main { display: block; } }",
        encoding="utf-8",
    )
    monkeypatch.setattr(capture, "get_project_root", lambda: tmp_path)
    observed: dict[str, object] = {}

    def fake_observe(
        url: str,
        destinations,
        *,
        full_page: bool = True,
        viewport_discovery=None,
    ) -> RuntimeObservation:
        observed["destinations"] = destinations
        observed["discovery"] = viewport_discovery
        pages = tuple(
            RuntimePage(
                url=url,
                title=viewport.name,
                viewport=viewport,
                elements=(),
                screenshot=str(path.resolve()),
            )
            for viewport, path in destinations
        )
        return RuntimeObservation(
            generated_at="2026-07-26T00:00:00Z",
            requested_urls=(url,),
            pages=pages,
            viewport_discovery=viewport_discovery,
        )

    monkeypatch.setattr(capture, "_observe_capture", fake_observe)

    captured, observation = capture._capture_named_stage(
        "https://example.invalid",
        "before",
        responsive=True,
    )

    assert observation is not None
    assert observation.viewport_discovery is observed["discovery"]
    widths = {viewport.width for viewport, _path in observed["destinations"]}
    assert {639, 641}.issubset(widths)
    probes = [
        viewport
        for viewport, _path in observed["destinations"]
        if viewport.kind == "boundary"
    ]
    assert {viewport.boundary_px for viewport in probes} == {640}
    assert len(captured) == len(observed["destinations"])
    assert (snapshots / "runtime_before.json").is_file()


@pytest.mark.parametrize(
    "url",
    (
        "file:///etc/hosts",
        "ftp://example.com/archive.zip",
        "data:text/plain,reachable",
        "example.com:3000",
    ),
)
def test_server_reachability_rejects_non_http_urls_without_opening(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        capture.urllib.request,
        "urlopen",
        lambda candidate, timeout: opened.append(candidate),
    )

    assert capture._server_is_reachable(url) is False
    assert opened == []


def test_server_reachability_accepts_http_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    closed: list[bool] = []

    class Response:
        def close(self) -> None:
            closed.append(True)

    def open_url(candidate: str, timeout: int) -> Response:
        calls.append((candidate, timeout))
        return Response()

    monkeypatch.setattr(capture.urllib.request, "urlopen", open_url)

    assert capture._server_is_reachable("https://example.com/health") is True
    assert calls == [("https://example.com/health", 3)]
    assert closed == [True]


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
    assert sorted(path.name for path in snapshots.iterdir()) == [
        "after.png",
        "latest.png",
    ]


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
    assert diff_calls == [([("mobile", before_mobile, after_mobile)], snapshots)]
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
        captured = (
            multi_result
            if responsive
            else ([snapshots / "captured.png"] if capture_result else [])
        )
        pages = [("mobile" if responsive else "desktop", path) for path in captured]
        return captured, _observation(url, pages)

    monkeypatch.setattr(capture, "_capture_named_stage", fake_stage)

    with pytest.raises(SystemExit) as exc_info:
        capture.run(_args(stage, responsive=responsive))

    assert exc_info.value.code == 1
    assert list(snapshots.iterdir()) == []
