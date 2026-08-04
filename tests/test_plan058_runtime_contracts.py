from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields
from inspect import signature
from pathlib import Path

import pytest

from uidetox import runtime_observer
from uidetox.frontend_map import map_frontend
from uidetox.runtime_layout import detect_runtime_findings
from uidetox.runtime_observer import (
    RuntimeElement,
    RuntimeObservation,
    RuntimePage,
    observe_frontend,
)
from uidetox.runtime_scenarios import (
    RuntimeDomBudget,
    RuntimeReadiness,
    RuntimeScenario,
    RuntimeViewport,
    runtime_capture_id,
)

_VIEWPORT = RuntimeViewport("desktop", 1280, 800)


def _element(
    *,
    selector: str = "main",
    role: str = "main",
    name: str = "Primary content",
    order: int = 0,
    measurements: dict[str, object] | None = None,
) -> RuntimeElement:
    return RuntimeElement(
        kind="region",
        tag="main" if role == "main" else "nav",
        role=role,
        name=name,
        selector=selector,
        order=order,
        bounds={"x": 0.0, "y": 0.0, "width": 800.0, "height": 600.0},
        styles={},
        measurements=measurements or {},
    )


def _observation(*pages: RuntimePage) -> RuntimeObservation:
    return RuntimeObservation(
        generated_at="2026-08-04T00:00:00+00:00",
        requested_urls=tuple(page.url for page in pages),
        pages=pages,
    )


def _skip_missing_browser(exc: RuntimeError) -> None:
    if "Playwright could not launch Chromium" in str(exc):
        pytest.skip(str(exc))


class _CapturePage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.evaluate_calls = 0
        self.screenshot_calls = 0

    def evaluate(self, _script: str) -> list[dict[str, object]]:
        self.evaluate_calls += 1
        return [
            {
                "kind": "region",
                "tag": "main",
                "role": "main",
                "name": "Primary content",
                "selector": "main",
                "order": 0,
                "bounds": {"x": 0, "y": 0, "width": 800, "height": 600},
                "styles": {},
                "states": {},
                "measurements": {},
            }
        ]

    def screenshot(self, **kwargs: object) -> None:
        self.screenshot_calls += 1
        Path(str(kwargs["path"])).write_bytes(b"stable-plan058-png")

    def title(self) -> str:
        return "Plan 058"


def test_plan058_freezes_runtime_public_signatures() -> None:
    assert tuple(field.name for field in fields(RuntimeElement)) == (
        "kind",
        "tag",
        "role",
        "name",
        "selector",
        "order",
        "bounds",
        "styles",
        "source_hint",
        "source_selectors",
        "states",
        "measurements",
        "findings",
    )
    assert tuple(field.name for field in fields(RuntimePage)) == (
        "url",
        "title",
        "viewport",
        "elements",
        "screenshot",
        "capture_id",
        "scenario",
        "state",
    )
    assert tuple(field.name for field in fields(RuntimeObservation)) == (
        "generated_at",
        "requested_urls",
        "pages",
        "errors",
        "captures",
        "viewport_discovery",
        "status",
    )
    assert tuple(signature(RuntimeElement).parameters) == tuple(
        field.name for field in fields(RuntimeElement)
    )
    assert tuple(signature(RuntimePage).parameters) == tuple(
        field.name for field in fields(RuntimePage)
    )
    assert tuple(signature(RuntimeObservation).parameters) == tuple(
        field.name for field in fields(RuntimeObservation)
    )


def test_plan058_freezes_capture_identity_status_and_serialized_order() -> None:
    page = RuntimePage(
        url="https://example.test/dashboard",
        title="Dashboard",
        viewport=_VIEWPORT,
        elements=(_element(),),
    )
    observation = _observation(page)
    payload = observation.to_dict()

    assert observation.status == "current"
    assert observation.pages[0].capture_id == runtime_capture_id(
        "default",
        "initial",
        page.url,
        _VIEWPORT,
    )
    assert list(payload) == [
        "generated_at",
        "requested_urls",
        "pages",
        "errors",
        "captures",
        "viewport_discovery",
        "status",
    ]
    assert list(payload["pages"][0]) == [
        "url",
        "title",
        "viewport",
        "elements",
        "screenshot",
        "capture_id",
        "scenario",
        "state",
    ]
    assert list(payload["pages"][0]["elements"][0]) == [
        "kind",
        "tag",
        "role",
        "name",
        "selector",
        "order",
        "bounds",
        "styles",
        "source_hint",
        "source_selectors",
        "states",
        "measurements",
        "findings",
    ]
    assert RuntimeObservation.from_dict(payload).to_dict() == payload


