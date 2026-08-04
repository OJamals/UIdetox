from __future__ import annotations

import pytest

from uidetox.runtime_layout import detect_runtime_findings
from uidetox.runtime_observer import RuntimeElement


def _element(**measurements: object) -> RuntimeElement:
    return RuntimeElement(
        kind="action",
        tag="div",
        role="region",
        name="",
        selector="#fixture",
        order=0,
        bounds={"x": 0, "y": 0, "width": 320, "height": 240},
        styles={},
        measurements=measurements,
    )


def _codes(**measurements: object) -> set[str]:
    return {
        finding.code for finding in detect_runtime_findings(_element(**measurements))
    }


def test_plan058_reports_vertical_task_action_concealment() -> None:
    findings = detect_runtime_findings(
        _element(
            isScrollRegionY=True,
            clientHeight=240,
            scrollHeight=720,
            concealedInteractiveDescendantCountY=2,
        )
    )

    assert [finding.code for finding in findings] == [
        "runtime-interactive-scroll-concealment"
    ]
    assert findings[0].metrics == {
        "concealed_action_count": 2.0,
        "client_height_px": 240.0,
        "scroll_height_px": 720.0,
        "scroll_height_ratio": 3.0,
    }


@pytest.mark.parametrize(
    "measurements",
    [
        {},
        {
            "isScrollRegionY": True,
            "clientHeight": 240,
            "scrollHeight": 241,
            "concealedInteractiveDescendantCountY": 2,
        },
        {
            "isScrollRegionY": True,
            "clientHeight": 240,
            "scrollHeight": 720,
            "concealedInteractiveDescendantCountY": 0,
        },
        {
            "isScrollRegionY": True,
            "clientHeight": 0,
            "scrollHeight": 720,
            "concealedInteractiveDescendantCountY": 2,
        },
        {
            "isScrollRegionY": False,
            "clientHeight": 240,
            "scrollHeight": 720,
            "concealedInteractiveDescendantCountY": 2,
        },
        {
            "obscuredByModal": True,
            "isScrollRegionY": True,
            "clientHeight": 240,
            "scrollHeight": 720,
            "concealedInteractiveDescendantCountY": 2,
        },
    ],
)
def test_plan058_vertical_concealment_fails_closed(
    measurements: dict[str, object],
) -> None:
    assert "runtime-interactive-scroll-concealment" not in _codes(**measurements)


def test_plan058_reports_inaccessible_responsive_table() -> None:
    assert _codes(
        table={
            "affordance": False,
            "headerCount": 4,
            "rowCount": 12,
            "scrollable": True,
            "scrollbarVisible": False,
        }
    ) == {"runtime-responsive-table-inaccessible"}


@pytest.mark.parametrize(
    "table",
    [
        None,
        {},
        {
            "affordance": False,
            "headerCount": 0,
            "rowCount": 12,
            "scrollable": True,
            "scrollbarVisible": False,
        },
        {
            "affordance": False,
            "headerCount": 4,
            "rowCount": 1,
            "scrollable": True,
            "scrollbarVisible": False,
        },
        {
            "affordance": True,
            "headerCount": 4,
            "rowCount": 12,
            "scrollable": True,
            "scrollbarVisible": False,
        },
        {
            "affordance": False,
            "headerCount": 4,
            "rowCount": 12,
            "scrollable": True,
            "scrollbarVisible": True,
        },
        {
            "affordance": False,
            "headerCount": 4,
            "rowCount": 12,
            "scrollable": False,
            "scrollbarVisible": False,
        },
    ],
)
def test_plan058_responsive_table_fails_closed(table: object) -> None:
    assert "runtime-responsive-table-inaccessible" not in _codes(table=table)
