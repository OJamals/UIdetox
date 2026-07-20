"""Observe rendered frontend structure through a headless browser.

Playwright is an implementation detail behind :func:`observe_frontend`. The
returned value is plain, serializable evidence that can be merged into a
``FrontendMap`` or constructed directly by tests and other local adapters.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit
from uuid import uuid4

from uidetox.capabilities import (
    capture_install_guidance,
    chromium_install_guidance,
)
from uidetox.runtime_layout import RuntimeFinding, detect_runtime_findings
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
    measurements: dict[str, Any] = field(default_factory=dict)
    findings: tuple[RuntimeFinding, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeElement":
        bounds = value.get("bounds", {})
        styles = value.get("styles", {})
        states = value.get("states", {})
        measurements = value.get("measurements", {})
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
            measurements=(
                dict(measurements) if isinstance(measurements, dict) else {}
            ),
            findings=tuple(
                RuntimeFinding.from_dict(dict(item))
                for item in value.get("findings", [])
                if isinstance(item, dict)
            ),
        )


def _attach_runtime_findings(
    elements: tuple[RuntimeElement, ...],
) -> tuple[RuntimeElement, ...]:
    return tuple(
        replace(element, findings=detect_runtime_findings(element))
        for element in elements
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
            f"Playwright unavailable. {capture_install_guidance()}"
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
                            viewport={
                                "width": viewport.width,
                                "height": viewport.height,
                            },
                            reduced_motion="no-preference",
                        )
                        page = context.new_page()
                        try:
                            page.goto(
                                url, wait_until="domcontentloaded", timeout=timeout_ms
                            )
                            try:
                                page.wait_for_load_state(
                                    "networkidle",
                                    timeout=min(3_000, timeout_ms),
                                )
                            except PlaywrightTimeoutError:
                                pass
                            page.wait_for_timeout(settle_ms)
                            payload = page.evaluate(_RUNTIME_EVALUATE_SCRIPT)
                            elements = _attach_runtime_findings(
                                _elements_from_payload(payload)
                            )
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
            "Playwright could not launch Chromium. "
            f"{chromium_install_guidance()}. "
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
        raise ValueError("Runtime screenshot names must be plain PNG filenames.")
    return root / relative


def _capture_screenshot_atomically(
    page: Any,
    destination: Path,
    *,
    full_page: bool,
) -> None:
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
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
        RuntimeElement.from_dict(item) for item in payload if isinstance(item, dict)
    )


def _screenshot_name(url: str, viewport: RuntimeViewport) -> str:
    parsed = urlsplit(url)
    readable = (
        re.sub(
            r"[^A-Za-z0-9]+",
            "-",
            f"{parsed.netloc}{parsed.path}",
        ).strip("-")[:60]
        or "page"
    )
    digest = hashlib.sha1(
        url.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    return f"{readable}-{digest}-{viewport.name}.png"


_RUNTIME_EVALUATE_SCRIPT = r"""
() => {
  const structuralCandidates = Array.from(document.querySelectorAll([
    "header", "nav", "main", "aside", "section", "article", "footer",
    "form", "table", "dialog", "button", "a[href]", "input", "select",
    "textarea", "[role]", "[tabindex]"
  ].join(",")));
  const allElements = Array.from(document.body?.querySelectorAll("*") || [])
    .slice(0, 3000);
  const round = value => Math.round(value * 100) / 100;
  const pixels = value => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

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

  const isVisible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return !(
      style.display === "none" ||
      style.visibility === "hidden" ||
      Number(style.opacity) === 0 ||
      rect.width <= 0 ||
      rect.height <= 0
    );
  };

  const textGeometry = (element, style, rect) => {
    const text = (element.innerText || element.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) return null;
    const range = document.createRange();
    range.selectNodeContents(element);
    const rects = Array.from(range.getClientRects()).filter(
      item => item.width > 0 && item.height > 0
    );
    if (!rects.length) return null;
    const left = Math.min(...rects.map(item => item.left));
    const right = Math.max(...rects.map(item => item.right));
    const top = Math.min(...rects.map(item => item.top));
    const bottom = Math.max(...rects.map(item => item.bottom));
    const lineTops = [];
    for (const item of [...rects].sort((a, b) => a.top - b.top)) {
      if (!lineTops.some(value => Math.abs(value - item.top) <= 1)) {
        lineTops.push(item.top);
      }
    }
    const fontSize = pixels(style.fontSize);
    return {
      text,
      bounds: {left, right, top, bottom},
      lineCount: lineTops.length,
      fontSize,
      lineHeight: style.lineHeight === "normal"
        ? fontSize * 1.2
        : pixels(style.lineHeight),
      insets: {
        top: top - rect.top,
        right: rect.right - right,
        bottom: rect.bottom - bottom,
        left: left - rect.left
      }
    };
  };

  const isControl = (element, role) => (
    interactiveRoles.has(role) ||
    element.matches("button,a[href],input,select,textarea,[tabindex]")
  );

  const isVisualContainer = (element, style) => {
    const tag = element.tagName.toLowerCase();
    const parentBackground = element.parentElement
      ? getComputedStyle(element.parentElement).backgroundColor
      : "";
    const hasBorder = [
      style.borderTopWidth,
      style.borderRightWidth,
      style.borderBottomWidth,
      style.borderLeftWidth
    ].some(value => pixels(value) > 0);
    const hasDistinctBackground = (
      style.backgroundColor !== "rgba(0, 0, 0, 0)" &&
      style.backgroundColor !== "transparent" &&
      style.backgroundColor !== parentBackground
    );
    const hasContainerName = /(?:card|panel|tile|surface)/i.test(
      `${element.id} ${element.className || ""}`
    );
    return (
      ["article", "dialog"].includes(tag) ||
      hasContainerName ||
      (element.children.length > 0 && (hasBorder || hasDistinctBackground))
    );
  };

  const measurementCache = new Map();
  const baseMeasurement = (element) => {
    if (measurementCache.has(element)) return measurementCache.get(element);
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const role = element.getAttribute("role") || implicitRole(element);
    const text = textGeometry(element, style, rect);
    const control = isControl(element, role);
    const visualContainer = isVisualContainer(element, style);
    const clipsX = ["clip", "hidden"].includes(style.overflowX);
    const clipsY = ["clip", "hidden"].includes(style.overflowY);
    let descendantClipped = false;
    if ((clipsX || clipsY) && element.children.length) {
      const contentLeft = rect.left + pixels(style.borderLeftWidth);
      const contentRight = rect.right - pixels(style.borderRightWidth);
      const contentTop = rect.top + pixels(style.borderTopWidth);
      const contentBottom = rect.bottom - pixels(style.borderBottomWidth);
      descendantClipped = Array.from(element.querySelectorAll("*")).some(child => {
        if (!isVisible(child)) return false;
        const childRect = child.getBoundingClientRect();
        return (
          (clipsX && (
            childRect.left < contentLeft - 1 ||
            childRect.right > contentRight + 1
          )) ||
          (clipsY && (
            childRect.top < contentTop - 1 ||
            childRect.bottom > contentBottom + 1
          ))
        );
      });
    }
    const measurements = {
      hasText: Boolean(text),
      isMultiline: Boolean(text && text.lineCount > 1),
      lineCount: text?.lineCount || 0,
      fontSize: round(text?.fontSize || pixels(style.fontSize)),
      lineHeight: round(text?.lineHeight || pixels(style.lineHeight)),
      fontFamily: style.fontFamily,
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      overflowX: style.overflowX,
      overflowY: style.overflowY,
      descendantClipped,
      isControl: control,
      isVisualContainer: visualContainer,
      paddingTop: round(pixels(style.paddingTop)),
      paddingRight: round(pixels(style.paddingRight)),
      paddingBottom: round(pixels(style.paddingBottom)),
      paddingLeft: round(pixels(style.paddingLeft))
    };
    if (text) {
      measurements.textInsetTop = round(text.insets.top);
      measurements.textInsetRight = round(text.insets.right);
      measurements.textInsetBottom = round(text.insets.bottom);
      measurements.textInsetLeft = round(text.insets.left);
      measurements.textBaseline = round(text.bounds.bottom);
    }
    const result = {style, rect, role, text, measurements};
    measurementCache.set(element, result);
    return result;
  };

  const median = values => {
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  };

  const clusteredPeerDeviation = (values, index) => {
    const peers = values.filter((_value, peerIndex) => peerIndex !== index);
    if (peers.length < 2 || Math.max(...peers) - Math.min(...peers) > 2) {
      return 0;
    }
    return Math.abs(values[index] - median(peers));
  };

  const enrichPeerMeasurements = (element, measurements) => {
    const parent = element.parentElement;
    if (!parent) return;
    const parentStyle = getComputedStyle(parent);
    if (parentStyle.display !== "flex") return;
    const siblings = Array.from(parent.children)
      .filter(isVisible)
      .slice(0, 20);
    if (siblings.length < 3 || !siblings.includes(element)) return;
    const index = siblings.indexOf(element);
    const row = !parentStyle.flexDirection.startsWith("column");
    const anchors = row
      ? [
          siblings.map(item => baseMeasurement(item).rect.top),
          siblings.map(item => {
            const rect = baseMeasurement(item).rect;
            return rect.top + rect.height / 2;
          }),
          siblings.map(item => baseMeasurement(item).rect.bottom)
        ]
      : [
          siblings.map(item => baseMeasurement(item).rect.left),
          siblings.map(item => {
            const rect = baseMeasurement(item).rect;
            return rect.left + rect.width / 2;
          }),
          siblings.map(item => baseMeasurement(item).rect.right)
        ];
    const deviations = anchors
      .map(values => clusteredPeerDeviation(values, index))
      .filter(value => value > 0);
    if (deviations.length) {
      measurements.layoutAxis = row ? "vertical" : "horizontal";
      measurements.layoutDeviation = round(Math.min(...deviations));
    }

    const textPeers = siblings.map(item => baseMeasurement(item));
    const semanticKeys = textPeers.map((item, peerIndex) => (
      `${siblings[peerIndex].tagName.toLowerCase()}:${item.role}`
    ));
    const equivalentPeers = semanticKeys.every(
      value => value === semanticKeys[0]
    );
    if (equivalentPeers && textPeers.every(item => item.text)) {
      const peerSizes = textPeers
        .filter((_item, peerIndex) => peerIndex !== index)
        .map(item => item.text.fontSize);
      if (Math.max(...peerSizes) - Math.min(...peerSizes) <= 1) {
        const baselines = textPeers.map(item => item.text.bounds.bottom);
        measurements.fontBaselineDeviation = round(
          clusteredPeerDeviation(baselines, index)
        );
      }
      const peerFonts = textPeers
        .filter((_item, peerIndex) => peerIndex !== index)
        .map(item => item.style.fontFamily);
      const expectedFont = peerFonts[0];
      if (
        peerFonts.every(value => value === expectedFont) &&
        textPeers[index].style.fontFamily !== expectedFont
      ) {
        measurements.fontMismatch = true;
        measurements.expectedFontFamily = expectedFont;
      }
    }
  };

  const candidateSet = new Set(structuralCandidates);
  const textElementPattern = /^(?:h[1-6]|p|li|label|legend|blockquote|figcaption|td|th|dt|dd|span|small|strong|em)$/;
  for (const element of allElements) {
    if (!isVisible(element)) continue;
    const style = getComputedStyle(element);
    const role = element.getAttribute("role") || implicitRole(element);
    const tag = element.tagName.toLowerCase();
    const hasText = Boolean((element.textContent || "").trim());
    const parentDisplay = element.parentElement
      ? getComputedStyle(element.parentElement).display
      : "";
    if (
      isControl(element, role) ||
      isVisualContainer(element, style) ||
      (hasText && (textElementPattern.test(tag) || element.children.length === 0)) ||
      parentDisplay === "flex"
    ) {
      candidateSet.add(element);
    }
  }

  const documentOrder = new Map(
    allElements.map((element, index) => [element, index])
  );
  return Array.from(candidateSet)
    .filter(isVisible)
    .sort((first, second) => (
      (documentOrder.get(first) ?? 0) - (documentOrder.get(second) ?? 0)
    ))
    .slice(0, 1500)
    .map((element, candidateOrder) => {
    const {style, rect, role, measurements} = baseMeasurement(element);
    enrichPeerMeasurements(element, measurements);

    const tag = element.tagName.toLowerCase();
    const kind = isControl(element, role)
      ? "action"
      : textElementPattern.test(tag)
        ? "text"
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
      order: documentOrder.get(element) ?? candidateOrder,
      bounds: {
        x: round(rect.x),
        y: round(rect.y),
        width: round(rect.width),
        height: round(rect.height)
      },
      styles: {
        display: style.display,
        position: style.position,
        color: style.color,
        backgroundColor: style.backgroundColor,
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
        textAlign: style.textAlign,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        paddingTop: style.paddingTop,
        paddingRight: style.paddingRight,
        paddingBottom: style.paddingBottom,
        paddingLeft: style.paddingLeft,
        alignItems: style.alignItems,
        flexDirection: style.flexDirection,
        gap: style.gap,
        gridTemplateColumns: style.gridTemplateColumns
      },
      states,
      measurements
    };
  });
}
"""