def test_plan058_capture_uses_one_evaluate_and_repeats_identically(
    tmp_path: Path,
) -> None:
    scenario = RuntimeScenario(name="default", url="https://example.test/dashboard")
    readiness = RuntimeReadiness(status="ready", strategy="load", duration_ms=0)
    page = _CapturePage(scenario.url)
    screenshots = tmp_path / "screenshots"
    screenshots.mkdir()

    first, _ = runtime_observer._capture_scenario_state(
        page,
        scenario=scenario,
        state="initial",
        viewport=_VIEWPORT,
        readiness=readiness,
        diagnostics=[],
        dom_budget=RuntimeDomBudget(scan=10, candidates=10),
        started_at="2026-08-04T00:00:00+00:00",
        screenshot_root=screenshots,
        screenshot_namer=lambda _url, _viewport: "stable.png",
        full_page=True,
    )
    assert page.evaluate_calls == 1
    first_bytes = Path(str(first.screenshot)).read_bytes()

    second, _ = runtime_observer._capture_scenario_state(
        page,
        scenario=scenario,
        state="initial",
        viewport=_VIEWPORT,
        readiness=readiness,
        diagnostics=[],
        dom_budget=RuntimeDomBudget(scan=10, candidates=10),
        started_at="2026-08-04T00:00:00+00:00",
        screenshot_root=screenshots,
        screenshot_namer=lambda _url, _viewport: "stable.png",
        full_page=True,
    )

    assert page.evaluate_calls == 2
    assert page.screenshot_calls == 2
    assert second.capture_id == first.capture_id
    assert second.elements == first.elements
    assert Path(str(second.screenshot)).read_bytes() == first_bytes


def test_plan058_freezes_map_order_with_and_without_runtime(tmp_path: Path) -> None:
    source = tmp_path / "src" / "App.tsx"
    source.parent.mkdir()
    source.write_text(
        "export function App() { return <main>Primary content</main>; }",
        encoding="utf-8",
    )
    page = RuntimePage(
        url="https://example.test/dashboard",
        title="Dashboard",
        viewport=_VIEWPORT,
        elements=(_element(),),
    )

    static_map = map_frontend(tmp_path)
    runtime_map = map_frontend(tmp_path, runtime=_observation(page))

    for frontend_map in (static_map, runtime_map):
        assert list(frontend_map.nodes) == sorted(
            frontend_map.nodes,
            key=lambda node: (node.file, node.line, node.kind, node.name, node.id),
        )
        assert list(frontend_map.edges) == sorted(
            frontend_map.edges,
            key=lambda edge: (edge.source, edge.kind, edge.target),
        )
        findings = frontend_map.evidence["runtime_findings"]
        assert findings == sorted(
            findings,
            key=lambda finding: (
                finding["url"],
                finding["viewport"],
                finding["selector"],
                finding["code"],
            ),
        )


def test_plan058_focus_obscuration_is_measured_and_modal_background_is_suppressed() -> (
    None
):
    obscured = _element(
        role="button",
        selector="#save",
        measurements={
            "focusVisibility": {
                "fullyVisible": False,
                "occludedBy": "#sticky-header",
                "occludedFraction": 0.4,
            }
        },
    )
    visible = _element(
        role="button",
        selector="#cancel",
        measurements={
            "focusVisibility": {
                "fullyVisible": True,
                "occludedBy": "",
                "occludedFraction": 0.0,
            }
        },
    )
    modal_background = _element(
        role="button",
        selector="#background",
        measurements={
            "obscuredByModal": True,
            "focusVisibility": {
                "fullyVisible": False,
                "occludedBy": "dialog",
                "occludedFraction": 1.0,
            },
        },
    )

    assert "runtime-focus-obscured" in {
        finding.code for finding in detect_runtime_findings(obscured)
    }
    assert "runtime-focus-obscured" not in {
        finding.code for finding in detect_runtime_findings(visible)
    }
    assert detect_runtime_findings(modal_background) == ()


