from __future__ import annotations

import pytest

from uidetox.design_semantics import detect_design_findings
from uidetox.runtime_observer import RuntimeElement, RuntimePage
from uidetox.runtime_scenarios import RuntimeViewport


def _geometry(selector: str, *, y: float, height: float) -> dict[str, object]:
    return {
        "selector": selector,
        "x": 0.0,
        "y": y,
        "width": 1280.0,
        "height": height,
    }


def _page(composition: object) -> RuntimePage:
    return RuntimePage(
        url="https://example.test/tasks",
        title="Tasks",
        viewport=RuntimeViewport("desktop", 1280, 800),
        elements=(
            RuntimeElement(
                kind="region",
                tag="main",
                role="main",
                name="Tasks",
                selector="main",
                order=0,
                bounds={"x": 0.0, "y": 0.0, "width": 1280.0, "height": 1600.0},
                styles={},
                measurements={"pageComposition": composition},
            ),
        ),
    )


def _composition() -> dict[str, object]:
    return {
        "adaptation": {},
        "contentBounds": _geometry("main", y=0.0, height=1600.0),
        "documentBounds": _geometry("document", y=0.0, height=1600.0),
        "firstTaskContent": _geometry("#task-table", y=560.0, height=400.0),
        "landmarks": {
            "main": _geometry("main", y=0.0, height=1600.0),
            "headers": [_geometry("header", y=0.0, height=200.0)],
            "navigations": [_geometry("nav", y=200.0, height=240.0)],
        },
        "majorTracks": [],
        "truncated": False,
        "viewportBounds": _geometry("viewport", y=0.0, height=800.0),
    }


def _codes(page: RuntimePage) -> set[str]:
    return {
        finding.code
        for findings in detect_design_findings(page)
        for finding in findings
    }


def test_task_content_delayed_by_proven_pre_task_chrome() -> None:
    findings = detect_design_findings(_page(_composition()))[0]
    finding = next(
        item
        for item in findings
        if item.code == "design-primary-content-delayed-by-chrome"
    )

    assert finding.metrics["task_start_ratio"] == pytest.approx(0.7)
    assert finding.metrics["chrome_coverage_ratio"] == pytest.approx(0.55)
    assert finding.metrics["task_selector"] == "#task-table"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.update(truncated=True),
        lambda value: value.pop("firstTaskContent"),
        lambda value: value.update(
            firstTaskContent=_geometry("#task", y=439, height=1)
        ),
        lambda value: value["landmarks"].update(navigations=[]),
        lambda value: value["landmarks"].update(
            headers=[_geometry("header", y=0, height=100)],
            navigations=[_geometry("nav", y=100, height=100)],
        ),
        lambda value: value.update(
            firstTaskContent={
                **_geometry("#task", y=560, height=1),
                "selector": "x" * 513,
            }
        ),
    ),
)
def test_task_content_chrome_finding_fails_closed(mutation: object) -> None:
    composition = _composition()
    mutation(composition)  # type: ignore[operator]

    assert "design-primary-content-delayed-by-chrome" not in _codes(_page(composition))


def test_task_content_chrome_finding_requires_main_region() -> None:
    page = _page(_composition())
    element = page.elements[0]
    non_main = RuntimeElement(
        kind=element.kind,
        tag="section",
        role="region",
        name=element.name,
        selector=element.selector,
        order=element.order,
        bounds=element.bounds,
        styles=element.styles,
        measurements=element.measurements,
    )

    assert "design-primary-content-delayed-by-chrome" not in _codes(
        RuntimePage(
            url=page.url,
            title=page.title,
            viewport=page.viewport,
            elements=(non_main,),
        )
    )
