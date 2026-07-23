"""Browser-boundary tests for the shared runtime observer."""

from __future__ import annotations

import sys
import threading
import types
from contextlib import contextmanager
from dataclasses import replace
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from uidetox import runtime_observer
from uidetox.runtime_observer import (
    RuntimeElement,
    RuntimeViewport,
    detect_runtime_findings,
    observe_frontend,
)


def _measured_element(**measurements: object) -> RuntimeElement:
    return RuntimeElement(
        kind="action",
        tag="button",
        role="button",
        name="Save changes",
        selector="#save",
        order=0,
        bounds={"x": 10, "y": 10, "width": 120, "height": 36},
        styles={"fontSize": "16px", "lineHeight": "16px"},
        measurements=measurements,
    )


def _finding_codes(element: RuntimeElement) -> set[str]:
    return {finding.code for finding in detect_runtime_findings(element)}


@contextmanager
def _serve_directory(directory: Path) -> Iterator[str]:
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return None

    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_detect_runtime_findings_reports_layout_and_font_misalignment() -> None:
    element = _measured_element(
        layoutAxis="vertical",
        layoutDeviation=6.0,
        fontBaselineDeviation=5.0,
    )

    codes = _finding_codes(element)

    assert "runtime-layout-misalignment" in codes
    assert "runtime-font-misalignment" in codes


def test_detect_runtime_findings_reports_text_and_component_clipping() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=120.0,
        scrollWidth=156.0,
        clientHeight=36.0,
        scrollHeight=52.0,
        overflowX="hidden",
        overflowY="clip",
        descendantClipped=True,
    )

    codes = _finding_codes(element)

    assert "runtime-text-clipped" in codes
    assert "runtime-component-clipped" in codes


def test_detect_runtime_findings_reports_text_clipped_by_ancestor() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=120.0,
        scrollWidth=120.0,
        clientHeight=36.0,
        scrollHeight=36.0,
        overflowX="visible",
        overflowY="visible",
        clippedByAncestor=True,
        ancestorClipOverflowInlineEnd=9.0,
        clippingAncestorSelector="#card",
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-text-clipped"}
    assert findings[0].metrics["clipping_ancestor"] == "#card"


def test_detect_runtime_findings_distinguishes_intentional_truncation() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=120.0,
        scrollWidth=156.0,
        clientHeight=36.0,
        scrollHeight=36.0,
        overflowX="hidden",
        overflowY="visible",
        intentionalTruncation=True,
        textOverflow="ellipsis",
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-text-truncated"}
    assert findings[0].severity == "info"


def test_detect_runtime_findings_reports_text_edge_contact_and_padding() -> None:
    element = _measured_element(
        hasText=True,
        isControl=True,
        isBoxControl=True,
        isVisualContainer=True,
        isTextFlow=True,
        textInsetTop=2.0,
        textInsetRight=1.0,
        textInsetBottom=2.0,
        textInsetLeft=1.0,
        paddingTop=2.0,
        paddingRight=4.0,
        paddingBottom=2.0,
        paddingLeft=4.0,
    )

    codes = _finding_codes(element)

    assert "runtime-text-edge-contact" in codes
    assert "runtime-horizontal-padding" in codes
    assert "runtime-vertical-padding" in codes


def test_detect_runtime_findings_prefers_logical_axis_padding() -> None:
    element = _measured_element(
        hasText=True,
        isControl=True,
        isBoxControl=True,
        isVisualContainer=True,
        isTextFlow=True,
        textInsetInlineStart=10.0,
        textInsetInlineEnd=10.0,
        textInsetBlockStart=10.0,
        textInsetBlockEnd=10.0,
        paddingInlineStart=3.0,
        paddingInlineEnd=12.0,
        paddingBlockStart=2.0,
        paddingBlockEnd=8.0,
    )

    codes = _finding_codes(element)

    assert "runtime-horizontal-padding" in codes
    assert "runtime-vertical-padding" in codes


def test_detect_runtime_findings_reports_inadequate_multiline_spacing() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        fontSize=16.0,
        lineHeight=17.0,
    )

    assert "runtime-line-spacing" in _finding_codes(element)


def test_detect_runtime_findings_reports_overlapping_lines_as_error() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        isTextFlow=True,
        fontSize=16.0,
        lineHeight=24.0,
        minimumLineGap=-2.0,
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-line-spacing"}
    assert findings[0].severity == "error"
    assert findings[0].metrics["minimum_line_gap_px"] == -2.0


