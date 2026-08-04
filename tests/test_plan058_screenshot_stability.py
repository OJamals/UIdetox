from __future__ import annotations

from pathlib import Path

from uidetox.runtime_observer import (
    _capture_screenshot_atomically,
    _stabilize_action_viewport,
)


class _Page:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def screenshot(self, **options: object) -> None:
        self.options = options
        Path(str(options["path"])).write_bytes(b"stable")


class _Locator:
    def __init__(self) -> None:
        self.script = ""

    def evaluate(self, script: str) -> None:
        self.script = script


def test_plan058_screenshot_capture_disables_animations(tmp_path: Path) -> None:
    page = _Page()
    destination = tmp_path / "capture.png"

    _capture_screenshot_atomically(page, destination, full_page=True)

    assert destination.read_bytes() == b"stable"
    assert page.options["animations"] == "disabled"
    assert page.options["style"] == "* { caret-color: transparent !important; }"
    assert page.options["full_page"] is True
    assert page.options["type"] == "png"


def test_plan058_action_stabilization_uses_exact_document_scroll_target() -> None:
    locator = _Locator()

    _stabilize_action_viewport(locator)

    assert "new Promise(resolve => requestAnimationFrame" in locator.script
    assert locator.script.count("requestAnimationFrame") == 2
    assert "element.scrollIntoView" in locator.script
    assert "rect.top + root.scrollTop" in locator.script
    assert "Math.round(documentTop - (window.innerHeight - rect.height) / 2)" in (
        locator.script
    )
    assert "root.scrollTo({top: targetTop, behavior: 'instant'})" in locator.script
