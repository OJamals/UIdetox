"""Browser-boundary tests for the shared runtime observer."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox import runtime_observer
from uidetox.runtime_observer import RuntimeViewport, observe_frontend


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
    assert len(observation.pages) == 2
    assert [Path(page.screenshot or "").name for page in observation.pages] == [
        "after_mobile.png",
        "after_desktop.png",
    ]
    assert all(Path(page.screenshot or "").read_bytes() == b"partial-png" for page in observation.pages)
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
