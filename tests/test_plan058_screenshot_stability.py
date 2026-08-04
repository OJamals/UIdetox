from __future__ import annotations

from pathlib import Path

from uidetox.runtime_observer import _capture_screenshot_atomically


class _Page:
    def __init__(self) -> None:
        self.options: dict[str, object] = {}

    def screenshot(self, **options: object) -> None:
        self.options = options
        Path(str(options["path"])).write_bytes(b"stable")


def test_plan058_screenshot_capture_disables_animations(tmp_path: Path) -> None:
    page = _Page()
    destination = tmp_path / "capture.png"

    _capture_screenshot_atomically(page, destination, full_page=True)

    assert destination.read_bytes() == b"stable"
    assert page.options["animations"] == "disabled"
    assert page.options["full_page"] is True
    assert page.options["type"] == "png"
