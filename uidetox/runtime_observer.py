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
from uidetox.findings import Finding
from uidetox.runtime_layout import detect_runtime_findings
from uidetox.runtime_scenarios import (
    DEFAULT_VIEWPORTS,
    RuntimeCaptureRecord,
    RuntimeCoverage,
    RuntimeDiagnostic,
    RuntimeDomBudget,
    RuntimeReadiness,
    RuntimeReadinessPolicy,
    RuntimeScenario,
    RuntimeScenarioAction,
    RuntimeViewport,
    normalize_runtime_urls,
    runtime_capture_id,
)
from uidetox.utils import now_iso


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
            measurements=(dict(measurements) if isinstance(measurements, dict) else {}),
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
            finding.code == "runtime-component-clipped"
            for finding in element.findings
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
                    and finding.metrics.get("clipping_ancestor")
                    in clipping_containers
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


def _legacy_capture(page: RuntimePage, generated_at: str) -> RuntimeCaptureRecord:
    capture_id = page.capture_id or runtime_capture_id(
        page.scenario,
        page.state,
        page.url,
        page.viewport,
    )
    return RuntimeCaptureRecord(
        capture_id=capture_id,
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
    status: str = ""

    def __post_init__(self) -> None:
        pages = tuple(
            page
            if page.capture_id
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
        captures = self.captures
        if not captures and pages:
            captures = tuple(
                _legacy_capture(page, self.generated_at) for page in pages
            )
            object.__setattr__(self, "captures", captures)
        completed = sum(capture.status == "completed" for capture in captures)
        failed = sum(capture.status == "failed" for capture in captures)
        degraded = any(
            capture.readiness.status == "degraded"
            or capture.coverage.truncated
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
) -> RuntimeObservation:
    """Observe explicit browser scenarios through one bounded capture engine.

    The caller must start the dev server. Individual navigation failures are
    recorded so other URLs/viewports can still complete; missing Playwright or
    browser binaries fail immediately with an actionable error.
    """

    normalized_urls = normalize_runtime_urls(urls)
    normalized_viewports = tuple(viewports)
    if not normalized_viewports:
        raise ValueError("At least one runtime viewport is required.")
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be greater than zero.")
    if settle_ms < 0:
        raise ValueError("settle_ms must be zero or greater.")
    active_scenarios = (
        tuple(scenarios)
        if scenarios is not None
        else tuple(
            RuntimeScenario(
                name="default",
                url=url,
                expected_state="initial",
                readiness=readiness
                or RuntimeReadinessPolicy(settle_ms=settle_ms),
            )
            for url in normalized_urls
        )
    )
    if not active_scenarios:
        raise ValueError("At least one runtime scenario is required.")
    unrequested_urls = {
        scenario.url for scenario in active_scenarios
    } - set(normalized_urls)
    if unrequested_urls:
        raise ValueError("Runtime scenario URLs must be included in requested URLs.")

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
    )


def _scenario_viewports(
    scenario: RuntimeScenario,
    available: tuple[RuntimeViewport, ...],
) -> tuple[RuntimeViewport, ...]:
    if not scenario.viewports:
        return available
    requested = set(scenario.viewports)
    selected = tuple(viewport for viewport in available if viewport.name in requested)
    if len(selected) != len(requested):
        missing = requested - {viewport.name for viewport in selected}
        raise ValueError(
            f"Scenario viewports were not provided: {', '.join(sorted(missing))}"
        )
    return selected


def _scenario_states(scenario: RuntimeScenario) -> tuple[str, ...]:
    states = tuple(
        action.state for action in scenario.actions if action.kind == "capture"
    )
    return states or (scenario.expected_state,)


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
                    state_context["state"] = action.state or state_context["state"]
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
            return tuple(pages), tuple(captures), ()
        except Exception as exc:
            state = state_context["state"]
            message = f"{scenario.url} [{viewport.name}/{scenario.name}/{state}]: {exc}"
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
            return tuple(pages), tuple(captures), tuple(errors)
    finally:
        context.close()


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
            outcome = page.evaluate(
                """
                policy => new Promise(resolve => {
                  const finish = outcome => {
                    observer.disconnect();
                    clearTimeout(idleTimer);
                    clearTimeout(limitTimer);
                    resolve(outcome);
                  };
                  let idleTimer = setTimeout(() => finish("idle"), policy.idle);
                  const limitTimer = setTimeout(
                    () => finish("timeout"),
                    policy.timeout
                  );
                  const observer = new MutationObserver(() => {
                    clearTimeout(idleTimer);
                    idleTimer = setTimeout(
                      () => finish("idle"),
                      policy.idle
                    );
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
                    "timeout": timeout_ms,
                },
            )
            if outcome == "timeout":
                status = "degraded"
                detail = "mutation-idle timed out"
        elif policy.request_idle_ms:
            strategy = "request-idle"
            page.wait_for_load_state(
                "networkidle",
                timeout=min(policy.request_idle_ms, timeout_ms),
            )
    except playwright_timeout_error as exc:
        status = (
            "failed"
            if strategy in {"selector", "app-hook"}
            else "degraded"
        )
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
        value = os.environ.get(action.env) if action.env else action.value
        if action.env and value is None:
            raise ValueError(
                f"Runtime scenario environment variable is missing: {action.env}"
            )
        page.locator(action.selector).fill(value or "", timeout=action.timeout_ms)
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
    runtime_page = RuntimePage(
        url=page.url,
        title=page.title(),
        viewport=viewport,
        elements=elements,
        screenshot=screenshot,
        capture_id=capture_id,
        scenario=scenario.name,
        state=state,
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
    if namer is None or (scenario.name == "default" and state == "initial"):
        return namer

    def name(url: str, viewport: RuntimeViewport) -> str:
        base = Path(namer(url, viewport))
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
            RuntimeElement.from_dict(item)
            for item in payload
            if isinstance(item, dict)
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
    return (
        _RUNTIME_EVALUATE_SCRIPT.replace("__UIDETOX_SCAN__", str(budget.scan))
        .replace("__UIDETOX_CANDIDATES__", str(budget.candidates))
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

  const selectorFor = (element, sourceSelectors = sourceSelectorsFor(element)) => {
    const stable = sourceSelectors.find(
      selector => selector.startsWith("#") || selector.startsWith("[data-")
    );
    if (stable) return stable;
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
    const visualContainer = isVisualContainer(element, style);
    const boxControl = isBoxControl(element, role, style);
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
    const measurements = {
      hasText: Boolean(text),
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
      paddingBlockEnd: round(pixels(style.paddingBlockEnd))
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
      return null;
    }
    return Math.abs(values[index] - median(peers));
  };

  const enrichPeerMeasurements = (element, measurements) => {
    const parent = element.parentElement;
    if (!parent) return;
    const parentStyle = geometryFor(parent).style;
    const siblings = Array.from(parent.children)
      .filter(isVisible)
      .slice(0, 20);
    if (siblings.length < 3 || !siblings.includes(element)) return;
    const elementRect = baseMeasurement(element).rect;
    const overlaps = (item, row) => {
      const rect = baseMeasurement(item).rect;
      const start = row
        ? Math.max(elementRect.top, rect.top)
        : Math.max(elementRect.left, rect.left);
      const end = row
        ? Math.min(elementRect.bottom, rect.bottom)
        : Math.min(elementRect.right, rect.right);
      const size = row
        ? Math.min(elementRect.height, rect.height)
        : Math.min(elementRect.width, rect.width);
      return size > 0 && (end - start) / size >= 0.5;
    };
    const groups = [];
    if (parentStyle.display === "flex") {
      const row = !parentStyle.flexDirection.startsWith("column");
      groups.push({
        members: siblings.filter(item => overlaps(item, row)),
        row,
        provenance: row ? "flex-row" : "flex-column"
      });
    } else if (["grid", "inline-grid"].includes(parentStyle.display)) {
      groups.push(
        {
          members: siblings.filter(item => overlaps(item, true)),
          row: true,
          provenance: "grid-row"
        },
        {
          members: siblings.filter(item => overlaps(item, false)),
          row: false,
          provenance: "grid-column"
        }
      );
    } else {
      return;
    }
    const candidates = [];
    for (const group of groups.filter(item => item.members.length >= 3)) {
      const index = group.members.indexOf(element);
      if (index < 0) continue;
      const anchors = group.row
        ? [
            group.members.map(item => baseMeasurement(item).rect.top),
            group.members.map(item => {
              const rect = baseMeasurement(item).rect;
              return rect.top + rect.height / 2;
            }),
            group.members.map(item => baseMeasurement(item).rect.bottom)
          ]
        : [
            group.members.map(item => baseMeasurement(item).rect.left),
            group.members.map(item => {
              const rect = baseMeasurement(item).rect;
              return rect.left + rect.width / 2;
            }),
            group.members.map(item => baseMeasurement(item).rect.right)
          ];
      const deviations = anchors
        .map(values => clusteredPeerDeviation(values, index))
        .filter(value => value !== null);
      candidates.push({
        ...group,
        deviation: deviations.length ? Math.min(...deviations) : 0
      });
    }
    if (!candidates.length) return;
    const misalignedGroups = candidates.filter(item => item.deviation > 0);
    const peerGroup = (misalignedGroups.length
      ? misalignedGroups
      : candidates
    ).sort(
      (first, second) => first.deviation - second.deviation
    )[0];
    const semanticKeys = peerGroup.members.map(item => {
      const measured = baseMeasurement(item);
      return `${item.tagName.toLowerCase()}:${measured.role}`;
    });
    const equivalentPeers = semanticKeys.every(
      value => value === semanticKeys[0]
    );
    measurements.layoutPeerProvenance = peerGroup.provenance;
    measurements.layoutPeerSelectors = peerGroup.members.map(
      member => selectorFor(member)
    );
    if (equivalentPeers && peerGroup.deviation > 0) {
      measurements.layoutAxis = peerGroup.row ? "vertical" : "horizontal";
      measurements.layoutDeviation = round(peerGroup.deviation);
    }

    const index = peerGroup.members.indexOf(element);
    const textPeers = peerGroup.members.map(item => baseMeasurement(item));
    if (equivalentPeers && textPeers.every(item => item.text)) {
      const peerSizes = textPeers
        .filter((_item, peerIndex) => peerIndex !== index)
        .map(item => item.text.fontSize);
      if (Math.max(...peerSizes) - Math.min(...peerSizes) <= 1) {
        const baselines = textPeers.map(item => item.text.baselineProxy);
        measurements.fontBaselineDeviation = round(
          clusteredPeerDeviation(baselines, index) || 0
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
  const elements = selected.map((element, candidateOrder) => {
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
        gridTemplateColumns: style.gridTemplateColumns
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
      )
    }
  };
}
"""
