"""Observe rendered frontend structure through a headless browser.

Playwright is an implementation detail behind :func:`observe_frontend`. The
returned value is plain, serializable evidence that can be merged into a
``FrontendMap`` or constructed directly by tests and other local adapters.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from uidetox.capabilities import (
    capture_install_guidance,
    chromium_install_guidance,
)
from uidetox.color_utils import (
    composite_rendered_color,
    contrast_ratio_rgba,
    normalize_rendered_color,
)
from uidetox.design_semantics import detect_design_findings
from uidetox.findings import Finding
from uidetox.runtime_layout import detect_runtime_findings
from uidetox.runtime_scenarios import (
    DEFAULT_VIEWPORTS,
    RUNTIME_OBSERVATION_LIMITS,
    RuntimeCaptureRecord,
    RuntimeCoverage,
    RuntimeDiagnostic,
    RuntimeDomBudget,
    RuntimeReadiness,
    RuntimeReadinessPolicy,
    RuntimeScenario,
    RuntimeScenarioAction,
    RuntimeViewport,
    RuntimeViewportDiscovery,
    bounded_tuple,
    discover_runtime_viewports,
    normalize_runtime_urls,
    runtime_capture_id,
    sanitize_runtime_text,
    sanitize_runtime_url,
    validate_runtime_observation_plan,
)
from uidetox.utils import now_iso

_FOCUS_COLOR_PATTERN = re.compile(
    r"(?:rgba?|hsla?|oklab|oklch|color)\([^)]*\)|#[0-9a-f]{3,8}|transparent",
    re.IGNORECASE,
)
_FOCUS_CONTRAST_THRESHOLD = 3.0
_WHITE = (1.0, 1.0, 1.0, 1.0)


def _focus_effective_color(
    raw: object,
    backdrop: tuple[float, float, float, float] = _WHITE,
) -> tuple[float, float, float, float] | None:
    color = normalize_rendered_color(str(raw or ""))
    return composite_rendered_color(color, backdrop) if color is not None else None


def _focus_contrast(
    first: tuple[float, float, float, float] | None,
    second: tuple[float, float, float, float] | None,
) -> float:
    if first is None or second is None:
        return 0.0
    return contrast_ratio_rgba(first, second)


def _normalize_focus_indicator(value: object) -> dict[str, Any]:
    indicator = dict(value) if isinstance(value, dict) else {}
    baseline = (
        dict(indicator.get("baseline"))
        if isinstance(indicator.get("baseline"), dict)
        else {}
    )
    focused = (
        dict(indicator.get("focused"))
        if isinstance(indicator.get("focused"), dict)
        else {}
    )
    if not baseline or not focused:
        return indicator

    baseline_background = _focus_effective_color(baseline.get("backgroundColor"))
    focused_background = _focus_effective_color(focused.get("backgroundColor"))
    perceptible: list[str] = []
    ratios: dict[str, float] = {}

    background_ratio = _focus_contrast(baseline_background, focused_background)
    if (
        baseline.get("backgroundColor") != focused.get("backgroundColor")
        and background_ratio >= _FOCUS_CONTRAST_THRESHOLD
    ):
        perceptible.append("backgroundColor")
        ratios["backgroundColor"] = round(background_ratio, 4)

    for side in ("Top", "Right", "Bottom", "Left"):
        property_name = f"border{side}Color"
        width_name = f"border{side}Width"
        width = float(str(focused.get(width_name, "0")).removesuffix("px") or 0)
        baseline_width = float(
            str(baseline.get(width_name, "0")).removesuffix("px") or 0
        )
        if width <= 0 or (
            baseline.get(property_name) == focused.get(property_name)
            and width == baseline_width
        ):
            continue
        baseline_border = _focus_effective_color(
            baseline.get(property_name),
            baseline_background or _WHITE,
        )
        focused_border = _focus_effective_color(
            focused.get(property_name),
            focused_background or _WHITE,
        )
        ratio = _focus_contrast(baseline_border, focused_border)
        if ratio >= _FOCUS_CONTRAST_THRESHOLD:
            perceptible.append(property_name)
            ratios[property_name] = round(ratio, 4)

    outline_width = float(str(focused.get("outlineWidth", "0")).removesuffix("px") or 0)
    outline_changed = any(
        baseline.get(property_name) != focused.get(property_name)
        for property_name in ("outlineStyle", "outlineWidth", "outlineColor")
    )
    if (
        outline_changed
        and outline_width > 0
        and focused.get("outlineStyle") not in {"none", "hidden"}
    ):
        baseline_outline = _focus_effective_color(
            baseline.get("outlineColor"),
            baseline_background or _WHITE,
        )
        if (
            baseline.get("outlineStyle") in {"none", "hidden"}
            or float(str(baseline.get("outlineWidth", "0")).removesuffix("px") or 0)
            <= 0
        ):
            baseline_outline = baseline_background
        focused_outline = _focus_effective_color(
            focused.get("outlineColor"),
            focused_background or _WHITE,
        )
        ratio = _focus_contrast(baseline_outline, focused_outline)
        if ratio >= _FOCUS_CONTRAST_THRESHOLD:
            perceptible.append("outline")
            ratios["outline"] = round(ratio, 4)

    if baseline.get("boxShadow") != focused.get("boxShadow"):
        baseline_shadow_colors = [
            _focus_effective_color(
                color,
                baseline_background or _WHITE,
            )
            for color in _FOCUS_COLOR_PATTERN.findall(
                str(baseline.get("boxShadow", ""))
            )
        ] or [baseline_background]
        focused_shadow_colors = [
            _focus_effective_color(
                color,
                focused_background or _WHITE,
            )
            for color in _FOCUS_COLOR_PATTERN.findall(str(focused.get("boxShadow", "")))
        ]
        ratio = max(
            (
                _focus_contrast(focused_color, baseline_color)
                for focused_color in focused_shadow_colors
                for baseline_color in baseline_shadow_colors
            ),
            default=0.0,
        )
        if ratio >= _FOCUS_CONTRAST_THRESHOLD:
            perceptible.append("boxShadow")
            ratios["boxShadow"] = round(ratio, 4)

    raw_areas = (
        indicator.get("areaByProperty")
        if isinstance(indicator.get("areaByProperty"), dict)
        else {}
    )
    area_keys = {
        "backgroundColor": "backgroundColor",
        "borderTopColor": "border",
        "borderRightColor": "border",
        "borderBottomColor": "border",
        "borderLeftColor": "border",
        "outline": "outline",
        "boxShadow": "boxShadow",
    }
    areas = [
        float(raw_areas.get(area_keys[property_name], 0) or 0)
        for property_name in perceptible
    ]
    indicator.update(
        {
            "visible": bool(perceptible),
            "changed": bool(indicator.get("changedProperties")),
            "distinguishable": bool(perceptible),
            "perceptibleProperties": perceptible,
            "contrastRatios": ratios,
            "area": round(max(areas, default=0.0), 2),
        }
    )
    return indicator


def _normalized_runtime_measurements(value: object) -> dict[str, Any]:
    measurements = dict(value) if isinstance(value, dict) else {}
    if isinstance(measurements.get("focusIndicator"), dict):
        measurements["focusIndicator"] = _normalize_focus_indicator(
            measurements["focusIndicator"]
        )
    raw_paint = measurements.get("paint")
    if not isinstance(raw_paint, dict):
        return measurements
    paint = dict(raw_paint)
    unresolved = [
        dict(item) for item in paint.get("unresolved", []) if isinstance(item, dict)
    ]

    def normalize_entry(
        raw_entry: object,
        *,
        selector: str,
        property_name: str,
    ) -> dict[str, Any]:
        entry = dict(raw_entry) if isinstance(raw_entry, dict) else {}
        raw = str(entry.get("raw", ""))
        existing = entry.get("rgba")
        if (
            isinstance(existing, (list, tuple))
            and len(existing) == 4
            and all(isinstance(channel, (int, float)) for channel in existing)
        ):
            entry["rgba"] = [float(channel) for channel in existing]
            return entry
        normalized = normalize_rendered_color(raw)
        entry["rgba"] = list(normalized) if normalized is not None else None
        if normalized is None:
            cause = {
                "selector": selector,
                "property": property_name,
                "value": raw,
            }
            if cause not in unresolved:
                unresolved.append(cause)
        return entry

    paint["foreground"] = normalize_entry(
        paint.get("foreground"),
        selector=str(paint.get("selector", "")),
        property_name="color",
    )
    layers: list[dict[str, Any]] = []
    for raw_layer in paint.get("background_layers", []):
        if not isinstance(raw_layer, dict):
            continue
        selector = str(raw_layer.get("selector", ""))
        layers.append(
            normalize_entry(
                raw_layer,
                selector=selector,
                property_name="background-color",
            )
        )
    paint["background_layers"] = layers
    paint["unresolved"] = unresolved
    measurements["paint"] = paint
    return measurements


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
    source_hint: str = ""
    source_selectors: tuple[str, ...] = ()
    states: dict[str, Any] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()

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
            source_hint=str(value.get("source_hint", "")),
            source_selectors=tuple(
                str(item)
                for item in value.get("source_selectors", [])
                if isinstance(item, str)
            ),
            states=dict(states),
            measurements=_normalized_runtime_measurements(measurements),
            findings=tuple(
                Finding.from_dict(dict(item))
                for item in value.get("findings", [])
                if isinstance(item, dict)
            ),
        )


def _attach_runtime_findings(
    elements: tuple[RuntimeElement, ...],
) -> tuple[RuntimeElement, ...]:
    attached = tuple(
        replace(element, findings=detect_runtime_findings(element))
        for element in elements
    )
    clipping_containers = {
        element.selector
        for element in attached
        if any(
            finding.code == "runtime-component-clipped" for finding in element.findings
        )
    }
    if not clipping_containers:
        return attached
    return tuple(
        replace(
            element,
            findings=tuple(
                finding
                for finding in element.findings
                if not (
                    finding.code == "runtime-text-clipped"
                    and finding.metrics.get("clipping_ancestor") in clipping_containers
                )
            ),
        )
        for element in attached
    )


@dataclass(frozen=True)
class RuntimePage:
    url: str
    title: str
    viewport: RuntimeViewport
    elements: tuple[RuntimeElement, ...]
    screenshot: str | None = None
    capture_id: str = ""
    scenario: str = "default"
    state: str = "initial"

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
            capture_id=str(value.get("capture_id", "")),
            scenario=str(value.get("scenario", "default")),
            state=str(value.get("state", "initial")),
        )


def _attach_design_findings(page: RuntimePage) -> RuntimePage:
    semantic_findings = detect_design_findings(page)
    if not any(semantic_findings):
        return page
    return replace(
        page,
        elements=tuple(
            replace(element, findings=(*element.findings, *findings))
            for element, findings in zip(
                page.elements,
                semantic_findings,
                strict=True,
            )
        ),
    )


def _legacy_capture(page: RuntimePage, generated_at: str) -> RuntimeCaptureRecord:
    return RuntimeCaptureRecord(
        capture_id=page.capture_id,
        scenario=page.scenario,
        state=page.state,
        url=page.url,
        viewport=page.viewport,
        status="completed",
        readiness=RuntimeReadiness("current", "legacy", 0),
        coverage=RuntimeCoverage(
            total=len(page.elements),
            candidates=len(page.elements),
            eligible=len(page.elements),
            emitted=len(page.elements),
            budget=len(page.elements),
        ),
        started_at=generated_at,
        completed_at=generated_at,
    )


@dataclass(frozen=True)
class RuntimeObservation:
    generated_at: str
    requested_urls: tuple[str, ...]
    pages: tuple[RuntimePage, ...]
    errors: tuple[str, ...] = ()
    captures: tuple[RuntimeCaptureRecord, ...] = ()
    viewport_discovery: RuntimeViewportDiscovery | None = None
    status: str = ""

    def __post_init__(self) -> None:
        sanitized_errors = tuple(sanitize_runtime_text(error) for error in self.errors)
        if sanitized_errors != self.errors:
            object.__setattr__(self, "errors", sanitized_errors)
        captures = self.captures
        normalize_page_ids = not captures
        pages = tuple(
            page
            if page.capture_id and not normalize_page_ids
            else replace(
                page,
                capture_id=runtime_capture_id(
                    page.scenario,
                    page.state,
                    page.url,
                    page.viewport,
                ),
            )
            for page in self.pages
        )
        if pages != self.pages:
            object.__setattr__(self, "pages", pages)
        if not captures and pages:
            captures = tuple(_legacy_capture(page, self.generated_at) for page in pages)
            object.__setattr__(self, "captures", captures)
        captures_by_id: dict[str, RuntimeCaptureRecord] = {}
        for capture in captures:
            if capture.capture_id in captures_by_id:
                raise ValueError(
                    "Runtime observation has duplicate capture identity: "
                    f"{capture.capture_id!r}."
                )
            if not normalize_page_ids and capture.url not in self.requested_urls:
                raise ValueError(
                    f"Runtime capture URL was not requested: {capture.url!r}."
                )
            captures_by_id[capture.capture_id] = capture
        page_ids: set[str] = set()
        for page in pages:
            if page.capture_id in page_ids:
                raise ValueError(
                    "Runtime observation has duplicate page identity: "
                    f"{page.capture_id!r}."
                )
            page_ids.add(page.capture_id)
            capture = captures_by_id.get(page.capture_id)
            if capture is None:
                raise ValueError(
                    "Runtime page capture identity has no matching record: "
                    f"{page.capture_id!r}."
                )
            # Capture URL is requested identity; page URL is resolved browser state.
            if (page.scenario, page.state, page.viewport) != (
                capture.scenario,
                capture.state,
                capture.viewport,
            ):
                raise ValueError(
                    "Runtime page capture metadata does not match record: "
                    f"{page.capture_id!r}."
                )
        completed = sum(capture.status == "completed" for capture in captures)
        failed = sum(capture.status == "failed" for capture in captures)
        degraded = any(
            capture.readiness.status == "degraded" or capture.coverage.truncated
            for capture in captures
            if capture.status == "completed"
        )
        if failed and completed:
            status = "partial"
        elif failed or (self.errors and not completed):
            status = "failed"
        elif completed and degraded:
            status = "degraded"
        elif completed and self.errors:
            status = "partial"
        elif completed:
            status = "current"
        else:
            status = "absent"
        object.__setattr__(self, "status", status)

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
            captures=tuple(
                RuntimeCaptureRecord.from_dict(dict(capture))
                for capture in value.get("captures", [])
                if isinstance(capture, dict)
            ),
            viewport_discovery=(
                RuntimeViewportDiscovery.from_dict(dict(value["viewport_discovery"]))
                if isinstance(value.get("viewport_discovery"), dict)
                else None
            ),
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
    scenarios: Iterable[RuntimeScenario] | None = None,
    readiness: RuntimeReadinessPolicy | None = None,
    dom_budget: RuntimeDomBudget = RuntimeDomBudget(),
    source_root: str | Path | None = None,
    viewport_discovery: RuntimeViewportDiscovery | None = None,
) -> RuntimeObservation:
    """Observe explicit browser scenarios through one bounded capture engine.

    The caller must start the dev server. Individual navigation failures are
    recorded so other URLs/viewports can still complete; missing Playwright or
    browser binaries fail immediately with an actionable error.
    """

    normalized_urls = normalize_runtime_urls(urls)
    normalized_viewports = bounded_tuple(
        viewports,
        limit=RUNTIME_OBSERVATION_LIMITS.viewports,
        label="Runtime viewport count",
    )
    if not normalized_viewports:
        raise ValueError("At least one runtime viewport is required.")
    if viewport_discovery is not None and source_root is not None:
        raise ValueError(
            "Provide runtime viewport discovery or a source root, not both."
        )
    effective_discovery = viewport_discovery or (
        discover_runtime_viewports(
            source_root,
            base_viewports=normalized_viewports,
        )
        if source_root is not None
        else None
    )
    if effective_discovery is not None:
        normalized_viewports = effective_discovery.viewports
    active_scenarios = (
        bounded_tuple(
            scenarios,
            limit=RUNTIME_OBSERVATION_LIMITS.scenarios,
            label="Runtime scenario count",
        )
        if scenarios is not None
        else tuple(
            RuntimeScenario(
                name="default",
                url=url,
                expected_state="initial",
                readiness=readiness or RuntimeReadinessPolicy(settle_ms=settle_ms),
            )
            for url in normalized_urls
        )
    )
    if not active_scenarios:
        raise ValueError("At least one runtime scenario is required.")
    unrequested_urls = {scenario.url for scenario in active_scenarios} - set(
        normalized_urls
    )
    if unrequested_urls:
        raise ValueError("Runtime scenario URLs must be included in requested URLs.")
    validate_runtime_observation_plan(
        active_scenarios,
        normalized_viewports,
        timeout_ms=timeout_ms,
        settle_ms=settle_ms,
    )

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
    captures: list[RuntimeCaptureRecord] = []
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for scenario in active_scenarios:
                    for viewport in _scenario_viewports(
                        scenario,
                        normalized_viewports,
                    ):
                        scenario_pages, scenario_captures, scenario_errors = (
                            _observe_scenario(
                                browser,
                                scenario,
                                viewport,
                                timeout_ms=timeout_ms,
                                dom_budget=dom_budget,
                                screenshot_root=screenshot_root,
                                screenshot_namer=screenshot_namer,
                                full_page=full_page,
                                playwright_timeout_error=PlaywrightTimeoutError,
                            )
                        )
                        pages.extend(scenario_pages)
                        captures.extend(scenario_captures)
                        errors.extend(scenario_errors)
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
        captures=tuple(captures),
        viewport_discovery=effective_discovery,
    )


def _scenario_viewports(
    scenario: RuntimeScenario,
    available: tuple[RuntimeViewport, ...],
) -> tuple[RuntimeViewport, ...]:
    if not scenario.viewports:
        return available
    requested = set(scenario.viewports)
    return tuple(viewport for viewport in available if viewport.name in requested)


def _scenario_states(scenario: RuntimeScenario) -> tuple[str, ...]:
    states = tuple(
        action.state for action in scenario.actions if action.kind == "capture"
    )
    return states or (scenario.expected_state,)


def _finalize_capture_diagnostics(
    captures: Iterable[RuntimeCaptureRecord],
    diagnostics: Iterable[RuntimeDiagnostic],
) -> tuple[RuntimeCaptureRecord, ...]:
    by_state: dict[str, list[RuntimeDiagnostic]] = {}
    for diagnostic in diagnostics:
        by_state.setdefault(diagnostic.state, []).append(diagnostic)
    finalized = []
    for capture in captures:
        merged = []
        seen: set[tuple[str, ...]] = set()
        capture_url = sanitize_runtime_url(capture.url)
        for diagnostic in (
            *capture.diagnostics,
            *by_state.get(capture.state, ()),
        ):
            if (
                diagnostic.scenario != capture.scenario
                or diagnostic.state != capture.state
                or diagnostic.url != capture_url
                or diagnostic.viewport != capture.viewport.name
            ):
                continue
            key = (
                diagnostic.kind,
                diagnostic.code,
                diagnostic.message,
                diagnostic.scenario,
                diagnostic.state,
                diagnostic.url,
                diagnostic.viewport,
                diagnostic.source,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(diagnostic)
        finalized.append(replace(capture, diagnostics=tuple(merged)))
    return tuple(finalized)


def _observe_scenario(
    browser: Any,
    scenario: RuntimeScenario,
    viewport: RuntimeViewport,
    *,
    timeout_ms: int,
    dom_budget: RuntimeDomBudget,
    screenshot_root: Path | None,
    screenshot_namer: Callable[[str, RuntimeViewport], str] | None,
    full_page: bool,
    playwright_timeout_error: type[BaseException],
) -> tuple[
    tuple[RuntimePage, ...],
    tuple[RuntimeCaptureRecord, ...],
    tuple[str, ...],
]:
    context = browser.new_context(
        viewport={"width": viewport.width, "height": viewport.height},
        reduced_motion="reduce",
    )
    page = context.new_page()
    states = _scenario_states(scenario)
    state_context = {"state": states[0]}
    diagnostics: list[RuntimeDiagnostic] = []
    _install_diagnostic_listeners(
        page,
        diagnostics,
        scenario=scenario,
        viewport=viewport,
        state_context=state_context,
    )
    started_at = now_iso()
    readiness = RuntimeReadiness("failed", "navigation", 0)
    pages: list[RuntimePage] = []
    captures: list[RuntimeCaptureRecord] = []
    errors: list[str] = []
    try:
        try:
            page.goto(
                scenario.url,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            readiness = _wait_for_readiness(
                page,
                scenario.readiness,
                timeout_ms=timeout_ms,
                playwright_timeout_error=playwright_timeout_error,
            )
            if readiness.status == "failed":
                raise RuntimeError(readiness.detail or "Runtime readiness failed.")
            captured_states: set[str] = set()
            for action in scenario.actions:
                if action.kind == "capture":
                    state_context["state"] = action.state
                    runtime_page, capture = _capture_scenario_state(
                        page,
                        scenario=scenario,
                        state=action.state,
                        viewport=viewport,
                        readiness=readiness,
                        diagnostics=diagnostics,
                        dom_budget=dom_budget,
                        started_at=started_at,
                        screenshot_root=screenshot_root,
                        screenshot_namer=screenshot_namer,
                        full_page=full_page,
                    )
                    pages.append(runtime_page)
                    captures.append(capture)
                    captured_states.add(action.state)
                else:
                    _perform_action(page, action)
            if not captured_states:
                state_context["state"] = scenario.expected_state
                runtime_page, capture = _capture_scenario_state(
                    page,
                    scenario=scenario,
                    state=scenario.expected_state,
                    viewport=viewport,
                    readiness=readiness,
                    diagnostics=diagnostics,
                    dom_budget=dom_budget,
                    started_at=started_at,
                    screenshot_root=screenshot_root,
                    screenshot_namer=screenshot_namer,
                    full_page=full_page,
                )
                pages.append(runtime_page)
                captures.append(capture)
        except Exception as exc:
            state = state_context["state"]
            message = sanitize_runtime_text(
                f"{scenario.url} [{viewport.name}/{scenario.name}/{state}]: {exc}"
            )
            errors.append(message)
            diagnostics.append(
                _diagnostic(
                    kind="action",
                    code="browser-action-failed",
                    message=str(exc),
                    scenario=scenario,
                    state=state,
                    viewport=viewport,
                    source="scenario",
                )
            )
            completed_ids = {capture.capture_id for capture in captures}
            for state in states:
                capture_id = runtime_capture_id(
                    scenario.name,
                    state,
                    scenario.url,
                    viewport,
                )
                if capture_id in completed_ids:
                    continue
                captures.append(
                    RuntimeCaptureRecord(
                        capture_id=capture_id,
                        scenario=scenario.name,
                        state=state,
                        url=scenario.url,
                        viewport=viewport,
                        status="failed",
                        readiness=readiness,
                        coverage=RuntimeCoverage.empty(dom_budget.candidates),
                        started_at=started_at,
                        completed_at=now_iso(),
                        diagnostics=tuple(diagnostics),
                    )
                )
    finally:
        context.close()
    return (
        tuple(pages),
        _finalize_capture_diagnostics(captures, diagnostics),
        tuple(errors),
    )


def _wait_for_readiness(
    page: Any,
    policy: RuntimeReadinessPolicy,
    *,
    timeout_ms: int,
    playwright_timeout_error: type[BaseException],
) -> RuntimeReadiness:
    started = perf_counter()
    strategy = "settle"
    detail = ""
    status = "current"
    try:
        if policy.selector:
            strategy = "selector"
            page.wait_for_selector(
                policy.selector,
                state="visible",
                timeout=timeout_ms,
            )
        elif policy.app_hook:
            strategy = "app-hook"
            page.wait_for_function(
                "(hook) => hook.split('.').reduce((value, key) => "
                "value?.[key], window) === true",
                policy.app_hook,
                timeout=timeout_ms,
            )
        elif policy.mutation_idle_ms:
            strategy = "mutation-idle"
            page.wait_for_function(
                """
                policy => new Promise(resolve => {
                  const finish = () => {
                    observer.disconnect();
                    clearTimeout(idleTimer);
                    resolve(true);
                  };
                  let idleTimer = setTimeout(finish, policy.idle);
                  const observer = new MutationObserver(() => {
                    clearTimeout(idleTimer);
                    idleTimer = setTimeout(finish, policy.idle);
                  });
                  observer.observe(document, {
                    subtree: true,
                    childList: true,
                    attributes: true,
                    characterData: true
                  });
                })
                """,
                {
                    "idle": policy.mutation_idle_ms,
                },
                timeout=timeout_ms,
            )
        elif policy.request_idle_ms:
            strategy = "request-idle"
            page.wait_for_load_state(
                "networkidle",
                timeout=min(policy.request_idle_ms, timeout_ms),
            )
    except playwright_timeout_error as exc:
        status = "failed" if strategy in {"selector", "app-hook"} else "degraded"
        detail = f"{strategy} timed out: {exc}"
    if policy.settle_ms:
        page.wait_for_timeout(policy.settle_ms)
        if status == "degraded":
            detail = f"{detail}; settle fallback {policy.settle_ms}ms"
    return RuntimeReadiness(
        status=status,
        strategy=strategy,
        duration_ms=round((perf_counter() - started) * 1_000),
        detail=detail,
    )


def _perform_action(page: Any, action: RuntimeScenarioAction) -> None:
    if action.kind == "click":
        page.locator(action.selector).click(timeout=action.timeout_ms)
    elif action.kind == "fill":
        value = os.environ.get(action.env)
        if value is None:
            raise ValueError(
                f"Runtime scenario environment variable is missing: {action.env}"
            )
        try:
            page.locator(action.selector).fill(value, timeout=action.timeout_ms)
        except Exception as exc:
            raise RuntimeError(
                f"Runtime fill failed for selector {action.selector}: "
                f"{type(exc).__name__}"
            ) from exc
    elif action.kind == "hover":
        page.locator(action.selector).hover(timeout=action.timeout_ms)
    elif action.kind == "focus":
        page.locator(action.selector).focus(timeout=action.timeout_ms)
    elif action.kind == "key":
        page.locator(action.selector).press(action.key, timeout=action.timeout_ms)
    elif action.kind == "wait-for-selector":
        page.wait_for_selector(
            action.selector,
            state="visible",
            timeout=action.timeout_ms,
        )
    elif action.kind == "wait-for-state":
        if action.selector:
            page.wait_for_selector(
                action.selector,
                state=action.state,
                timeout=action.timeout_ms,
            )
        else:
            page.wait_for_load_state(action.state, timeout=action.timeout_ms)


def _capture_scenario_state(
    page: Any,
    *,
    scenario: RuntimeScenario,
    state: str,
    viewport: RuntimeViewport,
    readiness: RuntimeReadiness,
    diagnostics: list[RuntimeDiagnostic],
    dom_budget: RuntimeDomBudget,
    started_at: str,
    screenshot_root: Path | None,
    screenshot_namer: Callable[[str, RuntimeViewport], str] | None,
    full_page: bool,
) -> tuple[RuntimePage, RuntimeCaptureRecord]:
    payload = page.evaluate(_runtime_evaluate_script(dom_budget))
    elements, coverage = _elements_and_coverage_from_payload(payload, dom_budget)
    elements = _attach_runtime_findings(elements)
    capture_id = runtime_capture_id(scenario.name, state, scenario.url, viewport)
    capture_diagnostics = list(diagnostics)
    if coverage.truncated:
        capture_diagnostics.append(
            _diagnostic(
                kind="coverage",
                code="runtime-dom-budget-exceeded",
                message=(
                    f"Emitted {coverage.emitted}/{coverage.eligible} eligible "
                    f"elements from {coverage.total} total."
                ),
                scenario=scenario,
                state=state,
                viewport=viewport,
                source="dom-budget",
            )
        )
    screenshot = _capture_runtime_screenshot(
        page,
        viewport,
        screenshot_root=screenshot_root,
        screenshot_namer=_stateful_screenshot_namer(
            screenshot_namer,
            scenario,
            state,
        ),
        full_page=full_page,
    )
    runtime_page = _attach_design_findings(
        RuntimePage(
            url=page.url,
            title=page.title(),
            viewport=viewport,
            elements=elements,
            screenshot=screenshot,
            capture_id=capture_id,
            scenario=scenario.name,
            state=state,
        )
    )
    return runtime_page, RuntimeCaptureRecord(
        capture_id=capture_id,
        scenario=scenario.name,
        state=state,
        url=scenario.url,
        viewport=viewport,
        status="completed",
        readiness=readiness,
        coverage=coverage,
        started_at=started_at,
        completed_at=now_iso(),
        diagnostics=tuple(capture_diagnostics),
    )


def _stateful_screenshot_namer(
    namer: Callable[[str, RuntimeViewport], str] | None,
    scenario: RuntimeScenario,
    state: str,
) -> Callable[[str, RuntimeViewport], str] | None:
    if scenario.name == "default" and state == "initial":
        return namer

    def name(url: str, viewport: RuntimeViewport) -> str:
        base = Path((namer or _screenshot_name)(url, viewport))
        suffix = f"-{scenario.name}-{state}"
        return f"{base.stem}{suffix}{base.suffix}"

    return name


def _capture_runtime_screenshot(
    page: Any,
    viewport: RuntimeViewport,
    *,
    screenshot_root: Path | None,
    screenshot_namer: Callable[[str, RuntimeViewport], str] | None,
    full_page: bool,
) -> str | None:
    if screenshot_root is None:
        return None
    screenshot_name = (
        screenshot_namer(page.url, viewport)
        if screenshot_namer is not None
        else _screenshot_name(page.url, viewport)
    )
    screenshot_path = _safe_screenshot_path(screenshot_root, screenshot_name)
    _capture_screenshot_atomically(page, screenshot_path, full_page=full_page)
    return str(screenshot_path)


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


def _diagnostic(
    *,
    kind: str,
    code: str,
    message: str,
    scenario: RuntimeScenario,
    state: str,
    viewport: RuntimeViewport,
    source: str,
    severity: str = "error",
) -> RuntimeDiagnostic:
    return RuntimeDiagnostic(
        kind=kind,
        code=code,
        message=message,
        severity=severity,
        scenario=scenario.name,
        state=state,
        url=scenario.url,
        viewport=viewport.name,
        source=source,
    )


def _install_diagnostic_listeners(
    page: Any,
    diagnostics: list[RuntimeDiagnostic],
    *,
    scenario: RuntimeScenario,
    viewport: RuntimeViewport,
    state_context: dict[str, str],
) -> None:
    if not hasattr(page, "on"):
        return

    def add(kind: str, code: str, message: str, source: str) -> None:
        diagnostics.append(
            _diagnostic(
                kind=kind,
                code=code,
                message=message,
                scenario=scenario,
                state=state_context["state"],
                viewport=viewport,
                source=source,
            )
        )

    def console(message: Any) -> None:
        if str(getattr(message, "type", "")).lower() == "error":
            add(
                "console",
                "browser-console-error",
                str(getattr(message, "text", message)),
                "console",
            )

    def page_error(error: Any) -> None:
        add("page", "browser-page-error", str(error), "pageerror")

    def request_failed(request: Any) -> None:
        failure = getattr(request, "failure", "")
        add(
            "network",
            "browser-request-failed",
            f"{getattr(request, 'url', '')}: {failure}",
            "requestfailed",
        )

    def response(received: Any) -> None:
        status = int(getattr(received, "status", 0))
        if status >= 400:
            add(
                "network",
                "browser-http-error",
                f"HTTP {status}: {getattr(received, 'url', '')}",
                "response",
            )

    page.on("console", console)
    page.on("pageerror", page_error)
    page.on("requestfailed", request_failed)
    page.on("response", response)


def _elements_and_coverage_from_payload(
    payload: Any,
    budget: RuntimeDomBudget,
) -> tuple[tuple[RuntimeElement, ...], RuntimeCoverage]:
    if isinstance(payload, list):
        elements = tuple(
            RuntimeElement.from_dict(item) for item in payload if isinstance(item, dict)
        )
        count = len(elements)
        return elements, RuntimeCoverage(
            total=count,
            candidates=count,
            eligible=count,
            emitted=count,
            budget=budget.candidates,
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Runtime DOM observer returned an invalid payload.")
    elements = tuple(
        RuntimeElement.from_dict(item)
        for item in payload["elements"]
        if isinstance(item, dict)
    )
    raw_coverage = payload.get("coverage", {})
    if not isinstance(raw_coverage, dict):
        raise ValueError("Runtime DOM observer returned invalid coverage.")
    coverage = RuntimeCoverage.from_dict(raw_coverage)
    if coverage.emitted != len(elements):
        raise ValueError("Runtime DOM coverage does not match emitted elements.")
    return elements, coverage


def _runtime_evaluate_script(budget: RuntimeDomBudget) -> str:
    return _RUNTIME_EVALUATE_SCRIPT.replace(
        "__UIDETOX_SCAN__", str(budget.scan)
    ).replace("__UIDETOX_CANDIDATES__", str(budget.candidates))


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
async () => {
  if (document.fonts?.ready) {
    await Promise.race([
      document.fonts.ready,
      new Promise(resolve => setTimeout(resolve, 1000))
    ]);
  }
  await new Promise(resolve => requestAnimationFrame(
    () => requestAnimationFrame(resolve)
  ));
  const structuralSelector = [
    "header", "nav", "main", "aside", "section", "article", "footer",
    "form", "table", "dialog", "button", "a[href]", "input", "select",
    "textarea", "[role]", "[tabindex]"
  ].join(",");
  const elementCollection = document.body?.querySelectorAll("*") || [];
  const totalElements = elementCollection.length;
  const allElements = [];
  for (
    let index = 0;
    index < Math.min(totalElements, __UIDETOX_SCAN__);
    index += 1
  ) {
    allElements.push(elementCollection[index]);
  }
  const structuralCandidates = allElements.filter(
    element => element.matches(structuralSelector)
  );
  const round = value => Math.round(value * 100) / 100;
  const pixels = value => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const computedAlpha = value => {
    const normalized = String(value || "").trim().toLowerCase();
    if (!normalized || normalized === "transparent") return 0;
    const slash = normalized.match(/\/\s*([+-]?(?:\d+\.?\d*|\.\d+)%?)\s*\)$/);
    if (slash) {
      const parsed = Number.parseFloat(slash[1]);
      return Number.isFinite(parsed)
        ? Math.max(0, Math.min(1, slash[1].endsWith("%") ? parsed / 100 : parsed))
        : null;
    }
    const body = normalized.match(/^rgba?\((.*)\)$/)?.[1] || "";
    const commaParts = body.split(",").map(part => part.trim());
    if (commaParts.length === 4) {
      const parsed = Number.parseFloat(commaParts[3]);
      return Number.isFinite(parsed)
        ? Math.max(
            0,
            Math.min(
              1,
              commaParts[3].endsWith("%") ? parsed / 100 : parsed
            )
          )
        : null;
    }
    return 1;
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

  const geometryCache = new WeakMap();
  const geometryFor = element => {
    if (geometryCache.has(element)) return geometryCache.get(element);
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const result = {
      style,
      rect,
      role: element.getAttribute("role") || implicitRole(element),
      visible: !(
        style.display === "none"
        || style.visibility === "hidden"
        || Number(style.opacity) === 0
        || rect.width <= 0
        || rect.height <= 0
      ),
      scrollAxes: {
        x: ["auto", "scroll"].includes(style.overflowX),
        y: ["auto", "scroll"].includes(style.overflowY)
      }
    };
    geometryCache.set(element, result);
    return result;
  };

  const sourceSelectorsFor = (element) => {
    const selectors = [];
    const testId = element.getAttribute("data-testid");
    if (testId) selectors.push(`[data-testid="${testId.replaceAll('"', '\\"')}"]`);
    const dataTest = element.getAttribute("data-test");
    if (dataTest) selectors.push(`[data-test="${dataTest.replaceAll('"', '\\"')}"]`);
    if (element.id) selectors.push(`#${CSS.escape(element.id)}`);
    for (const className of element.classList) {
      if (/^[-_A-Za-z][-\w]*$/.test(className)) selectors.push(`.${className}`);
    }
    selectors.push(element.tagName.toLowerCase());
    return Array.from(new Set(selectors));
  };

  const selectorCache = new WeakMap();
  const siblingPositionCache = new WeakMap();
  const siblingPositionFor = element => {
    const parent = element.parentElement;
    if (!parent) return {count: 0, index: 0};
    let positions = siblingPositionCache.get(parent);
    if (!positions) {
      positions = new WeakMap();
      const childrenByTag = new Map();
      for (const child of parent.children) {
        const tag = child.tagName;
        const siblings = childrenByTag.get(tag) || [];
        siblings.push(child);
        childrenByTag.set(tag, siblings);
      }
      for (const siblings of childrenByTag.values()) {
        siblings.forEach((sibling, index) => {
          positions.set(sibling, {count: siblings.length, index: index + 1});
        });
      }
      siblingPositionCache.set(parent, positions);
    }
    return positions.get(element) || {count: 0, index: 0};
  };

  const selectorFor = (element, sourceSelectors = null) => {
    if (selectorCache.has(element)) return selectorCache.get(element);
    const resolvedSourceSelectors = sourceSelectors || sourceSelectorsFor(element);
    const stable = resolvedSourceSelectors.find(
      selector => selector.startsWith("#") || selector.startsWith("[data-")
    );
    if (stable) {
      selectorCache.set(element, stable);
      return stable;
    }
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 4) {
      const tag = current.tagName.toLowerCase();
      const siblingPosition = siblingPositionFor(current);
      const suffix = siblingPosition.count > 1
        ? `:nth-of-type(${siblingPosition.index})`
        : "";
      parts.unshift(`${tag}${suffix}`);
      current = current.parentElement;
    }
    const selector = parts.join(" > ");
    selectorCache.set(element, selector);
    return selector;
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

  const isVisible = element => geometryFor(element).visible;

  const canvasContext = document.createElement("canvas").getContext("2d");
  const fontMetrics = (style, text) => {
    const font = style.font || `${style.fontSize} ${style.fontFamily}`;
    let ready = null;
    if (document.fonts) {
      try {
        ready = document.fonts.check(font, text.slice(0, 32));
      } catch (_error) {
        ready = null;
      }
    }
    if (!canvasContext) return {font, ready, ascent: 0, descent: 0};
    canvasContext.font = font;
    const metrics = canvasContext.measureText(text);
    return {
      font,
      ready,
      ascent: Number(metrics.actualBoundingBoxAscent) || 0,
      descent: Number(metrics.actualBoundingBoxDescent) || 0
    };
  };

  const logicalSides = (style, physical) => {
    const vertical = style.writingMode.startsWith("vertical")
      || style.writingMode.startsWith("sideways");
    if (!vertical) {
      return {
        inlineStart: style.direction === "rtl" ? physical.right : physical.left,
        inlineEnd: style.direction === "rtl" ? physical.left : physical.right,
        blockStart: physical.top,
        blockEnd: physical.bottom
      };
    }
    return {
      inlineStart: style.direction === "rtl" ? physical.bottom : physical.top,
      inlineEnd: style.direction === "rtl" ? physical.top : physical.bottom,
      blockStart: style.writingMode.endsWith("-rl")
        ? physical.right
        : physical.left,
      blockEnd: style.writingMode.endsWith("-rl")
        ? physical.left
        : physical.right
    };
  };

  const textGeometry = (element, style, rect) => {
    const text = (element.innerText || element.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) return null;
    const rects = [];
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let textNode = walker.nextNode();
    while (textNode) {
      if ((textNode.textContent || "").trim()) {
        const range = document.createRange();
        range.selectNodeContents(textNode);
        rects.push(...Array.from(range.getClientRects()).filter(
          item => item.width > 0 && item.height > 0
        ));
      }
      textNode = walker.nextNode();
    }
    if (!rects.length) return null;
    const left = Math.min(...rects.map(item => item.left));
    const right = Math.max(...rects.map(item => item.right));
    const top = Math.min(...rects.map(item => item.top));
    const bottom = Math.max(...rects.map(item => item.bottom));
    const lines = [];
    for (const item of [...rects].sort((a, b) => a.top - b.top)) {
      const currentLine = lines[lines.length - 1];
      if (currentLine && Math.abs(currentLine.top - item.top) <= 1) {
        currentLine.left = Math.min(currentLine.left, item.left);
        currentLine.right = Math.max(currentLine.right, item.right);
        currentLine.bottom = Math.max(currentLine.bottom, item.bottom);
      } else {
        lines.push({
          top: item.top,
          right: item.right,
          bottom: item.bottom,
          left: item.left
        });
      }
    }
    const lineGaps = lines.slice(1).map(
      (line, index) => line.top - lines[index].bottom
    );
    const fontSize = pixels(style.fontSize);
    const metrics = fontMetrics(style, text);
    const physicalInsets = {
      top: top - rect.top,
      right: rect.right - right,
      bottom: rect.bottom - bottom,
      left: left - rect.left
    };
    return {
      text,
      bounds: {left, right, top, bottom},
      lineCount: lines.length,
      minimumLineGap: lineGaps.length ? Math.min(...lineGaps) : null,
      fontSize,
      lineHeight: style.lineHeight === "normal"
        ? fontSize * 1.2
        : pixels(style.lineHeight),
      insets: physicalInsets,
      logicalInsets: logicalSides(style, physicalInsets),
      font: metrics.font,
      fontReady: metrics.ready,
      fontAscent: metrics.ascent,
      fontDescent: metrics.descent,
      baselineProxy: lines[0].bottom - metrics.descent
    };
  };

  const isControl = (element, role) => (
    interactiveRoles.has(role) ||
    element.matches(
      "button,a[href],input,select,textarea,[tabindex]:not([tabindex='-1'])"
    )
  );

  const paletteRoleFor = (element, role, visualContainer) => {
    const tag = element.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) return "heading";
    if (isControl(element, role)) return "action";
    if (visualContainer) return "surface";
    if ((element.textContent || "").trim()) return "body";
    return "";
  };

  // Ephemeral ancestry cache shared by every emitted text node in this DOM pass.
  const paintLayerCache = new WeakMap();
  const pseudoPaintCandidates = new WeakSet();
  let inspectAllPaintPseudos = false;
  const collectPseudoPaintCandidates = rules => {
    for (const rule of rules) {
      if (rule.cssRules) {
        collectPseudoPaintCandidates(rule.cssRules);
      }
      const selector = String(rule.selectorText || "");
      if (!/::(?:before|after)\b/.test(selector)) continue;
      const baseSelector = selector.replace(/::(?:before|after)\b/g, "");
      try {
        for (const element of document.querySelectorAll(baseSelector)) {
          pseudoPaintCandidates.add(element);
        }
      } catch {
        inspectAllPaintPseudos = true;
      }
    }
  };
  for (const sheet of document.styleSheets) {
    try {
      collectPseudoPaintCandidates(sheet.cssRules);
    } catch {
      // Cross-origin sheets cannot be inspected. Preserve correctness by
      // falling back to computed pseudo styles for every painted layer.
      inspectAllPaintPseudos = true;
    }
  }
  const paintLayerFor = current => {
    if (paintLayerCache.has(current)) return paintLayerCache.get(current);
    const currentStyle = geometryFor(current).style;
    const selector = selectorFor(current);
    const raw = currentStyle.backgroundColor;
    const unresolved = [];
    const properties = [
      ["background-image", currentStyle.backgroundImage, "none"],
      ["background-blend-mode", currentStyle.backgroundBlendMode, "normal"],
      ["mix-blend-mode", currentStyle.mixBlendMode, "normal"],
      ["filter", currentStyle.filter, "none"],
      [
        "backdrop-filter",
        currentStyle.backdropFilter || currentStyle.webkitBackdropFilter,
        "none"
      ]
    ];
    for (const [property, value, clean] of properties) {
      if (value && value !== clean) {
        unresolved.push({selector, property, value});
      }
    }
    const opacity = Number.parseFloat(currentStyle.opacity);
    if (Number.isFinite(opacity) && opacity < 0.999) {
      unresolved.push({
        selector,
        property: "opacity",
        value: currentStyle.opacity
      });
    }
    if (inspectAllPaintPseudos || pseudoPaintCandidates.has(current)) {
      for (const pseudo of ["::before", "::after"]) {
        const pseudoStyle = getComputedStyle(current, pseudo);
        const content = pseudoStyle.content;
        if (content && !["none", "normal", '""'].includes(content)) {
          const pseudoAlpha = computedAlpha(pseudoStyle.backgroundColor);
          if (
            pseudoStyle.backgroundImage !== "none"
            || (pseudoAlpha !== null && pseudoAlpha > 0)
          ) {
            unresolved.push({
              selector,
              property: pseudo,
              value: `${content};${pseudoStyle.backgroundColor};${pseudoStyle.backgroundImage}`
            });
          }
        }
      }
    }
    const result = {
      selector,
      raw,
      alpha: computedAlpha(raw),
      unresolved
    };
    paintLayerCache.set(current, result);
    return result;
  };

  const paintEvidence = (element, style) => {
    const unresolved = [];
    const backgroundLayers = [];
    let current = element;
    let opaque = false;
    while (current) {
      const layer = paintLayerFor(current);
      backgroundLayers.push({selector: layer.selector, raw: layer.raw});
      unresolved.push(...layer.unresolved);
      if (layer.alpha === 1 && layer.unresolved.length === 0) {
        opaque = true;
        break;
      }
      current = current.parentElement;
    }
    if (!opaque) {
      backgroundLayers.push({
        selector: "viewport",
        raw: "rgb(255, 255, 255)"
      });
    }
    return {
      selector: selectorFor(element),
      foreground: {raw: style.color},
      background_layers: backgroundLayers,
      unresolved
    };
  };

  const themeEvidence = (element, style) => ({
    name: element.closest("[data-theme]")?.getAttribute("data-theme") || "",
    colorScheme: style.colorScheme || ""
  });

  const focusVisualSnapshot = style => ({
    outlineStyle: style.outlineStyle,
    outlineWidth: style.outlineWidth,
    outlineColor: style.outlineColor,
    boxShadow: style.boxShadow,
    borderTopColor: style.borderTopColor,
    borderTopWidth: style.borderTopWidth,
    borderRightColor: style.borderRightColor,
    borderRightWidth: style.borderRightWidth,
    borderBottomColor: style.borderBottomColor,
    borderBottomWidth: style.borderBottomWidth,
    borderLeftColor: style.borderLeftColor,
    borderLeftWidth: style.borderLeftWidth,
    backgroundColor: style.backgroundColor,
    color: style.color
  });

  const focusIndicatorProperties = new Set([
    "outlineStyle", "outlineWidth", "outlineColor", "boxShadow",
    "borderTopColor", "borderTopWidth",
    "borderRightColor", "borderRightWidth",
    "borderBottomColor", "borderBottomWidth",
    "borderLeftColor", "borderLeftWidth",
    "backgroundColor", "color"
  ]);
  const focusIndicator = (element, style, rect) => {
    const focused = document.activeElement === element;
    const current = focusVisualSnapshot(style);
    let baseline = null;
    if (focused && element.parentElement) {
      const clone = element.cloneNode(false);
      clone.removeAttribute("autofocus");
      clone.setAttribute("aria-hidden", "true");
      clone.setAttribute("tabindex", "-1");
      clone.style.setProperty("position", "fixed", "important");
      clone.style.setProperty("left", "-10000px", "important");
      clone.style.setProperty("top", "-10000px", "important");
      clone.style.setProperty("visibility", "hidden", "important");
      clone.style.setProperty("pointer-events", "none", "important");
      element.parentElement.appendChild(clone);
      baseline = focusVisualSnapshot(getComputedStyle(clone));
      clone.remove();
    }
    const changedProperties = baseline
      ? Object.keys(current).filter(property => current[property] !== baseline[property])
      : [];
    const outlineWidth = pixels(current.outlineWidth);
    const outlineVisible = (
      !["none", "hidden"].includes(current.outlineStyle)
      && outlineWidth > 0
      && computedAlpha(current.outlineColor) !== 0
    );
    const outlineArea = outlineVisible
      ? (
          (rect.width + outlineWidth * 2) * (rect.height + outlineWidth * 2)
          - rect.width * rect.height
        )
      : 0;
    const borderArea = (
      pixels(current.borderTopWidth) * rect.width
      + pixels(current.borderRightWidth) * rect.height
      + pixels(current.borderBottomWidth) * rect.width
      + pixels(current.borderLeftWidth) * rect.height
    );
    const shadowArea = (
      (rect.width + 2) * (rect.height + 2) - rect.width * rect.height
    );
    const changed = changedProperties.some(
      property => focusIndicatorProperties.has(property)
    );
    return {
      visible: false,
      changed,
      distinguishable: false,
      changedProperties,
      baseline: baseline || {},
      focused: current,
      outlineStyle: current.outlineStyle,
      outlineWidth: round(outlineWidth),
      outlineColor: current.outlineColor,
      boxShadow: current.boxShadow,
      areaByProperty: {
        backgroundColor: round(rect.width * rect.height),
        border: round(borderArea),
        outline: round(outlineArea),
        boxShadow: round(shadowArea)
      },
      area: 0,
      minimum_area: round(2 * 2 * (rect.width + rect.height))
    };
  };

  const paintedSurface = (element, style) => {
    const parentBackground = element.parentElement
      ? geometryFor(element.parentElement).style.backgroundColor
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
    return {hasBorder, hasDistinctBackground};
  };

  const isVisualContainer = (element, style) => {
    const tag = element.tagName.toLowerCase();
    const {hasBorder, hasDistinctBackground} = paintedSurface(element, style);
    const hasContainerName = /(?:card|panel|tile|surface)/i.test(
      `${element.id} ${element.className || ""}`
    );
    return (
      ["article", "dialog"].includes(tag) ||
      hasContainerName ||
      (element.children.length > 0 && hasBorder && hasDistinctBackground)
    );
  };

  const isBoxControl = (element, role, style) => {
    const tag = element.tagName.toLowerCase();
    const inputType = tag === "input"
      ? (element.getAttribute("type") || "text").toLowerCase()
      : "";
    const compactInput = [
      "checkbox", "radio", "range", "color", "file", "hidden"
    ].includes(inputType);
    const boxedRole = new Set([
      "button", "combobox", "listbox", "searchbox", "spinbutton", "textbox"
    ]).has(role);
    const namedAsControl = /(?:button|btn|cta|chip|pill|tab|nav-item)/i.test(
      `${element.id} ${element.className || ""}`
    );
    const {hasBorder, hasDistinctBackground} = paintedSurface(element, style);
    const semanticControl = isControl(element, role);
    return (
      ["button", "select", "textarea"].includes(tag) ||
      (tag === "input" && !compactInput) ||
      boxedRole ||
      (semanticControl && namedAsControl) ||
      (tag === "a" && (hasBorder || hasDistinctBackground))
    );
  };

  const textFlowCount = (element, limit = 2) => {
    const childrenWithText = Array.from(element.children).filter(
      child => (child.textContent || "").trim()
    );
    const blockChildren = childrenWithText.filter(child => (
      !["contents", "inline"].includes(geometryFor(child).style.display)
    ));
    const flowChildren = blockChildren.length
      ? blockChildren
      : childrenWithText.filter(
          child => geometryFor(child).style.display === "contents"
        );
    if (!flowChildren.length) {
      return (element.textContent || "").trim() ? 1 : 0;
    }
    let count = 0;
    for (const child of flowChildren) {
      count += textFlowCount(child, limit - count);
      if (count >= limit) return count;
    }
    return count;
  };

  const isSingleTextFlow = element => textFlowCount(element) <= 1;

  const scrollAxesFor = element => geometryFor(element).scrollAxes;

  const isScrollRegion = element => {
    const axes = scrollAxesFor(element);
    return axes.x || axes.y;
  };

  const clippingCache = new WeakMap();
  const clippingEvidence = element => {
    if (clippingCache.has(element)) return clippingCache.get(element);
    const {rect, style} = geometryFor(element);
    const overflow = {top: 0, right: 0, bottom: 0, left: 0};
    const subject = {
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      left: rect.left
    };
    let clippingAncestorSelector = "";
    let ancestor = element.parentElement;
    while (ancestor) {
      const ancestorGeometry = geometryFor(ancestor);
      const ancestorStyle = ancestorGeometry.style;
      const clipsX = ["clip", "hidden"].includes(ancestorStyle.overflowX);
      const clipsY = ["clip", "hidden"].includes(ancestorStyle.overflowY);
      const scrollsX = ["auto", "scroll"].includes(ancestorStyle.overflowX);
      const scrollsY = ["auto", "scroll"].includes(ancestorStyle.overflowY);
      const ancestorRect = ancestorGeometry.rect;
      if (clipsX || clipsY) {
        const inner = {
          top: ancestorRect.top + pixels(ancestorStyle.borderTopWidth),
          right: ancestorRect.right - pixels(ancestorStyle.borderRightWidth),
          bottom: ancestorRect.bottom - pixels(ancestorStyle.borderBottomWidth),
          left: ancestorRect.left + pixels(ancestorStyle.borderLeftWidth)
        };
        const before = Math.max(...Object.values(overflow));
        if (clipsX) {
          overflow.left = Math.max(overflow.left, inner.left - subject.left);
          overflow.right = Math.max(
            overflow.right,
            subject.right - inner.right
          );
        }
        if (clipsY) {
          overflow.top = Math.max(overflow.top, inner.top - subject.top);
          overflow.bottom = Math.max(
            overflow.bottom,
            subject.bottom - inner.bottom
          );
        }
        if (
          !clippingAncestorSelector &&
          Math.max(...Object.values(overflow)) > Math.max(1, before)
        ) {
          clippingAncestorSelector = selectorFor(ancestor);
        }
      }
      if (scrollsX) {
        subject.left = ancestorRect.left;
        subject.right = ancestorRect.right;
      }
      if (scrollsY) {
        subject.top = ancestorRect.top;
        subject.bottom = ancestorRect.bottom;
      }
      ancestor = ancestor.parentElement;
    }
    const logical = logicalSides(style, overflow);
    const result = {
      clipped: Math.max(...Object.values(overflow)) > 1,
      clippingAncestorSelector,
      overflow,
      logical
    };
    clippingCache.set(element, result);
    return result;
  };

  allElements.forEach(geometryFor);
  const descendantCache = new WeakMap();
  for (const element of [...allElements].reverse()) {
    let bounds = null;
    let containsScrollRegionX = false;
    let containsScrollRegionY = false;
    for (const child of element.children) {
      if (!geometryCache.has(child)) continue;
      const childGeometry = geometryFor(child);
      const childSummary = descendantCache.get(child);
      containsScrollRegionX ||= (
        childGeometry.scrollAxes.x
        || Boolean(childSummary?.containsScrollRegionX)
      );
      containsScrollRegionY ||= (
        childGeometry.scrollAxes.y
        || Boolean(childSummary?.containsScrollRegionY)
      );
      if (!childGeometry.visible) continue;
      const childBounds = childSummary?.bounds;
      const rect = childGeometry.rect;
      const aggregate = childBounds
        ? {
            top: Math.min(rect.top, childBounds.top),
            right: Math.max(rect.right, childBounds.right),
            bottom: Math.max(rect.bottom, childBounds.bottom),
            left: Math.min(rect.left, childBounds.left)
          }
        : {
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
            left: rect.left
          };
      bounds = bounds
        ? {
            top: Math.min(bounds.top, aggregate.top),
            right: Math.max(bounds.right, aggregate.right),
            bottom: Math.max(bounds.bottom, aggregate.bottom),
            left: Math.min(bounds.left, aggregate.left)
          }
        : aggregate;
    }
    descendantCache.set(element, {
      bounds,
      containsScrollRegionX,
      containsScrollRegionY
    });
  }

  const measurementCache = new Map();
  const baseMeasurement = (element) => {
    if (measurementCache.has(element)) return measurementCache.get(element);
    const {style, rect, role} = geometryFor(element);
    const text = textGeometry(element, style, rect);
    const control = isControl(element, role);
    const tag = element.tagName.toLowerCase();
    const directText = Array.from(element.childNodes).some(node => (
      node.nodeType === Node.TEXT_NODE && (node.textContent || "").trim()
    ));
    const controlText = (
      ["input", "textarea"].includes(tag)
      && Boolean(element.value || element.getAttribute("placeholder"))
    ) || (
      tag === "select"
      && Boolean(element.selectedOptions?.[0]?.textContent?.trim())
    );
    const paintedText = Boolean(directText || controlText);
    const visualContainer = isVisualContainer(element, style);
    const boxControl = isBoxControl(element, role, style);
    const paletteRole = paletteRoleFor(element, role, visualContainer);
    const scrollAxes = scrollAxesFor(element);
    const descendantSummary = descendantCache.get(element);
    const containsScrollRegionX = Boolean(
      descendantSummary?.containsScrollRegionX
    );
    const containsScrollRegionY = Boolean(
      descendantSummary?.containsScrollRegionY
    );
    const clipEvidence = clippingEvidence(element);
    const clipsX = ["clip", "hidden"].includes(style.overflowX);
    const clipsY = ["clip", "hidden"].includes(style.overflowY);
    const lineClamp = Number.parseInt(style.webkitLineClamp, 10);
    const intentionalTruncation = (
      style.textOverflow === "ellipsis" ||
      (Number.isFinite(lineClamp) && lineClamp > 0)
    );
    let descendantClipped = false;
    if (
      (clipsX || clipsY)
      && element.children.length
      && descendantSummary?.bounds
    ) {
      const contentLeft = rect.left + pixels(style.borderLeftWidth);
      const contentRight = rect.right - pixels(style.borderRightWidth);
      const contentTop = rect.top + pixels(style.borderTopWidth);
      const contentBottom = rect.bottom - pixels(style.borderBottomWidth);
      const childBounds = descendantSummary.bounds;
      descendantClipped = (
        (clipsX && (
          childBounds.left < contentLeft - 1
          || childBounds.right > contentRight + 1
        ))
        || (clipsY && (
          childBounds.top < contentTop - 1
          || childBounds.bottom > contentBottom + 1
        ))
      );
    }
    const readingHierarchy = element.closest(
      "main,section,article,aside,nav,[role='region']"
    );
    const measurements = {
      hasText: Boolean(text),
      paintedText,
      isMultiline: Boolean(text && text.lineCount > 1),
      isTextFlow: Boolean(text && isSingleTextFlow(element)),
      lineCount: text?.lineCount || 0,
      minimumLineGap: text?.minimumLineGap == null
        ? null
        : round(text.minimumLineGap),
      fontSize: round(text?.fontSize || pixels(style.fontSize)),
      lineHeight: round(text?.lineHeight || pixels(style.lineHeight)),
      fontFamily: style.fontFamily,
      fontShorthand: text?.font || style.font,
      fontStatus: document.fonts?.status || "unsupported",
      fontReady: text?.fontReady ?? null,
      fontAscent: round(text?.fontAscent || 0),
      fontDescent: round(text?.fontDescent || 0),
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      overflowX: style.overflowX,
      overflowY: style.overflowY,
      textOverflow: style.textOverflow,
      lineClamp: Number.isFinite(lineClamp) ? lineClamp : 0,
      intentionalTruncation,
      descendantClipped,
      clippedByAncestor: clipEvidence.clipped,
      clippingAncestorSelector: clipEvidence.clippingAncestorSelector,
      ancestorClipOverflowInlineStart: round(
        clipEvidence.logical.inlineStart
      ),
      ancestorClipOverflowInlineEnd: round(clipEvidence.logical.inlineEnd),
      ancestorClipOverflowBlockStart: round(clipEvidence.logical.blockStart),
      ancestorClipOverflowBlockEnd: round(clipEvidence.logical.blockEnd),
      isControl: control,
      isBoxControl: boxControl,
      isVisualContainer: visualContainer,
      isScrollRegion: scrollAxes.x || scrollAxes.y,
      isScrollRegionX: scrollAxes.x,
      isScrollRegionY: scrollAxes.y,
      containsScrollRegion: containsScrollRegionX || containsScrollRegionY,
      containsScrollRegionX,
      containsScrollRegionY,
      writingMode: style.writingMode,
      direction: style.direction,
      paddingTop: round(pixels(style.paddingTop)),
      paddingRight: round(pixels(style.paddingRight)),
      paddingBottom: round(pixels(style.paddingBottom)),
      paddingLeft: round(pixels(style.paddingLeft)),
      paddingInlineStart: round(pixels(style.paddingInlineStart)),
      paddingInlineEnd: round(pixels(style.paddingInlineEnd)),
      paddingBlockStart: round(pixels(style.paddingBlockStart)),
      paddingBlockEnd: round(pixels(style.paddingBlockEnd)),
      layoutParentSelector: element.parentElement
        ? selectorFor(element.parentElement)
        : "",
      readingHierarchySelector: readingHierarchy
        ? selectorFor(readingHierarchy)
        : "",
      paletteRole,
      readingOrder: documentOrder.get(element) ?? 0,
      prominence: round(
        pixels(style.fontSize)
        * Math.max(1, pixels(style.fontWeight) / 400)
        + Math.log2(Math.max(1, rect.width * rect.height))
        + (/^h[1-6]$/i.test(element.tagName) ? 12 : 0)
      )
    };
    if (text) {
      measurements.textInsetTop = round(text.insets.top);
      measurements.textInsetRight = round(text.insets.right);
      measurements.textInsetBottom = round(text.insets.bottom);
      measurements.textInsetLeft = round(text.insets.left);
      measurements.textInsetInlineStart = round(
        text.logicalInsets.inlineStart
      );
      measurements.textInsetInlineEnd = round(text.logicalInsets.inlineEnd);
      measurements.textInsetBlockStart = round(text.logicalInsets.blockStart);
      measurements.textInsetBlockEnd = round(text.logicalInsets.blockEnd);
      measurements.textBaseline = round(text.baselineProxy);
      measurements.fontBaselineProxy = round(text.baselineProxy);
    }
    const result = {style, rect, role, text, measurements};
    measurementCache.set(element, result);
    return result;
  };

  const peerStats = values => {
    const sorted = values
      .map((value, index) => ({value, index}))
      .sort((first, second) => first.value - second.value);
    const rankByIndex = new Map(
      sorted.map((item, rank) => [item.index, rank])
    );
    const deviations = Array(values.length).fill(null);
    const ranges = Array(values.length).fill(Infinity);
    for (let index = 0; index < values.length; index += 1) {
      const peerCount = values.length - 1;
      if (peerCount < 2) continue;
      const removedRank = rankByIndex.get(index);
      const peerValue = rank => sorted[
        rank + (rank >= removedRank ? 1 : 0)
      ].value;
      const minimum = peerValue(0);
      const maximum = peerValue(peerCount - 1);
      ranges[index] = maximum - minimum;
      if (ranges[index] > 2) continue;
      const middle = Math.floor(peerCount / 2);
      const peerMedian = peerCount % 2
        ? peerValue(middle)
        : (peerValue(middle - 1) + peerValue(middle)) / 2;
      deviations[index] = Math.abs(values[index] - peerMedian);
    }
    return {deviations, ranges};
  };

  const overlapsOnAxis = (first, second, row) => {
    const firstRect = baseMeasurement(first).rect;
    const secondRect = baseMeasurement(second).rect;
    const start = row
      ? Math.max(firstRect.top, secondRect.top)
      : Math.max(firstRect.left, secondRect.left);
    const end = row
      ? Math.min(firstRect.bottom, secondRect.bottom)
      : Math.min(firstRect.right, secondRect.right);
    const size = row
      ? Math.min(firstRect.height, secondRect.height)
      : Math.min(firstRect.width, secondRect.width);
    return size > 0 && (end - start) / size >= 0.5;
  };

  const partitionPeerGroups = (siblings, row, provenance) => {
    const ordered = [...siblings].sort((first, second) => {
      const firstRect = baseMeasurement(first).rect;
      const secondRect = baseMeasurement(second).rect;
      return row
        ? firstRect.top - secondRect.top
        : firstRect.left - secondRect.left;
    });
    const groups = [];
    for (const sibling of ordered) {
      const current = groups[groups.length - 1];
      if (
        current
        && overlapsOnAxis(current.members[0], sibling, row)
      ) {
        current.members.push(sibling);
      } else {
        groups.push({members: [sibling], row, provenance});
      }
    }
    return groups.filter(group => group.members.length >= 3);
  };

  const analyzePeerGroup = group => {
    const measured = group.members.map(baseMeasurement);
    const anchors = group.row
      ? [
          measured.map(item => item.rect.top),
          measured.map(item => item.rect.top + item.rect.height / 2),
          measured.map(item => item.rect.bottom)
        ]
      : [
          measured.map(item => item.rect.left),
          measured.map(item => item.rect.left + item.rect.width / 2),
          measured.map(item => item.rect.right)
        ];
    const anchorStats = anchors.map(peerStats);
    const semanticKeys = group.members.map((item, index) => (
      `${item.tagName.toLowerCase()}:${measured[index].role}`
    ));
    const equivalentPeers = semanticKeys.every(
      value => value === semanticKeys[0]
    );
    const allText = measured.every(item => item.text);
    const fontSizeStats = allText
      ? peerStats(measured.map(item => item.text.fontSize))
      : null;
    const baselineStats = allText
      ? peerStats(measured.map(item => item.text.baselineProxy))
      : null;
    const fontCounts = new Map();
    if (allText) {
      for (const item of measured) {
        fontCounts.set(
          item.style.fontFamily,
          (fontCounts.get(item.style.fontFamily) || 0) + 1
        );
      }
    }
    return {
      ...group,
      measured,
      anchorStats,
      equivalentPeers,
      allText,
      fontSizeStats,
      baselineStats,
      fontCounts
    };
  };

  const peerAnalysisCache = new WeakMap();
  const peerCandidatesFor = parent => {
    if (peerAnalysisCache.has(parent)) {
      return peerAnalysisCache.get(parent);
    }
    const candidates = new Map();
    const siblings = Array.from(parent.children).filter(
      item => geometryCache.has(item) && isVisible(item)
    );
    const parentStyle = geometryFor(parent).style;
    let groups = [];
    if (parentStyle.display === "flex") {
      const row = !parentStyle.flexDirection.startsWith("column");
      groups = partitionPeerGroups(
        siblings,
        row,
        row ? "flex-row" : "flex-column"
      );
    } else if (["grid", "inline-grid"].includes(parentStyle.display)) {
      groups = [
        ...partitionPeerGroups(siblings, true, "grid-row"),
        ...partitionPeerGroups(siblings, false, "grid-column")
      ];
    }
    for (const group of groups.map(analyzePeerGroup)) {
      for (let index = 0; index < group.members.length; index += 1) {
        const deviations = group.anchorStats
          .map(stats => stats.deviations[index])
          .filter(value => value !== null);
        const candidate = {
          group,
          index,
          deviation: deviations.length ? Math.min(...deviations) : 0
        };
        const member = group.members[index];
        const memberCandidates = candidates.get(member) || [];
        memberCandidates.push(candidate);
        candidates.set(member, memberCandidates);
      }
    }
    peerAnalysisCache.set(parent, candidates);
    return candidates;
  };

  const enrichPeerMeasurements = (element, measurements) => {
    const parent = element.parentElement;
    if (!parent) return;
    const candidates = peerCandidatesFor(parent).get(element) || [];
    if (!candidates.length) return;
    const misaligned = candidates.filter(item => item.deviation > 0);
    const peer = (misaligned.length ? misaligned : candidates).sort(
      (first, second) => first.deviation - second.deviation
    )[0];
    const {group, index, deviation} = peer;
    measurements.layoutPeerProvenance = group.provenance;
    measurements.layoutPeerGroup = selectorFor(parent);
    measurements.layoutPeerCount = group.members.length;
    if (group.equivalentPeers && deviation > 0) {
      measurements.layoutAxis = group.row ? "vertical" : "horizontal";
      measurements.layoutDeviation = round(deviation);
    }
    if (!group.equivalentPeers || !group.allText) return;
    if (group.fontSizeStats.ranges[index] <= 1) {
      measurements.fontBaselineDeviation = round(
        group.baselineStats.deviations[index] || 0
      );
    }
    const actualFont = group.measured[index].style.fontFamily;
    if (
      group.fontCounts.size === 2
      && group.fontCounts.get(actualFont) === 1
    ) {
      measurements.fontMismatch = true;
      measurements.expectedFontFamily = [...group.fontCounts.keys()].find(
        value => value !== actualFont
      );
    }
  };

  const candidateSet = new Set(structuralCandidates);
  const textElementPattern = /^(?:h[1-6]|p|li|label|legend|blockquote|figcaption|td|th|dt|dd|span|small|strong|em)$/;
  for (const element of allElements) {
    if (!isVisible(element)) continue;
    const {style, role} = geometryFor(element);
    const tag = element.tagName.toLowerCase();
    const hasText = Boolean((element.textContent || "").trim());
    const parentDisplay = element.parentElement
      ? geometryFor(element.parentElement).style.display
      : "";
    if (
      isControl(element, role) ||
      isVisualContainer(element, style) ||
      (hasText && (textElementPattern.test(tag) || element.children.length === 0)) ||
      ["flex", "grid", "inline-grid"].includes(parentDisplay)
    ) {
      candidateSet.add(element);
    }
  }

  const documentOrder = new Map(
    allElements.map((element, index) => [element, index])
  );
  const priority = element => {
    if (
      element.hasAttribute("data-uidetox-source")
      || element.hasAttribute("data-testid")
      || element.hasAttribute("data-test")
      || element.id
    ) return 0;
    const measured = baseMeasurement(element);
    if (isControl(element, measured.role)) return 1;
    if (
      element.matches(structuralSelector)
      || measured.measurements.isVisualContainer
      || measured.measurements.clippedByAncestor
      || measured.measurements.isScrollRegion
    ) return 2;
    return 3;
  };
  const eligible = Array.from(candidateSet)
    .filter(isVisible)
    .sort((first, second) => (
      priority(first) - priority(second)
      || (documentOrder.get(first) ?? 0) - (documentOrder.get(second) ?? 0)
    ));
  const selected = eligible.slice(0, __UIDETOX_CANDIDATES__);
  const visibleTargets = allElements.filter(element => {
    if (!isVisible(element)) return false;
    const measured = baseMeasurement(element);
    return isControl(element, measured.role);
  });
  const targetGeometryTruncated = totalElements > allElements.length;
  const targetCellSize = 64;
  const targetCellBudget = 4096;
  const targetRecords = visibleTargets.map(element => ({
    element,
    selector: selectorFor(element),
    rect: baseMeasurement(element).rect
  }));
  const minimumTargetShapeGap = targetRecords.some(
    record => record.rect.width < 24 || record.rect.height < 24
  ) ? -24 : -12;
  const targetCells = (rect, expansion = 0) => {
    const cells = [];
    const left = Math.floor((rect.left - expansion) / targetCellSize);
    const right = Math.floor((rect.right + expansion) / targetCellSize);
    const top = Math.floor((rect.top - expansion) / targetCellSize);
    const bottom = Math.floor((rect.bottom + expansion) / targetCellSize);
    const cellCount = (right - left + 1) * (bottom - top + 1);
    if (!Number.isSafeInteger(cellCount) || cellCount > targetCellBudget) {
      return null;
    }
    for (let x = left; x <= right; x += 1) {
      for (let y = top; y <= bottom; y += 1) {
        cells.push(`${x}:${y}`);
      }
    }
    return cells;
  };
  const buildSpatialIndex = records => {
    const byCell = new Map();
    const overflow = [];
    for (const record of records) {
      const cells = targetCells(record.rect);
      if (cells === null) {
        overflow.push(record);
        continue;
      }
      for (const cell of cells) {
        const bucket = byCell.get(cell) || [];
        bucket.push(record);
        byCell.set(cell, bucket);
      }
    }
    return {byCell, overflow};
  };
  const targetSpatialIndex = buildSpatialIndex(targetRecords);
  const targetSpacingEvidence = element => {
    if (targetGeometryTruncated) {
      return {
        status: "unresolved",
        reason: "document-scan-truncated",
        total_targets: targetRecords.length,
        indexed_targets: targetRecords.length,
        truncated: true
      };
    }
    const rect = baseMeasurement(element).rect;
    const cells = targetCells(rect, 24);
    let candidates = targetRecords;
    if (cells !== null) {
      candidates = new Set(targetSpatialIndex.overflow);
      for (const cell of cells) {
        for (const candidate of targetSpatialIndex.byCell.get(cell) || []) {
          candidates.add(candidate);
        }
      }
    }
    let nearest = null;
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    for (const candidate of candidates) {
      if (candidate.element === element) continue;
      const other = candidate.rect;
      const otherCenterX = other.left + other.width / 2;
      const otherCenterY = other.top + other.height / 2;
      const centerDistance = Math.hypot(
        centerX - otherCenterX,
        centerY - otherCenterY
      );
      const horizontalGap = Math.max(
        0,
        Math.max(rect.left, other.left) - Math.min(rect.right, other.right)
      );
      const verticalGap = Math.max(
        0,
        Math.max(rect.top, other.top) - Math.min(rect.bottom, other.bottom)
      );
      const edgeGap = Math.hypot(horizontalGap, verticalGap);
      const neighborUndersized = other.width < 24 || other.height < 24;
      const closestX = Math.max(other.left, Math.min(centerX, other.right));
      const closestY = Math.max(other.top, Math.min(centerY, other.bottom));
      const shapeGap = neighborUndersized
        ? centerDistance - 24
        : Math.hypot(centerX - closestX, centerY - closestY) - 12;
      const intersects = shapeGap < 0;
      if (!nearest || shapeGap < nearest.score) {
        nearest = {
          score: shapeGap,
          selector: candidate.selector,
          centerDistance,
          shapeGap,
          edgeGap,
          intersects,
          neighborShape: neighborUndersized ? "circle" : "rectangle"
        };
        if (shapeGap <= minimumTargetShapeGap) break;
      }
    }
    const evidence = {
      status: nearest?.intersects ? "intersects" : "clear",
      nearest_selector: nearest?.selector || "",
      center_distance_px: nearest ? round(nearest.centerDistance) : null,
      shape_gap_px: nearest ? round(nearest.shapeGap) : null,
      neighbor_shape: nearest?.neighborShape || "",
      edge_gap_px: nearest ? round(nearest.edgeGap) : null,
      total_targets: targetRecords.length,
      indexed_targets: targetRecords.length,
      truncated: false
    };
    if (cells === null) {
      evidence.index = "bounded-linear-fallback";
    }
    return evidence;
  };
  const potentialOccluderRecords = allElements
    .filter(element => {
      if (!isVisible(element)) return false;
      const {style} = geometryFor(element);
      const position = style.position;
      return (
        ["fixed", "sticky"].includes(position)
        || (
          position !== "static"
          && style.zIndex !== "auto"
          && Number.isFinite(Number.parseFloat(style.zIndex))
        )
        || (element.tagName.toLowerCase() === "dialog" && element.open)
        || element.matches("[popover]:popover-open")
      );
    })
    .map(element => ({
      element,
      rect: baseMeasurement(element).rect
    }));
  const occluderSpatialIndex = buildSpatialIndex(potentialOccluderRecords);
  // Ephemeral per-capture index; this is never retained in Python or artifacts.
  const semanticSiblingGroups = new WeakMap();
  const semanticSiblingEvidence = element => {
    const parent = element.parentElement;
    if (!parent) {
      return null;
    }
    const measured = baseMeasurement(element);
    const key = `${element.tagName.toLowerCase()}:${measured.role}`;
    let groups = semanticSiblingGroups.get(parent);
    if (!groups) {
      groups = new Map();
      semanticSiblingGroups.set(parent, groups);
    }
    if (groups.has(key)) {
      return groups.get(key);
    }
    const peers = Array.from(parent.children).filter(candidate => {
      if (!geometryCache.has(candidate) || !isVisible(candidate)) return false;
      const candidateRole = baseMeasurement(candidate).role;
      return `${candidate.tagName.toLowerCase()}:${candidateRole}` === key;
    });
    const parentStyle = geometryFor(parent).style;
    const axis = (
      parentStyle.display === "flex"
      && ["row", "row-reverse"].includes(parentStyle.flexDirection)
    )
      ? "horizontal"
      : "vertical";
    const evidence = peers.length < 3
      ? null
      : {
          group: `${selectorFor(parent)}:${key}`,
          evidence: "same-parent-role",
          axis,
          peers: peers.slice(0, 20).map(peer => selectorFor(peer))
        };
    groups.set(key, evidence);
    return evidence;
  };
  const targetException = (element, role, style) => {
    if (element.getAttribute("data-uidetox-essential") === "true") {
      return "essential";
    }
    if (role === "link" && style.display === "inline") {
      return "inline";
    }
    if (
      ["input", "select", "textarea"].includes(element.tagName.toLowerCase())
      && style.appearance === "auto"
    ) {
      return "user-agent";
    }
    return "";
  };
  const occlusionEvidence = (element, rect) => {
    const possibleOccluders = new Set();
    const addOccluder = candidate => {
      if (
        candidate.element !== element
        && !candidate.element.contains(element)
        && !element.contains(candidate.element)
        && candidate.rect.right > rect.left
        && candidate.rect.left < rect.right
        && candidate.rect.bottom > rect.top
        && candidate.rect.top < rect.bottom
      ) {
        possibleOccluders.add(candidate.element);
      }
    };
    const cells = targetCells(rect);
    if (cells === null) {
      potentialOccluderRecords.forEach(addOccluder);
    } else {
      occluderSpatialIndex.overflow.forEach(addOccluder);
      for (const cell of cells) {
        for (const candidate of occluderSpatialIndex.byCell.get(cell) || []) {
          addOccluder(candidate);
        }
      }
    }
    if (!possibleOccluders.size) {
      return {selector: "", fraction: 0};
    }
    const insetX = Math.min(2, Math.max(0, rect.width / 4));
    const insetY = Math.min(2, Math.max(0, rect.height / 4));
    const points = [
      [rect.left + rect.width / 2, rect.top + rect.height / 2],
      [rect.left + insetX, rect.top + insetY],
      [rect.right - insetX, rect.top + insetY],
      [rect.left + insetX, rect.bottom - insetY],
      [rect.right - insetX, rect.bottom - insetY]
    ].filter(([x, y]) => (
      x >= 0 && y >= 0 && x < window.innerWidth && y < window.innerHeight
    ));
    const covering = new Map();
    for (const [x, y] of points) {
      const top = document.elementFromPoint(x, y);
      if (!top || top === element || element.contains(top)) continue;
      const selector = selectorFor(top);
      covering.set(selector, (covering.get(selector) || 0) + 1);
    }
    if (!covering.size || !points.length) {
      return {selector: "", fraction: 0};
    }
    const [selector, count] = [...covering.entries()].sort(
      (first, second) => second[1] - first[1]
    )[0];
    const evidence = {selector, fraction: count / points.length};
    return evidence;
  };
  const elements = selected.map((element, candidateOrder) => {
    const {style, rect, role, measurements} = baseMeasurement(element);
    measurements.theme = themeEvidence(element, style);
    if (measurements.paintedText) {
      measurements.paint = paintEvidence(element, style);
    }
    if (isControl(element, role) && document.activeElement === element) {
      measurements.focusIndicator = focusIndicator(element, style, rect);
    }
    enrichPeerMeasurements(element, measurements);
    const equivalence = semanticSiblingEvidence(element);
    if (equivalence) {
      measurements.equivalenceGroup = equivalence.group;
      measurements.equivalenceEvidence = equivalence.evidence;
      measurements.equivalenceAxis = equivalence.axis;
      measurements.equivalentPeerSelectors = equivalence.peers;
    }
    if (isControl(element, role)) {
      measurements.targetSpacing = targetSpacingEvidence(element);
      measurements.targetException = targetException(element, role, style);
    }
    const occlusion = occlusionEvidence(element, rect);
    measurements.occludedBy = occlusion.selector;
    measurements.occludedFraction = round(occlusion.fraction);

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
    states.hovered = element.matches(":hover");
    states.focused = document.activeElement === element;
    states.error = (
      element.getAttribute("aria-invalid") === "true"
      || (typeof element.matches === "function" && element.matches(":invalid"))
    );
    states.tabIndex = element.tabIndex;
    const sourceSelectors = sourceSelectorsFor(element);

    return {
      kind,
      tag,
      role,
      name: nameFor(element),
      selector: selectorFor(element, sourceSelectors),
      source_hint: element.getAttribute("data-uidetox-source") || "",
      source_selectors: sourceSelectors,
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
        textOverflow: style.textOverflow,
        writingMode: style.writingMode,
        direction: style.direction,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        paddingTop: style.paddingTop,
        paddingRight: style.paddingRight,
        paddingBottom: style.paddingBottom,
        paddingLeft: style.paddingLeft,
        paddingInlineStart: style.paddingInlineStart,
        paddingInlineEnd: style.paddingInlineEnd,
        paddingBlockStart: style.paddingBlockStart,
        paddingBlockEnd: style.paddingBlockEnd,
        alignItems: style.alignItems,
        flexDirection: style.flexDirection,
        gap: style.gap,
        gridTemplateColumns: style.gridTemplateColumns,
        borderRadius: style.borderRadius,
      },
      states,
      measurements
    };
  });
  return {
    elements,
    coverage: {
      total: totalElements,
      candidates: candidateSet.size,
      eligible: eligible.length,
      emitted: elements.length,
      budget: __UIDETOX_CANDIDATES__,
      truncated: (
        totalElements > allElements.length
        || eligible.length > elements.length
      ),
      target_geometry: {
        visible: targetRecords.length,
        indexed: targetRecords.length,
        truncated: targetGeometryTruncated,
        index: "spatial-grid"
      }
    }
  };
}
"""