def test_detect_runtime_findings_ignores_multiple_nested_text_flows() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        isTextFlow=False,
        fontSize=16.0,
        lineHeight=17.0,
    )

    assert "runtime-line-spacing" not in _finding_codes(element)


def test_detect_runtime_findings_ignores_healthy_geometry() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        isControl=True,
        isBoxControl=True,
        isVisualContainer=True,
        isTextFlow=True,
        fontSize=16.0,
        lineHeight=24.0,
        clientWidth=120.0,
        scrollWidth=120.0,
        clientHeight=48.0,
        scrollHeight=48.0,
        overflowX="visible",
        overflowY="visible",
        textInsetTop=10.0,
        textInsetRight=12.0,
        textInsetBottom=10.0,
        textInsetLeft=12.0,
        paddingTop=10.0,
        paddingRight=12.0,
        paddingBottom=10.0,
        paddingLeft=12.0,
        layoutDeviation=1.0,
        fontBaselineDeviation=1.0,
    )

    assert detect_runtime_findings(element) == ()


def test_attach_runtime_findings_collapses_clipped_descendants_into_container() -> None:
    container = replace(
        _measured_element(descendantClipped=True),
        kind="region",
        tag="aside",
        role="complementary",
        selector="#sidebar",
    )
    child = replace(
        _measured_element(
            hasText=True,
            clippedByAncestor=True,
            clippingAncestorSelector="#sidebar",
        ),
        selector="#sidebar-link",
    )

    attached = runtime_observer._attach_runtime_findings((container, child))

    assert _finding_codes(attached[0]) == {"runtime-component-clipped"}
    assert attached[1].findings == ()


def test_plain_link_and_compact_input_are_not_padding_targets() -> None:
    plain_link = _measured_element(
        hasText=True,
        isControl=True,
        isBoxControl=False,
        isVisualContainer=False,
        paddingInlineStart=0.0,
        paddingInlineEnd=0.0,
        paddingBlockStart=0.0,
        paddingBlockEnd=0.0,
    )

    assert detect_runtime_findings(plain_link) == ()


def test_visual_container_accepts_child_managed_spacing_and_scroll_regions() -> None:
    container = _measured_element(
        hasText=True,
        isBoxControl=False,
        isVisualContainer=True,
        isTextFlow=False,
        containsScrollRegionX=True,
        containsScrollRegionY=False,
        textInsetInlineStart=0.0,
        textInsetInlineEnd=-120.0,
        textInsetBlockStart=12.0,
        textInsetBlockEnd=12.0,
        paddingInlineStart=0.0,
        paddingInlineEnd=0.0,
        paddingBlockStart=12.0,
        paddingBlockEnd=12.0,
    )

    assert detect_runtime_findings(container) == ()


def test_inline_scroll_region_does_not_hide_block_padding_defects() -> None:
    container = _measured_element(
        hasText=True,
        isBoxControl=False,
        isVisualContainer=True,
        isTextFlow=False,
        containsScrollRegionX=True,
        containsScrollRegionY=False,
        textInsetInlineStart=0.0,
        textInsetInlineEnd=-120.0,
        textInsetBlockStart=0.0,
        textInsetBlockEnd=0.0,
        paddingInlineStart=0.0,
        paddingInlineEnd=0.0,
        paddingBlockStart=0.0,
        paddingBlockEnd=0.0,
    )

    assert _finding_codes(container) == {"runtime-vertical-padding"}


class _Page:
    def __init__(self, events: list[tuple], fail_screenshot: bool = False) -> None:
        self.events = events
        self.fail_screenshot = fail_screenshot
        self.url = "http://127.0.0.1:4173/projects"

    def goto(self, url: str, **kwargs: object) -> None:
        self.events.append(("goto", url, kwargs))
        self.url = f"{url.rstrip('/')}/projects"

    def wait_for_load_state(self, state: str, **kwargs: object) -> None:
        self.events.append(("load", state, kwargs))

    def wait_for_timeout(self, value: int) -> None:
        self.events.append(("wait", value))

    def evaluate(self, _script: str) -> list[dict[str, object]]:
        return [
            {
                "kind": "region",
                "tag": "main",
                "role": "main",
                "name": "Projects",
                "selector": "main",
                "order": 0,
                "bounds": {"x": 0, "y": 0, "width": 100, "height": 80},
                "styles": {},
                "states": {},
                "measurements": {
                    "hasText": True,
                    "isMultiline": True,
                    "fontSize": 16.0,
                    "lineHeight": 17.0,
                },
            }
        ]

    def screenshot(self, **kwargs: object) -> None:
        self.events.append(("screenshot", kwargs))
        Path(str(kwargs["path"])).write_bytes(b"partial-png")
        if self.fail_screenshot:
            raise RuntimeError("screenshot failed")

    def title(self) -> str:
        return "Projects"


