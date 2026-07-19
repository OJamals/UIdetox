"""Observe rendered frontend structure through a headless browser.

Playwright is an implementation detail behind :func:`observe_frontend`. The
returned value is plain, serializable evidence that can be merged into a
``FrontendMap`` or constructed directly by tests and other local adapters.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit
from uuid import uuid4

from uidetox.utils import now_iso


@dataclass(frozen=True)
class RuntimeViewport:
    name: str
    width: int
    height: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeViewport":
        return cls(
            name=str(value["name"]),
            width=int(value["width"]),
            height=int(value["height"]),
        )


DEFAULT_VIEWPORTS = (
    RuntimeViewport("mobile", 390, 844),
    RuntimeViewport("tablet", 768, 1024),
    RuntimeViewport("desktop", 1440, 900),
)


@dataclass(frozen=True)
class RuntimeElement:
    kind: str
    tag: str
    role: str
    name: str
    selector: str
    order: int
    bounds: dict[str, float]
    styles: dict[str, str]
    states: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeElement":
        bounds = value.get("bounds", {})
        styles = value.get("styles", {})
        states = value.get("states", {})
        return cls(
            kind=str(value.get("kind", "region")),
            tag=str(value.get("tag", "div")),
            role=str(value.get("role", "")),
            name=str(value.get("name", "")),
            selector=str(value.get("selector", "")),
            order=int(value.get("order", 0)),
            bounds={str(key): float(item) for key, item in dict(bounds).items()},
            styles={str(key): str(item) for key, item in dict(styles).items()},
            states=dict(states),
        )


@dataclass(frozen=True)
class RuntimePage:
    url: str
    title: str
    viewport: RuntimeViewport
    elements: tuple[RuntimeElement, ...]
    screenshot: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimePage":
        return cls(
            url=str(value["url"]),
            title=str(value.get("title", "")),
            viewport=RuntimeViewport.from_dict(dict(value["viewport"])),
            elements=tuple(
                RuntimeElement.from_dict(dict(item))
                for item in value.get("elements", [])
            ),
            screenshot=(
                str(value["screenshot"])
                if value.get("screenshot") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class RuntimeObservation:
    generated_at: str
    requested_urls: tuple[str, ...]
    pages: tuple[RuntimePage, ...]
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeObservation":
        return cls(
            generated_at=str(value.get("generated_at", "")),
            requested_urls=tuple(str(url) for url in value.get("requested_urls", [])),
            pages=tuple(
                RuntimePage.from_dict(dict(page)) for page in value.get("pages", [])
            ),
            errors=tuple(str(error) for error in value.get("errors", [])),
        )


def observe_frontend(
    urls: str | Iterable[str],
    *,
    viewports: Iterable[RuntimeViewport] = DEFAULT_VIEWPORTS,
    screenshots_dir: str | Path | None = None,
    timeout_ms: int = 15_000,
    screenshot_namer: Callable[[str, RuntimeViewport], str] | None = None,
    full_page: bool = True,
    settle_ms: int = 250,
) -> RuntimeObservation:
    """Observe initial rendered state for each URL and viewport.

    The caller must start the dev server. Individual navigation failures are
    recorded so other URLs/viewports can still complete; missing Playwright or
    browser binaries fail immediately with an actionable error.
    """

    normalized_urls = _normalize_urls(urls)
    normalized_viewports = tuple(viewports)
    if not normalized_viewports:
        raise ValueError("At least one runtime viewport is required.")
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be greater than zero.")
    if settle_ms < 0:
        raise ValueError("settle_ms must be zero or greater.")

    screenshot_root = None
    if screenshots_dir is not None:
        screenshot_root = Path(screenshots_dir).expanduser().resolve()
        screenshot_root.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright unavailable. Install with `pip install playwright` and "
            "`playwright install chromium`."
        ) from exc

    pages: list[RuntimePage] = []
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for url in normalized_urls:
                    for viewport in normalized_viewports:
                        context = browser.new_context(
                            viewport={"width": viewport.width, "height": viewport.height},
                            reduced_motion="no-preference",
                        )
                        page = context.new_page()
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                            try:
                                page.wait_for_load_state(
                                    "networkidle",
                                    timeout=min(3_000, timeout_ms),
                                )
                            except PlaywrightTimeoutError:
                                pass
                            page.wait_for_timeout(settle_ms)
                            payload = page.evaluate(_RUNTIME_EVALUATE_SCRIPT)
                            elements = _elements_from_payload(payload)
                            screenshot = None
                            if screenshot_root is not None:
                                screenshot_name = (
                                    screenshot_namer(page.url, viewport)
                                    if screenshot_namer is not None
                                    else _screenshot_name(page.url, viewport)
                                )
                                screenshot_path = _safe_screenshot_path(
                                    screenshot_root,
                                    screenshot_name,
                                )
                                _capture_screenshot_atomically(
                                    page,
                                    screenshot_path,
                                    full_page=full_page,
                                )
                                screenshot = str(screenshot_path)
                            pages.append(
                                RuntimePage(
                                    url=page.url,
                                    title=page.title(),
                                    viewport=viewport,
                                    elements=elements,
                                    screenshot=screenshot,
                                )
                            )
                        except Exception as exc:
                            errors.append(f"{url} [{viewport.name}]: {exc}")
                        finally:
                            context.close()
            finally:
                browser.close()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Playwright could not launch Chromium. Run `playwright install chromium`. "
            f"Original error: {exc}"
        ) from exc

    return RuntimeObservation(
        generated_at=now_iso(),
        requested_urls=normalized_urls,
        pages=tuple(pages),
        errors=tuple(errors),
    )


def _safe_screenshot_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if (
        not name
        or relative.is_absolute()
        or len(relative.parts) != 1
        or relative.suffix.lower() != ".png"
    ):
        raise ValueError(
            "Runtime screenshot names must be plain PNG filenames."
        )
    return root / relative


def _capture_screenshot_atomically(
    page: Any,
    destination: Path,
    *,
    full_page: bool,
) -> None:
    temporary = destination.with_name(
        f".{destination.name}.{uuid4().hex}.tmp"
    )
    try:
        page.screenshot(
            path=str(temporary),
            full_page=full_page,
            type="png",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_urls(urls: str | Iterable[str]) -> tuple[str, ...]:
    values = [urls] if isinstance(urls, str) else list(urls)
    normalized: list[str] = []
    for value in values:
        url = str(value).strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Runtime URL must be absolute HTTP(S): {url}")
        if url not in normalized:
            normalized.append(url)
    if not normalized:
        raise ValueError("At least one runtime URL is required.")
    return tuple(normalized)


def _elements_from_payload(payload: Any) -> tuple[RuntimeElement, ...]:
    if not isinstance(payload, list):
        raise ValueError("Runtime DOM observer returned a non-list payload.")
    return tuple(
        RuntimeElement.from_dict(item)
        for item in payload
        if isinstance(item, dict)
    )


def _screenshot_name(url: str, viewport: RuntimeViewport) -> str:
    parsed = urlsplit(url)
    readable = re.sub(
        r"[^A-Za-z0-9]+",
        "-",
        f"{parsed.netloc}{parsed.path}",
    ).strip("-")[:60] or "page"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{readable}-{digest}-{viewport.name}.png"


_RUNTIME_EVALUATE_SCRIPT = r"""
() => {
  const candidates = Array.from(document.querySelectorAll([
    "header", "nav", "main", "aside", "section", "article", "footer",
    "form", "table", "dialog", "button", "a[href]", "input", "select",
    "textarea", "[role]", "[tabindex]"
  ].join(",")));

  const implicitRole = (element) => {
    const tag = element.tagName.toLowerCase();
    const type = (element.getAttribute("type") || "").toLowerCase();
    if (tag === "a" && element.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "nav") return "navigation";
    if (tag === "main") return "main";
    if (tag === "aside") return "complementary";
    if (tag === "header") return "banner";
    if (tag === "footer") return "contentinfo";
    if (tag === "form") return "form";
    if (tag === "table") return "table";
    if (tag === "dialog") return "dialog";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input" && ["button", "submit", "reset"].includes(type)) return "button";
    if (tag === "input" && type === "checkbox") return "checkbox";
    if (tag === "input" && type === "radio") return "radio";
    if (tag === "input") return "textbox";
    return "";
  };

  const selectorFor = (element) => {
    const testId = element.getAttribute("data-testid");
    if (testId) return `[data-testid="${testId.replaceAll('"', '\\"')}"]`;
    if (element.id) return `#${CSS.escape(element.id)}`;
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 4) {
      const tag = current.tagName.toLowerCase();
      const siblings = current.parentElement
        ? Array.from(current.parentElement.children).filter(item => item.tagName === current.tagName)
        : [];
      const suffix = siblings.length > 1 ? `:nth-of-type(${siblings.indexOf(current) + 1})` : "";
      parts.unshift(`${tag}${suffix}`);
      current = current.parentElement;
    }
    return parts.join(" > ");
  };

  const nameFor = (element) => {
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      const value = labelledBy.split(/\s+/).map(id => document.getElementById(id)?.textContent || "").join(" ").trim();
      if (value) return value;
    }
    const explicit = element.getAttribute("aria-label")
      || element.getAttribute("alt")
      || element.getAttribute("title")
      || element.labels?.[0]?.textContent
      || element.getAttribute("placeholder")
      || element.textContent
      || "";
    return explicit.replace(/\s+/g, " ").trim().slice(0, 160);
  };

  const interactiveRoles = new Set([
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "menuitem", "option", "slider", "spinbutton", "switch", "tab"
  ]);

  return candidates.map((element, order) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      rect.width <= 0 ||
      rect.height <= 0
    ) return null;

    const tag = element.tagName.toLowerCase();
    const role = element.getAttribute("role") || implicitRole(element);
    const kind = interactiveRoles.has(role) || element.matches("button,a[href],input,select,textarea,[tabindex]")
      ? "action"
      : "region";
    const states = {};
    for (const attribute of ["aria-expanded", "aria-checked", "aria-selected", "aria-pressed", "aria-current", "aria-invalid"]) {
      if (element.hasAttribute(attribute)) states[attribute] = element.getAttribute(attribute);
    }
    if ("disabled" in element) states.disabled = Boolean(element.disabled);
    states.tabIndex = element.tabIndex;

    return {
      kind,
      tag,
      role,
      name: nameFor(element),
      selector: selectorFor(element),
      order,
      bounds: {
        x: Math.round(rect.x * 100) / 100,
        y: Math.round(rect.y * 100) / 100,
        width: Math.round(rect.width * 100) / 100,
        height: Math.round(rect.height * 100) / 100
      },
      styles: {
        display: style.display,
        position: style.position,
        color: style.color,
        backgroundColor: style.backgroundColor,
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        gap: style.gap,
        gridTemplateColumns: style.gridTemplateColumns
      },
      states
    };
  }).filter(Boolean).slice(0, 1000);
}
"""