def test_plan058_browser_emits_bounded_page_composition_evidence(
    tmp_path: Path,
    local_http_server: Callable[[Path], str],
) -> None:
    hostile = "HOSTILE-" + ("x" * 20_000)
    fixture = tmp_path / "page-composition.html"
    fixture.write_text(
        f"""
<!doctype html>
<header><nav aria-label="Primary">
  <a href="/home">Home</a>
  <a href="/{hostile}">Hostile destination</a>
</nav></header>
<h1 id="hostile-heading">{hostile}</h1>
<main aria-labelledby="hostile-heading" data-hostile="{hostile}">
  <button>Continue</button>
</main>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)
    try:
        observation = observe_frontend(
            f"{origin}/{fixture.name}",
            viewports=(_VIEWPORT,),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    main = next(
        element for element in observation.pages[0].elements if element.role == "main"
    )
    navigation = next(
        element
        for element in observation.pages[0].elements
        if element.role == "navigation"
    )
    evidence = main.measurements["pageComposition"]

    assert set(evidence) == {
        "adaptation",
        "contentBounds",
        "documentBounds",
        "firstTaskContent",
        "landmarks",
        "majorTracks",
        "truncated",
        "viewportBounds",
    }
    assert evidence["landmarks"]["main"]["selector"] == "html > body > main"
    assert len(main.name) == 160
    encoded = json.dumps(evidence, sort_keys=True)
    assert hostile not in encoded
    assert len(encoded.encode("utf-8")) <= 4096
    assert navigation.measurements["navigation"]["truncated"] is True
    assert navigation.measurements["navigation"]["destinations"][-1]["identity"] == ""
    payload = json.dumps(observation.to_dict(), sort_keys=True)
    assert hostile not in payload
    assert len(payload.encode("utf-8")) <= 50_000


def test_plan058_cross_route_navigation_continuity_is_reported(
    tmp_path: Path,
    local_http_server: Callable[[Path], str],
) -> None:
    pages = {
        "alpha.html": """
<nav aria-label="Primary">
  <a href="/alpha.html" aria-current="page">Alpha</a>
  <a href="/beta.html">Beta</a>
  <a href="/help.html">Help</a>
</nav><main><h1>Alpha</h1></main>
""",
        "beta.html": """
<nav aria-label="Primary">
  <a href="/help.html">Help</a>
  <a href="/beta.html" aria-current="page">Beta</a>
  <a href="/alpha.html">Alpha</a>
</nav><main><h1>Beta</h1></main>
""",
    }
    for name, content in pages.items():
        (tmp_path / name).write_text(content.strip(), encoding="utf-8")
    origin = local_http_server(tmp_path)
    urls = tuple(f"{origin}/{name}" for name in pages)
    try:
        observation = observe_frontend(
            urls,
            viewports=(_VIEWPORT,),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    frontend_map = map_frontend(tmp_path, runtime=observation)
    codes = {finding["code"] for finding in frontend_map.evidence["runtime_findings"]}

    assert "design-navigation-order-inconsistent" in codes


@pytest.mark.parametrize(
    ("orders", "truncated"),
    [
        ((("/alpha", "/beta"), ("/alpha", "/beta")), False),
        ((("/alpha", "/beta"), ("/alpha", "/help")), False),
        ((("/alpha", "/alpha"), ("/alpha", "/alpha")), False),
        ((("/alpha", "/beta"), ("/beta", "/alpha")), True),
    ],
)
def test_plan058_navigation_continuity_fails_closed(
    tmp_path: Path,
    orders: tuple[tuple[str, ...], tuple[str, ...]],
    truncated: bool,
) -> None:
    pages = tuple(
        RuntimePage(
            url=f"https://example.test/{index}",
            title=str(index),
            viewport=_VIEWPORT,
            elements=(
                _element(
                    selector="nav",
                    role="navigation",
                    measurements={
                        "navigation": {
                            "destinations": [
                                {"identity": destination, "order": order}
                                for order, destination in enumerate(destinations)
                            ],
                            "identity": "Primary",
                            "truncated": truncated,
                        }
                    },
                ),
            ),
        )
        for index, destinations in enumerate(orders)
    )

    frontend_map = map_frontend(tmp_path, runtime=_observation(*pages))
    codes = {finding["code"] for finding in frontend_map.evidence["runtime_findings"]}

    assert "design-navigation-order-inconsistent" not in codes


def test_plan058_navigation_continuity_rejects_partial_observation(
    tmp_path: Path,
) -> None:
    pages = tuple(
        RuntimePage(
            url=f"https://example.test/{index}",
            title=str(index),
            viewport=_VIEWPORT,
            elements=(
                _element(
                    selector="nav",
                    role="navigation",
                    measurements={
                        "navigation": {
                            "destinations": [
                                {"identity": destination, "order": order}
                                for order, destination in enumerate(destinations)
                            ],
                            "identity": "Primary",
                            "truncated": False,
                        }
                    },
                ),
            ),
        )
        for index, destinations in enumerate((("/alpha", "/beta"), ("/beta", "/alpha")))
    )
    observation = RuntimeObservation(
        generated_at="2026-08-04T00:00:00+00:00",
        requested_urls=tuple(page.url for page in pages),
        pages=pages,
        errors=("one route capture failed",),
    )

    assert observation.status == "partial"
    frontend_map = map_frontend(tmp_path, runtime=observation)
    codes = {finding["code"] for finding in frontend_map.evidence["runtime_findings"]}
    assert "design-navigation-order-inconsistent" not in codes