class _Context:
    def __init__(self, events: list[tuple], fail_screenshot: bool = False) -> None:
        self.events = events
        self.page = _Page(events, fail_screenshot)

    def new_page(self) -> _Page:
        return self.page

    def close(self) -> None:
        self.events.append(("context-close",))


class _Browser:
    def __init__(self, events: list[tuple], fail_screenshot: bool = False) -> None:
        self.events = events
        self.fail_screenshot = fail_screenshot

    def new_context(self, **kwargs: object) -> _Context:
        self.events.append(("context", kwargs))
        return _Context(self.events, self.fail_screenshot)

    def close(self) -> None:
        self.events.append(("browser-close",))


class _Chromium:
    def __init__(self, events: list[tuple], fail_screenshot: bool = False) -> None:
        self.events = events
        self.fail_screenshot = fail_screenshot

    def launch(self, **kwargs: object) -> _Browser:
        self.events.append(("launch", kwargs))
        return _Browser(self.events, self.fail_screenshot)


class _PlaywrightContext:
    def __init__(self, chromium: _Chromium) -> None:
        self.chromium = chromium

    def __enter__(self) -> SimpleNamespace:
        return SimpleNamespace(chromium=self.chromium)

    def __exit__(self, *_args: object) -> None:
        return None


def _install_playwright(
    monkeypatch: pytest.MonkeyPatch,
    events: list[tuple],
    *,
    fail_screenshot: bool = False,
) -> None:
    sync_api = types.ModuleType("playwright.sync_api")

    class FakeTimeoutError(Exception):
        pass

    sync_api.TimeoutError = FakeTimeoutError  # type: ignore[attr-defined]
    sync_api.sync_playwright = lambda: _PlaywrightContext(  # type: ignore[attr-defined]
        _Chromium(events, fail_screenshot)
    )
    package = types.ModuleType("playwright")
    package.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_observer_owns_one_browser_and_atomically_names_all_viewports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple] = []
    _install_playwright(monkeypatch, events)
    monkeypatch.setattr(
        runtime_observer,
        "uuid4",
        lambda: SimpleNamespace(hex="atomic"),
    )
    viewports = (
        RuntimeViewport("mobile", 375, 812),
        RuntimeViewport("desktop", 1280, 800),
    )

    observation = observe_frontend(
        "http://127.0.0.1:4173",
        viewports=viewports,
        screenshots_dir=tmp_path,
        screenshot_namer=lambda _url, viewport: f"after_{viewport.name}.png",
        settle_ms=1000,
    )

    assert sum(event[0] == "launch" for event in events) == 1
    assert all(
        event[1]["reduced_motion"] == "reduce"
        for event in events
        if event[0] == "context"
    )
    assert len(observation.pages) == 2
    assert [Path(page.screenshot or "").name for page in observation.pages] == [
        "after_mobile.png",
        "after_desktop.png",
    ]
    assert all(
        Path(page.screenshot or "").read_bytes() == b"partial-png"
        for page in observation.pages
    )
    assert {finding.code for finding in observation.pages[0].elements[0].findings} == {
        "runtime-line-spacing"
    }
    assert not list(tmp_path.glob(".*.tmp"))


def test_observer_screenshot_failure_preserves_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple] = []
    _install_playwright(monkeypatch, events, fail_screenshot=True)
    monkeypatch.setattr(
        runtime_observer,
        "uuid4",
        lambda: SimpleNamespace(hex="atomic"),
    )
    existing = tmp_path / "after_desktop.png"
    existing.write_bytes(b"known-good")

    observation = observe_frontend(
        "http://127.0.0.1:4173",
        viewports=(RuntimeViewport("desktop", 1280, 800),),
        screenshots_dir=tmp_path,
        screenshot_namer=lambda _url, _viewport: existing.name,
    )

    assert observation.pages == ()
    assert observation.errors
    assert existing.read_bytes() == b"known-good"
    assert not list(tmp_path.glob(".*.tmp"))


def test_observer_detects_rendered_layout_and_typography_defects(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "layout-defects.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  .row { display: flex; align-items: flex-start; gap: 8px; }
  .peer { width: 100px; height: 36px; padding: 8px 12px; }
  #misaligned { transform: translateY(7px); font-family: serif; }
  .grid { display: grid; grid-template-columns: repeat(3, 100px); gap: 8px; }
  #grid-misaligned { transform: translateY(7px); }
  #truncated { width: 70px; overflow: hidden; white-space: nowrap; }
  #ellipsis {
    width: 70px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  #card { width: 180px; padding: 2px; border: 1px solid black; }
  #tight { width: 110px; font-size: 16px; line-height: 17px; }
  #clip { width: 80px; height: 30px; overflow: clip; }
  #clip > div { width: 140px; height: 50px; }
  #ancestor-clip { width: 90px; overflow: hidden; white-space: nowrap; }
  #ancestor-clipped-text {
    display: inline-block;
    margin-left: 70px;
    width: 100px;
  }
  #badge { background: #eee; }
</style>
<main>
  <div class="row">
    <button class="peer">First</button>
    <button class="peer">Second</button>
    <button class="peer" id="misaligned">Third</button>
  </div>
  <div class="grid">
    <button class="peer">Alpha</button>
    <button class="peer">Beta</button>
    <button class="peer" id="grid-misaligned">Gamma</button>
  </div>
  <div class="row">
    <button class="peer">North</button>
    <button class="peer">South</button>
    <button class="peer" id="font-only" style="font-family: serif">West</button>
  </div>
  <button id="truncated">This label is deliberately too long</button>
  <button id="ellipsis">This label is intentionally shortened</button>
  <article id="card"><p>Card text</p></article>
  <p id="tight">Tight multiline text needs more leading.</p>
  <section id="clip"><div>Oversized child component</div></section>
  <div id="ancestor-clip">
    <span id="ancestor-clipped-text">Clipped by ancestor</span>
  </div>
  <span id="badge">New</span>
</main>
""".strip(),
        encoding="utf-8",
    )

    with _serve_directory(tmp_path) as origin:
        try:
            observation = observe_frontend(
                f"{origin}/{fixture.name}",
                viewports=(RuntimeViewport("desktop", 1280, 800),),
                settle_ms=0,
            )
        except RuntimeError as exc:
            if "playwright install chromium" in str(exc).lower():
                pytest.skip("Chromium is not installed for runtime integration tests.")
            raise

    findings_by_selector = {
        element.selector: {finding.code for finding in element.findings}
        for element in observation.pages[0].elements
        if element.findings
    }
    elements_by_selector = {
        element.selector: element for element in observation.pages[0].elements
    }

    assert "runtime-layout-misalignment" in findings_by_selector["#misaligned"]
    assert "runtime-font-misalignment" in findings_by_selector["#misaligned"]
    assert "runtime-layout-misalignment" in findings_by_selector["#grid-misaligned"]
    assert "runtime-font-misalignment" in findings_by_selector["#font-only"]
    assert "runtime-layout-misalignment" not in findings_by_selector["#font-only"]
    assert "runtime-text-clipped" in findings_by_selector["#truncated"]
    assert "runtime-text-truncated" in findings_by_selector["#ellipsis"]
    assert "runtime-text-clipped" not in findings_by_selector["#ellipsis"]
    assert "runtime-text-edge-contact" in findings_by_selector["#card"]
    assert "runtime-horizontal-padding" in findings_by_selector["#card"]
    assert "runtime-vertical-padding" not in findings_by_selector["#card"]
    assert "runtime-line-spacing" in findings_by_selector["#tight"]
    assert "runtime-component-clipped" in findings_by_selector["#clip"]
    assert "runtime-text-clipped" in findings_by_selector["#ancestor-clipped-text"]
    assert "#badge" not in findings_by_selector
    assert elements_by_selector["#tight"].measurements["fontStatus"] == "loaded"
    assert elements_by_selector["#tight"].measurements["fontReady"] is True
    assert elements_by_selector["#tight"].measurements["isTextFlow"] is True
    assert isinstance(
        elements_by_selector["#tight"].measurements["minimumLineGap"],
        (int, float),
    )
    assert isinstance(
        elements_by_selector["#misaligned"].measurements["fontBaselineProxy"],
        (int, float),
    )
    assert (
        elements_by_selector["#misaligned"].measurements["layoutPeerProvenance"]
        == "flex-row"
    )
    assert elements_by_selector["#card"].measurements["paddingInlineStart"] == 2
    assert (
        elements_by_selector["#ancestor-clipped-text"].measurements["clippedByAncestor"]
        is True
    )
    assert (
        elements_by_selector["#ancestor-clipped-text"].measurements[
            "clippingAncestorSelector"
        ]
        == "#ancestor-clip"
    )
