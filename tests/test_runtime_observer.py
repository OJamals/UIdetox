"""Browser-boundary tests for the shared runtime observer."""

from __future__ import annotations

import builtins
import json
import sys
import types
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox import runtime_observer
from uidetox.runtime_observer import (
    DEFAULT_VIEWPORTS,
    RuntimeElement,
    RuntimeObservation,
    RuntimePage,
    RuntimeViewport,
    detect_runtime_findings,
    observe_frontend,
)
from uidetox.runtime_scenarios import (
    RUNTIME_OBSERVATION_LIMITS,
    VIEWPORT_REGISTRY,
    RuntimeCaptureRecord,
    RuntimeCoverage,
    RuntimeDiagnostic,
    RuntimeDomBudget,
    RuntimeReadiness,
    RuntimeReadinessPolicy,
    RuntimeScenario,
    RuntimeScenarioAction,
    discover_runtime_viewports,
    load_runtime_scenarios,
    normalize_runtime_urls,
    validate_runtime_observation_plan,
)


def _measured_element(**measurements: object) -> RuntimeElement:
    return RuntimeElement(
        kind="action",
        tag="button",
        role="button",
        name="Save changes",
        selector="#save",
        order=0,
        bounds={"x": 10, "y": 10, "width": 120, "height": 36},
        styles={"fontSize": "16px", "lineHeight": "16px"},
        measurements=measurements,
    )


def _finding_codes(element: RuntimeElement) -> set[str]:
    return {finding.code for finding in detect_runtime_findings(element)}


def _capture_record(
    capture_id: str,
    *,
    status: str,
    readiness: str = "current",
) -> RuntimeCaptureRecord:
    return RuntimeCaptureRecord(
        capture_id=capture_id,
        scenario="default",
        state="initial",
        url="https://example.invalid",
        viewport=VIEWPORT_REGISTRY["desktop"],
        status=status,
        readiness=RuntimeReadiness(
            status=readiness,
            strategy="request-idle",
            duration_ms=1,
        ),
        coverage=RuntimeCoverage(
            total=1,
            candidates=1,
            eligible=1,
            emitted=1,
            budget=10,
        ),
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
    )


def test_scenario_schema_rejects_unsafe_or_unbounded_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Unsupported runtime action"):
        RuntimeScenarioAction.from_dict({"kind": "destroy", "selector": "#account"})
    with pytest.raises(ValueError, match="Unknown runtime action fields: value"):
        RuntimeScenarioAction.from_dict(
            {"kind": "fill", "selector": "#nickname", "value": "inline-bypass"}
        )
    with pytest.raises(ValueError, match="environment variable"):
        RuntimeScenarioAction.from_dict(
            {"kind": "fill", "selector": "#nickname"}
        )
    with pytest.raises(ValueError, match="Unknown runtime action fields: key"):
        RuntimeScenarioAction.from_dict(
            {"kind": "click", "selector": "#save", "key": "Enter"}
        )
    with pytest.raises(ValueError, match="must be one of"):
        RuntimeScenarioAction.from_dict(
            {"kind": "wait-for-state", "state": "visible"}
        )
    with pytest.raises(ValueError, match="must be one of"):
        RuntimeScenarioAction.from_dict(
            {
                "kind": "wait-for-state",
                "selector": "#ready",
                "state": "networkidle",
            }
        )
    with pytest.raises(ValueError, match="timeout_ms"):
        RuntimeScenarioAction.from_dict(
            {"kind": "wait-for-selector", "selector": "#ready", "timeout_ms": 0}
        )
    fill = RuntimeScenarioAction.from_dict(
        {"kind": "fill", "selector": "#nickname", "env": "UIDETOX_TEST_VALUE"}
    )
    assert fill.env == "UIDETOX_TEST_VALUE"
    monkeypatch.setenv(fill.env, "never-print-this-value")
    locator = SimpleNamespace(
        fill=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("never-print-this-value")
        )
    )
    with pytest.raises(RuntimeError) as fill_error:
        runtime_observer._perform_action(
            SimpleNamespace(locator=lambda _selector: locator),
            fill,
        )
    assert "never-print-this-value" not in str(fill_error.value)

    outside = tmp_path.parent / "outside-runtime-scenarios.json"
    outside.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="inside"):
        load_runtime_scenarios(outside, root=tmp_path)


def test_runtime_work_limits_reject_before_playwright_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = RUNTIME_OBSERVATION_LIMITS
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (limits.scenario_file_bytes + 1))
    with pytest.raises(ValueError, match="file exceeds"):
        load_runtime_scenarios(oversized, root=tmp_path)

    def write_scenarios(name: str, value: object) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    scenario = {"name": "bounded", "url": "https://example.invalid"}
    with pytest.raises(ValueError, match="scenario count"):
        load_runtime_scenarios(
            write_scenarios(
                "too-many.json",
                [
                    {**scenario, "name": f"scenario-{index}"}
                    for index in range(limits.scenarios + 1)
                ],
            ),
            root=tmp_path,
        )
    action = {"kind": "click", "selector": "#save", "timeout_ms": 1}
    with pytest.raises(ValueError, match="scenario action count"):
        load_runtime_scenarios(
            write_scenarios(
                "too-many-actions.json",
                [
                    {
                        **scenario,
                        "actions": [action] * (limits.actions_per_scenario + 1),
                    }
                ],
            ),
            root=tmp_path,
        )
    with pytest.raises(ValueError, match="total action count"):
        load_runtime_scenarios(
            write_scenarios(
                "too-many-total-actions.json",
                [
                    {
                        **scenario,
                        "name": f"scenario-{index}",
                        "actions": [action] * limits.actions_per_scenario,
                    }
                    for index in range(
                        limits.actions_total // limits.actions_per_scenario + 1
                    )
                ],
            ),
            root=tmp_path,
        )

    original_import = builtins.__import__

    def reject_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            pytest.fail("over-budget observation reached Playwright import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_playwright)
    with pytest.raises(ValueError, match="URL count"):
        observe_frontend(
            tuple(
                f"https://example.invalid/{index}"
                for index in range(limits.scenarios + 1)
            )
        )
    viewports = tuple(
        RuntimeViewport(f"viewport-{index}", 320 + index, 800)
        for index in range(limits.viewports + 1)
    )
    with pytest.raises(ValueError, match="viewport count"):
        observe_frontend("https://example.invalid", viewports=viewports)
    with pytest.raises(ValueError, match="timeout_ms"):
        observe_frontend("https://example.invalid", timeout_ms=limits.timeout_ms + 1)
    with pytest.raises(ValueError, match="settle_ms"):
        observe_frontend("https://example.invalid", settle_ms=limits.settle_ms + 1)

    bounded_viewports = viewports[: limits.viewports]
    matrix_scenario = RuntimeScenario(
        name="matrix",
        url="https://example.invalid",
        actions=tuple(
            RuntimeScenarioAction(kind="capture", state=f"state-{index}")
            for index in range(limits.capture_matrix // limits.viewports + 1)
        ),
    )
    with pytest.raises(ValueError, match="capture matrix"):
        observe_frontend(
            matrix_scenario.url,
            viewports=bounded_viewports,
            scenarios=(matrix_scenario,),
        )
    boundary_root = tmp_path / "boundary-project"
    boundary_root.mkdir()
    (boundary_root / "responsive.css").write_text(
        "\n".join(
            f"@media (min-width: {400 + index * 100}px) {{ main {{ order: {index}; }} }}"
            for index in range(8)
        ),
        encoding="utf-8",
    )
    boundary_matrix = RuntimeScenario(
        name="boundary-matrix",
        url="https://example.invalid",
        actions=tuple(
            RuntimeScenarioAction(kind="capture", state=f"state-{index}")
            for index in range(14)
        ),
    )
    with pytest.raises(ValueError, match="capture matrix"):
        observe_frontend(
            boundary_matrix.url,
            scenarios=(boundary_matrix,),
            source_root=boundary_root,
        )

    work_scenarios = tuple(
        RuntimeScenario(
            name=f"work-{index}",
            url="https://example.invalid",
            actions=tuple(
                RuntimeScenarioAction(
                    kind="click",
                    selector="#save",
                    timeout_ms=1,
                )
                for _ in range(limits.actions_per_scenario)
            ),
            readiness=RuntimeReadinessPolicy(request_idle_ms=0, settle_ms=0),
        )
        for index in range(2)
    )
    with pytest.raises(ValueError, match="observation work"):
        observe_frontend(
            "https://example.invalid",
            viewports=bounded_viewports,
            scenarios=work_scenarios,
            timeout_ms=1,
            settle_ms=0,
        )

    time_scenario = RuntimeScenario(
        name="time",
        url="https://example.invalid",
        actions=tuple(
            RuntimeScenarioAction(
                kind="click",
                selector="#save",
                timeout_ms=limits.timeout_ms,
            )
            for _ in range(15)
        ),
        readiness=RuntimeReadinessPolicy(request_idle_ms=0, settle_ms=0),
    )
    with pytest.raises(ValueError, match="time budget"):
        observe_frontend(
            time_scenario.url,
            viewports=bounded_viewports[:2],
            scenarios=(time_scenario,),
            timeout_ms=limits.timeout_ms,
            settle_ms=0,
        )


def test_public_runtime_iterables_stop_at_limit_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uidetox import runtime_scenarios

    limits = RUNTIME_OBSERVATION_LIMITS

    def guarded(factory, limit):
        for index in range(limit + 1):
            yield factory(index)
        raise AssertionError("iterable consumed past limit+1")

    with pytest.raises(ValueError, match="URL count"):
        normalize_runtime_urls(
            guarded(lambda _index: "https://example.invalid", limits.scenarios)
        )

    original_import = builtins.__import__

    def reject_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            pytest.fail("bounded iterable reached Playwright import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_playwright)
    monkeypatch.setattr(
        runtime_observer,
        "discover_runtime_viewports",
        lambda *_args, **_kwargs: pytest.fail(
            "over-budget viewports reached source discovery"
        ),
    )
    with pytest.raises(ValueError, match="viewport count"):
        observe_frontend(
            "https://example.invalid",
            viewports=guarded(
                lambda index: RuntimeViewport(
                    f"viewport-{index}",
                    320 + index,
                    800,
                ),
                limits.viewports,
            ),
            source_root=tmp_path,
        )

    with pytest.raises(ValueError, match="scenario count"):
        observe_frontend(
            "https://example.invalid",
            scenarios=guarded(
                lambda index: RuntimeScenario(
                    name=f"scenario-{index}",
                    url="https://example.invalid",
                ),
                limits.scenarios,
            ),
        )

    monkeypatch.setattr(
        runtime_scenarios.ProjectFileSet,
        "discover",
        lambda _self: pytest.fail(
            "over-budget base viewports reached project source scan"
        ),
    )
    with pytest.raises(ValueError, match="viewport count"):
        discover_runtime_viewports(
            tmp_path,
            base_viewports=guarded(
                lambda index: RuntimeViewport(
                    f"base-{index}",
                    320 + index,
                    800,
                ),
                limits.viewports,
            ),
        )

    with pytest.raises(ValueError, match="scenario count"):
        validate_runtime_observation_plan(
            guarded(
                lambda index: RuntimeScenario(
                    name=f"direct-{index}",
                    url="https://example.invalid",
                ),
                limits.scenarios,
            ),
            (VIEWPORT_REGISTRY["desktop"],),
            timeout_ms=1_000,
            settle_ms=0,
        )
    with pytest.raises(ValueError, match="viewport count"):
        validate_runtime_observation_plan(
            (
                RuntimeScenario(
                    name="direct",
                    url="https://example.invalid",
                ),
            ),
            guarded(
                lambda index: RuntimeViewport(
                    f"direct-{index}",
                    320 + index,
                    800,
                ),
                limits.viewports,
            ),
            timeout_ms=1_000,
            settle_ms=0,
        )


def test_source_boundaries_supplement_canonical_viewports(tmp_path: Path) -> None:
    (tmp_path / "responsive.css").write_text(
        """
@media (max-width: 600px) { main { display: block; } }
@container card (inline-size >= 42rem) { article { display: grid; } }
@container card (min-width: 500px) { article { gap: 1rem; } }
""".strip(),
        encoding="utf-8",
    )

    discovery = discover_runtime_viewports(
        tmp_path,
        base_viewports=(VIEWPORT_REGISTRY["desktop"],),
    )

    assert discovery.total_boundaries == 2
    assert discovery.truncated is False
    assert {boundary.width for boundary in discovery.boundaries} == {500, 600}
    probes = [viewport for viewport in discovery.viewports if viewport.kind == "boundary"]
    assert {viewport.width for viewport in probes} == {499, 501, 599, 601}
    assert all(viewport.sources == ("responsive.css",) for viewport in probes)


def test_observation_status_never_promotes_partial_or_degraded_to_current() -> None:
    page = RuntimePage(
        url="https://example.invalid",
        title="Example",
        viewport=VIEWPORT_REGISTRY["desktop"],
        elements=(),
        capture_id="ok",
    )
    partial = RuntimeObservation(
        generated_at="2026-07-26T00:00:00Z",
        requested_urls=("https://example.invalid",),
        pages=(page,),
        captures=(
            _capture_record("ok", status="completed"),
            _capture_record("failed", status="failed"),
        ),
    )
    degraded = RuntimeObservation(
        generated_at="2026-07-26T00:00:00Z",
        requested_urls=("https://example.invalid",),
        pages=(page,),
        captures=(
            _capture_record("ok", status="completed", readiness="degraded"),
        ),
    )

    assert partial.status == "partial"
    assert degraded.status == "degraded"
    assert RuntimeObservation.from_dict(partial.to_dict()) == partial


def test_runtime_payload_exposes_truncation_instead_of_silent_slicing() -> None:
    elements, coverage = runtime_observer._elements_and_coverage_from_payload(
        {
            "elements": [{}, {}, {}, {}],
            "coverage": {
                "total": 20,
                "candidates": 12,
                "eligible": 10,
                "emitted": 4,
                "budget": 4,
                "truncated": True,
            },
        },
        RuntimeDomBudget(scan=20, candidates=4),
    )

    assert len(elements) == 4
    assert coverage.truncated is True
    assert coverage.emitted == 4
    assert coverage.candidates == 12


def test_default_viewports_are_canonical_registry_members() -> None:
    assert DEFAULT_VIEWPORTS == tuple(
        VIEWPORT_REGISTRY[name] for name in ("mobile", "tablet", "desktop")
    )


def test_runtime_diagnostics_round_trip_with_scenario_provenance() -> None:
    diagnostic = RuntimeDiagnostic(
        kind="console",
        code="browser-console-error",
        message="boom",
        severity="error",
        scenario="modal",
        state="open",
        url="https://example.invalid",
        viewport="desktop",
        source="console",
    )

    assert RuntimeDiagnostic.from_dict(asdict(diagnostic)) == diagnostic


def test_context_close_diagnostics_are_finalized_on_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks: dict[str, object] = {}

    class Page:
        def on(self, event, callback) -> None:
            callbacks[event] = callback

        def goto(self, *_args, **_kwargs) -> None:
            return None

    page = Page()

    class Context:
        def new_page(self):
            return page

        def close(self) -> None:
            callbacks["console"](
                SimpleNamespace(type="error", text="late console failure")
            )

    class Browser:
        def new_context(self, **_kwargs):
            return Context()

    scenario = RuntimeScenario(
        name="default",
        url="https://example.invalid",
        readiness=RuntimeReadinessPolicy(request_idle_ms=0, settle_ms=0),
    )
    runtime_page = RuntimePage(
        url=scenario.url,
        title="Late",
        viewport=VIEWPORT_REGISTRY["desktop"],
        elements=(),
        capture_id="late",
    )
    monkeypatch.setattr(
        runtime_observer,
        "_wait_for_readiness",
        lambda *_args, **_kwargs: RuntimeReadiness("current", "test", 0),
    )
    monkeypatch.setattr(
        runtime_observer,
        "_capture_scenario_state",
        lambda *_args, **_kwargs: (
            runtime_page,
            _capture_record("late", status="completed"),
        ),
    )

    _pages, captures, errors = runtime_observer._observe_scenario(
        Browser(),
        scenario,
        VIEWPORT_REGISTRY["desktop"],
        timeout_ms=1_000,
        dom_budget=RuntimeDomBudget(scan=10, candidates=10),
        screenshot_root=None,
        screenshot_namer=None,
        full_page=True,
        playwright_timeout_error=RuntimeError,
    )

    assert errors == ()
    assert [diagnostic.code for diagnostic in captures[0].diagnostics] == [
        "browser-console-error"
    ]


def test_finalization_preserves_capture_local_coverage_diagnostic(
    tmp_path: Path,
) -> None:
    from uidetox.frontend_map import map_frontend

    coverage_diagnostic = RuntimeDiagnostic(
        kind="coverage",
        code="runtime-dom-budget-exceeded",
        message="DOM coverage truncated.",
        severity="warning",
        scenario="default",
        state="initial",
        url="https://example.invalid",
        viewport="desktop",
        source="dom-budget",
    )
    late_diagnostic = RuntimeDiagnostic(
        kind="console",
        code="browser-console-error",
        message="late console failure",
        severity="error",
        scenario="default",
        state="initial",
        url="https://example.invalid",
        viewport="desktop",
        source="console",
    )
    capture = replace(
        _capture_record("coverage", status="completed"),
        coverage=RuntimeCoverage(
            total=20,
            candidates=10,
            eligible=10,
            emitted=4,
            budget=4,
            truncated=True,
        ),
        diagnostics=(coverage_diagnostic,),
    )
    finalized = runtime_observer._finalize_capture_diagnostics(
        (capture,),
        (late_diagnostic, late_diagnostic),
    )

    assert [diagnostic.code for diagnostic in finalized[0].diagnostics] == [
        "runtime-dom-budget-exceeded",
        "browser-console-error",
    ]
    page = RuntimePage(
        url=capture.url,
        title="Coverage",
        viewport=capture.viewport,
        elements=(),
        capture_id=capture.capture_id,
        scenario=capture.scenario,
        state=capture.state,
    )
    observation = RuntimeObservation(
        generated_at="2026-07-26T00:00:01Z",
        requested_urls=(capture.url,),
        pages=(page,),
        captures=finalized,
    )
    (tmp_path / "index.html").write_text("<main>Coverage</main>", encoding="utf-8")
    frontend_map = map_frontend(tmp_path, runtime=observation)

    assert {
        finding["code"]
        for finding in frontend_map.evidence["runtime_findings"]
    } == {
        "runtime-dom-budget-exceeded",
        "browser-console-error",
    }


def test_finalization_keeps_diagnostics_on_their_exact_capture() -> None:
    first_state = RuntimeDiagnostic(
        kind="console",
        code="first-state-error",
        message="failure before opening",
        severity="error",
        scenario="checkout",
        state="closed",
        url="https://example.invalid",
        viewport="desktop",
        source="console",
    )
    coverage = RuntimeDiagnostic(
        kind="coverage",
        code="runtime-dom-budget-exceeded",
        message="DOM coverage truncated.",
        severity="warning",
        scenario="checkout",
        state="open",
        url="https://example.invalid",
        viewport="desktop",
        source="dom-budget",
    )
    late_current_state = RuntimeDiagnostic(
        kind="console",
        code="late-current-state-error",
        message="failure while open",
        severity="error",
        scenario="checkout",
        state="open",
        url="https://example.invalid",
        viewport="desktop",
        source="console",
    )
    mismatched_current_state = tuple(
        replace(late_current_state, code=code, **changes)
        for code, changes in (
            ("wrong-scenario", {"scenario": "other"}),
            ("wrong-url", {"url": "https://other.invalid"}),
            ("wrong-viewport", {"viewport": "tablet"}),
        )
    )
    first_capture = replace(
        _capture_record("closed", status="completed"),
        scenario="checkout",
        state="closed",
        diagnostics=(first_state,),
    )
    second_capture = replace(
        _capture_record("open", status="completed"),
        scenario="checkout",
        state="open",
        diagnostics=(first_state, coverage, *mismatched_current_state),
    )

    finalized = runtime_observer._finalize_capture_diagnostics(
        (first_capture, second_capture),
        (first_state, late_current_state, late_current_state),
    )

    assert [diagnostic.code for diagnostic in finalized[0].diagnostics] == [
        "first-state-error"
    ]
    assert [diagnostic.code for diagnostic in finalized[1].diagnostics] == [
        "runtime-dom-budget-exceeded",
        "late-current-state-error",
    ]
    assert all(
        diagnostic.state == capture.state
        and diagnostic.scenario == capture.scenario
        and diagnostic.url == capture.url
        and diagnostic.viewport == capture.viewport.name
        for capture in finalized
        for diagnostic in capture.diagnostics
    )


def test_runtime_diagnostics_are_sanitized_before_serialization(
    tmp_path: Path,
) -> None:
    from uidetox.frontend_map import map_frontend

    callbacks: dict[str, object] = {}
    page = SimpleNamespace(on=lambda event, callback: callbacks.__setitem__(event, callback))
    scenario = RuntimeScenario(
        name="safe",
        url="https://example.invalid/dashboard",
    )
    diagnostics: list[RuntimeDiagnostic] = []
    runtime_observer._install_diagnostic_listeners(
        page,
        diagnostics,
        scenario=scenario,
        viewport=VIEWPORT_REGISTRY["desktop"],
        state_context={"state": "initial"},
    )
    console_secret = "sk-1234567890abcdefghijkl"
    password_secret = "correct-horse-battery-staple"
    query_secret = "query-secret-value"
    callbacks["console"](
        SimpleNamespace(type="error", text=f"token={console_secret}")
    )
    callbacks["pageerror"](RuntimeError(f"password={password_secret}"))
    callbacks["requestfailed"](
        SimpleNamespace(
            url=f"https://user:pass@example.invalid/api?token={query_secret}#fragment",
            failure=f"authorization=Bearer {console_secret}",
        )
    )
    callbacks["response"](
        SimpleNamespace(
            status=500,
            url=f"https://example.invalid/api?token={query_secret}#fragment",
        )
    )

    viewport = VIEWPORT_REGISTRY["desktop"]
    page_evidence = RuntimePage(
        url=scenario.url,
        title="Safe",
        viewport=viewport,
        elements=(),
        capture_id="safe-capture",
        scenario=scenario.name,
        state="initial",
    )
    capture = RuntimeCaptureRecord(
        capture_id=page_evidence.capture_id,
        scenario=scenario.name,
        state="initial",
        url=scenario.url,
        viewport=viewport,
        status="completed",
        readiness=RuntimeReadiness("current", "selector", 1),
        coverage=RuntimeCoverage.empty(1),
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
        diagnostics=tuple(diagnostics),
    )
    observation = RuntimeObservation(
        generated_at="2026-07-26T00:00:01Z",
        requested_urls=(scenario.url,),
        pages=(page_evidence,),
        captures=(capture,),
    )
    (tmp_path / "index.html").write_text("<main>Safe</main>", encoding="utf-8")
    serialized = json.dumps(map_frontend(tmp_path, runtime=observation).to_dict())
    assert console_secret not in serialized
    assert password_secret not in serialized
    assert query_secret not in serialized
    assert "user:pass@" not in serialized
    assert "https://example.invalid/api" in serialized


def _skip_missing_browser(exc: RuntimeError) -> None:
    message = str(exc).lower()
    if "playwright unavailable" in message:
        pytest.skip("Playwright is not installed for runtime integration tests.")
    if "playwright install chromium" in message:
        pytest.skip("Chromium is not installed for runtime integration tests.")


def test_detect_runtime_findings_reports_layout_and_font_misalignment() -> None:
    element = _measured_element(
        layoutAxis="vertical",
        layoutDeviation=6.0,
        fontBaselineDeviation=5.0,
    )

    codes = _finding_codes(element)

    assert "runtime-layout-misalignment" in codes
    assert "runtime-font-misalignment" in codes


def test_detect_runtime_findings_reports_text_and_component_clipping() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=120.0,
        scrollWidth=156.0,
        clientHeight=36.0,
        scrollHeight=52.0,
        overflowX="hidden",
        overflowY="clip",
        descendantClipped=True,
    )

    codes = _finding_codes(element)

    assert "runtime-text-clipped" in codes
    assert "runtime-component-clipped" in codes


def test_detect_runtime_findings_reports_text_clipped_by_ancestor() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=120.0,
        scrollWidth=120.0,
        clientHeight=36.0,
        scrollHeight=36.0,
        overflowX="visible",
        overflowY="visible",
        clippedByAncestor=True,
        ancestorClipOverflowInlineEnd=9.0,
        clippingAncestorSelector="#card",
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-text-clipped"}
    assert findings[0].metrics["clipping_ancestor"] == "#card"


def test_detect_runtime_findings_distinguishes_intentional_truncation() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=120.0,
        scrollWidth=156.0,
        clientHeight=36.0,
        scrollHeight=36.0,
        overflowX="hidden",
        overflowY="visible",
        intentionalTruncation=True,
        textOverflow="ellipsis",
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-text-truncated"}
    assert findings[0].severity == "info"


def test_detect_runtime_findings_reports_text_edge_contact_and_padding() -> None:
    element = _measured_element(
        hasText=True,
        isControl=True,
        isBoxControl=True,
        isVisualContainer=True,
        isTextFlow=True,
        textInsetTop=2.0,
        textInsetRight=1.0,
        textInsetBottom=2.0,
        textInsetLeft=1.0,
        paddingTop=2.0,
        paddingRight=4.0,
        paddingBottom=2.0,
        paddingLeft=4.0,
    )

    codes = _finding_codes(element)

    assert "runtime-text-edge-contact" in codes
    assert "runtime-horizontal-padding" in codes
    assert "runtime-vertical-padding" in codes


def test_detect_runtime_findings_prefers_logical_axis_padding() -> None:
    element = _measured_element(
        hasText=True,
        isControl=True,
        isBoxControl=True,
        isVisualContainer=True,
        isTextFlow=True,
        textInsetInlineStart=10.0,
        textInsetInlineEnd=10.0,
        textInsetBlockStart=10.0,
        textInsetBlockEnd=10.0,
        paddingInlineStart=3.0,
        paddingInlineEnd=12.0,
        paddingBlockStart=2.0,
        paddingBlockEnd=8.0,
    )

    codes = _finding_codes(element)

    assert "runtime-horizontal-padding" in codes
    assert "runtime-vertical-padding" in codes


def test_detect_runtime_findings_reports_inadequate_multiline_spacing() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        fontSize=16.0,
        lineHeight=17.0,
    )

    assert "runtime-line-spacing" in _finding_codes(element)


def test_detect_runtime_findings_reports_overlapping_lines_as_error() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        isTextFlow=True,
        fontSize=16.0,
        lineHeight=24.0,
        minimumLineGap=-2.0,
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-line-spacing"}
    assert findings[0].severity == "error"
    assert findings[0].metrics["minimum_line_gap_px"] == -2.0


def test_detect_runtime_findings_ignores_multiple_nested_text_flows() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        isTextFlow=False,
        fontSize=16.0,
        lineHeight=17.0,
    )

    assert "runtime-line-spacing" not in _finding_codes(element)


def test_detect_runtime_findings_ignores_healthy_geometry() -> None:
    element = _measured_element(
        hasText=True,
        isMultiline=True,
        isControl=True,
        isBoxControl=True,
        isVisualContainer=True,
        isTextFlow=True,
        fontSize=16.0,
        lineHeight=24.0,
        clientWidth=120.0,
        scrollWidth=120.0,
        clientHeight=48.0,
        scrollHeight=48.0,
        overflowX="visible",
        overflowY="visible",
        textInsetTop=10.0,
        textInsetRight=12.0,
        textInsetBottom=10.0,
        textInsetLeft=12.0,
        paddingTop=10.0,
        paddingRight=12.0,
        paddingBottom=10.0,
        paddingLeft=12.0,
        layoutDeviation=1.0,
        fontBaselineDeviation=1.0,
    )

    assert detect_runtime_findings(element) == ()


def test_attach_runtime_findings_collapses_clipped_descendants_into_container() -> None:
    container = replace(
        _measured_element(descendantClipped=True),
        kind="region",
        tag="aside",
        role="complementary",
        selector="#sidebar",
    )
    child = replace(
        _measured_element(
            hasText=True,
            clippedByAncestor=True,
            clippingAncestorSelector="#sidebar",
        ),
        selector="#sidebar-link",
    )

    attached = runtime_observer._attach_runtime_findings((container, child))

    assert _finding_codes(attached[0]) == {"runtime-component-clipped"}
    assert attached[1].findings == ()


def test_plain_link_and_compact_input_are_not_padding_targets() -> None:
    plain_link = _measured_element(
        hasText=True,
        isControl=True,
        isBoxControl=False,
        isVisualContainer=False,
        paddingInlineStart=0.0,
        paddingInlineEnd=0.0,
        paddingBlockStart=0.0,
        paddingBlockEnd=0.0,
    )

    assert detect_runtime_findings(plain_link) == ()


def test_visual_container_accepts_child_managed_spacing_and_scroll_regions() -> None:
    container = _measured_element(
        hasText=True,
        isBoxControl=False,
        isVisualContainer=True,
        isTextFlow=False,
        containsScrollRegionX=True,
        containsScrollRegionY=False,
        textInsetInlineStart=0.0,
        textInsetInlineEnd=-120.0,
        textInsetBlockStart=12.0,
        textInsetBlockEnd=12.0,
        paddingInlineStart=0.0,
        paddingInlineEnd=0.0,
        paddingBlockStart=12.0,
        paddingBlockEnd=12.0,
    )

    assert detect_runtime_findings(container) == ()


def test_inline_scroll_region_does_not_hide_block_padding_defects() -> None:
    container = _measured_element(
        hasText=True,
        isBoxControl=False,
        isVisualContainer=True,
        isTextFlow=False,
        containsScrollRegionX=True,
        containsScrollRegionY=False,
        textInsetInlineStart=0.0,
        textInsetInlineEnd=-120.0,
        textInsetBlockStart=0.0,
        textInsetBlockEnd=0.0,
        paddingInlineStart=0.0,
        paddingInlineEnd=0.0,
        paddingBlockStart=0.0,
        paddingBlockEnd=0.0,
    )

    assert _finding_codes(container) == {"runtime-vertical-padding"}


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
                "measurements": {
                    "hasText": True,
                    "isMultiline": True,
                    "fontSize": 16.0,
                    "lineHeight": 17.0,
                },
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
    assert all(
        event[1]["reduced_motion"] == "reduce"
        for event in events
        if event[0] == "context"
    )
    assert len(observation.pages) == 2
    assert [Path(page.screenshot or "").name for page in observation.pages] == [
        "after_mobile.png",
        "after_desktop.png",
    ]
    assert all(
        Path(page.screenshot or "").read_bytes() == b"partial-png"
        for page in observation.pages
    )
    assert {finding.code for finding in observation.pages[0].elements[0].findings} == {
        "runtime-line-spacing"
    }
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


@pytest.mark.browser
def test_observer_detects_rendered_layout_and_typography_defects(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "layout-defects.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  .row { display: flex; align-items: flex-start; gap: 8px; }
  .peer { width: 100px; height: 36px; padding: 8px 12px; }
  #misaligned { transform: translateY(7px); font-family: serif; }
  .grid { display: grid; grid-template-columns: repeat(3, 100px); gap: 8px; }
  #grid-misaligned { transform: translateY(7px); }
  #truncated { width: 70px; overflow: hidden; white-space: nowrap; }
  #ellipsis {
    width: 70px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  #card { width: 180px; padding: 2px; border: 1px solid black; }
  #tight { width: 110px; font-size: 16px; line-height: 17px; }
  #clip { width: 80px; height: 30px; overflow: clip; }
  #clip > div { width: 140px; height: 50px; }
  #ancestor-clip { width: 90px; overflow: hidden; white-space: nowrap; }
  #ancestor-clipped-text {
    display: inline-block;
    margin-left: 70px;
    width: 100px;
  }
  #badge { background: #eee; }
</style>
<main>
  <div class="row">
    <button class="peer">First</button>
    <button class="peer">Second</button>
    <button class="peer" id="misaligned">Third</button>
  </div>
  <div class="grid">
    <button class="peer">Alpha</button>
    <button class="peer">Beta</button>
    <button class="peer" id="grid-misaligned">Gamma</button>
  </div>
  <div class="row">
    <button class="peer">North</button>
    <button class="peer">South</button>
    <button class="peer" id="font-only" style="font-family: serif">West</button>
  </div>
  <button id="truncated">This label is deliberately too long</button>
  <button id="ellipsis">This label is intentionally shortened</button>
  <article id="card"><p>Card text</p></article>
  <p id="tight">Tight multiline text needs more leading.</p>
  <section id="clip"><div>Oversized child component</div></section>
  <div id="ancestor-clip">
    <span id="ancestor-clipped-text">Clipped by ancestor</span>
  </div>
  <span id="badge">New</span>
</main>
""".strip(),
        encoding="utf-8",
    )

    origin = local_http_server(tmp_path)
    try:
        observation = observe_frontend(
            f"{origin}/{fixture.name}",
            viewports=(RuntimeViewport("desktop", 1280, 800),),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    assert observation.pages, observation.errors
    findings_by_selector = {
        element.selector: {finding.code for finding in element.findings}
        for element in observation.pages[0].elements
        if element.findings
    }
    elements_by_selector = {
        element.selector: element for element in observation.pages[0].elements
    }

    assert "runtime-layout-misalignment" in findings_by_selector["#misaligned"]
    assert "runtime-font-misalignment" in findings_by_selector["#misaligned"]
    assert "runtime-layout-misalignment" in findings_by_selector["#grid-misaligned"]
    assert "runtime-font-misalignment" in findings_by_selector["#font-only"]
    assert "runtime-layout-misalignment" not in findings_by_selector["#font-only"]
    assert "runtime-text-clipped" in findings_by_selector["#truncated"]
    assert "runtime-text-truncated" in findings_by_selector["#ellipsis"]
    assert "runtime-text-clipped" not in findings_by_selector["#ellipsis"]
    assert "runtime-text-edge-contact" in findings_by_selector["#card"]
    assert "runtime-horizontal-padding" in findings_by_selector["#card"]
    assert "runtime-vertical-padding" not in findings_by_selector["#card"]
    assert "runtime-line-spacing" in findings_by_selector["#tight"]
    assert "runtime-component-clipped" in findings_by_selector["#clip"]
    assert "runtime-text-clipped" in findings_by_selector["#ancestor-clipped-text"]
    assert "#badge" not in findings_by_selector
    assert elements_by_selector["#tight"].measurements["fontStatus"] == "loaded"
    assert elements_by_selector["#tight"].measurements["fontReady"] is True
    assert elements_by_selector["#tight"].measurements["isTextFlow"] is True
    assert isinstance(
        elements_by_selector["#tight"].measurements["minimumLineGap"],
        (int, float),
    )
    assert isinstance(
        elements_by_selector["#misaligned"].measurements["fontBaselineProxy"],
        (int, float),
    )
    assert (
        elements_by_selector["#misaligned"].measurements["layoutPeerProvenance"]
        == "flex-row"
    )
    assert elements_by_selector["#card"].measurements["paddingInlineStart"] == 2
    assert (
        elements_by_selector["#ancestor-clipped-text"].measurements["clippedByAncestor"]
        is True
    )
    assert (
        elements_by_selector["#ancestor-clipped-text"].measurements[
            "clippingAncestorSelector"
        ]
        == "#ancestor-clip"
    )


@pytest.mark.browser
def test_fullstack_lab_runtime_observation_is_repeatable(
    tmp_path: Path,
    local_http_server,
) -> None:
    lab = Path(__file__).parents[1] / "examples" / "fullstack-slop-lab"
    origin = local_http_server(lab)

    def capture(run: str) -> tuple[dict[str, object], ...]:
        screenshot_root = tmp_path / run
        try:
            observation = observe_frontend(
                f"{origin}/index.html",
                viewports=DEFAULT_VIEWPORTS,
                screenshots_dir=screenshot_root,
                settle_ms=0,
            )
        except RuntimeError as exc:
            _skip_missing_browser(exc)
            raise

        assert observation.errors == ()
        assert len(observation.pages) == len(DEFAULT_VIEWPORTS)
        assert all(
            page.screenshot and Path(page.screenshot).is_file()
            for page in observation.pages
        )
        return tuple(
            {
                "url": page.url,
                "title": page.title,
                "viewport": (
                    page.viewport.name,
                    page.viewport.width,
                    page.viewport.height,
                ),
                "elements": tuple(
                    (
                        element.kind,
                        element.tag,
                        element.role,
                        element.name,
                        element.selector,
                        tuple(finding.code for finding in element.findings),
                    )
                    for element in page.elements
                ),
            }
            for page in observation.pages
        )

    assert capture("first") == capture("second")


@pytest.mark.browser
def test_scenario_observation_records_interaction_state_and_diagnostics(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "scenario.html"
    fixture.write_text(
        """
<!doctype html>
<button id="open">Open modal</button>
<dialog id="modal"><p>Ready</p></dialog>
<script>
  document.querySelector("#open").addEventListener("click", () => {
    document.querySelector("#modal").showModal();
    console.error("fixture console failure");
    setTimeout(() => { throw new Error("fixture page failure"); }, 0);
    fetch("/missing-runtime-resource");
  });
</script>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)
    scenario = RuntimeScenario(
        name="modal",
        url=f"{origin}/{fixture.name}",
        actions=(
            RuntimeScenarioAction(kind="click", selector="#open"),
            RuntimeScenarioAction(kind="wait-for-selector", selector="#modal[open]"),
            RuntimeScenarioAction(kind="capture", state="open"),
        ),
        expected_state="open",
        readiness=RuntimeReadinessPolicy(
            selector="#open",
            request_idle_ms=0,
            settle_ms=0,
        ),
    )

    observation = observe_frontend(
        scenario.url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        scenarios=(scenario,),
        settle_ms=0,
    )

    assert observation.status == "current"
    assert [page.state for page in observation.pages] == ["open"]
    assert any(element.selector == "#modal" for element in observation.pages[0].elements)
    assert {
        diagnostic.code
        for diagnostic in observation.captures[0].diagnostics
    } >= {
        "browser-console-error",
        "browser-http-error",
        "browser-page-error",
    }


@pytest.mark.browser
def test_dom_budget_finds_prioritized_tail_or_reports_coverage(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "large-dom.html"
    fixture.write_text(
        "<!doctype html><main>"
        + "".join(f"<div>Node {index}</div>" for index in range(3_200))
        + '<button id="tail-defect" style="width:20px;overflow:hidden">'
        "Tail action deliberately clipped"
        "</button></main>",
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    observation = observe_frontend(
        f"{origin}/{fixture.name}",
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        dom_budget=RuntimeDomBudget(scan=4_000, candidates=100),
        settle_ms=0,
    )

    page = observation.pages[0]
    coverage = observation.captures[0].coverage
    assert (
        any(element.selector == "#tail-defect" for element in page.elements)
        or coverage.truncated
    )
    assert coverage.total >= 3_201
    assert coverage.emitted <= 100


@pytest.mark.browser
def test_top_aligned_variable_height_peer_is_not_misaligned(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "top-aligned.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  .row { display: flex; align-items: flex-start; }
  .card { width: 100px; }
  #short { height: 40px; }
  .tall { height: 80px; }
</style>
<main class="row">
  <article class="card" id="short">Short</article>
  <article class="card tall">Tall A</article>
  <article class="card tall">Tall B</article>
</main>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    observation = observe_frontend(
        f"{origin}/{fixture.name}",
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        settle_ms=0,
    )
    short = next(
        element
        for element in observation.pages[0].elements
        if element.selector == "#short"
    )

    assert "runtime-layout-misalignment" not in _finding_codes(short)


@pytest.mark.browser
def test_peer_analysis_covers_aligned_and_outlier_tails_after_twenty(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "peer-tail.html"
    aligned = "".join(
        f'<article class="peer">Aligned {index}</article>' for index in range(24)
    )
    outliers = "".join(
        f'<article class="peer">Outlier row {index}</article>' for index in range(24)
    )
    fixture.write_text(
        f"""
<!doctype html>
<style>
  .row {{ display: flex; align-items: flex-start; }}
  .peer {{ flex: 0 0 44px; height: 40px; }}
  #tail-outlier {{ margin-top: 12px; }}
</style>
<main>
  <section class="row">{aligned}<article class="peer" id="tail-aligned">Tail</article></section>
  <section class="row">{outliers}<article class="peer" id="tail-outlier">Tail</article></section>
</main>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    observation = observe_frontend(
        f"{origin}/{fixture.name}",
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        settle_ms=0,
    )
    assert observation.pages, observation.errors
    elements = {
        element.selector: element for element in observation.pages[0].elements
    }

    assert elements["#tail-aligned"].measurements["layoutPeerCount"] == 25
    assert "runtime-layout-misalignment" not in _finding_codes(
        elements["#tail-aligned"]
    )
    assert elements["#tail-outlier"].measurements["layoutPeerCount"] == 25
    assert "runtime-layout-misalignment" in _finding_codes(
        elements["#tail-outlier"]
    )


@pytest.mark.browser
def test_source_boundary_text_zoom_and_long_localization_runtime_probes(
    tmp_path: Path,
    local_http_server,
) -> None:
    boundary = tmp_path / "boundary.html"
    boundary.write_text(
        """
<!doctype html>
<link rel="stylesheet" href="responsive.css">
<main id="boundary">Boundary</main>
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "responsive.css").write_text(
        "@media (max-width: 640px) { main { display: grid; } }",
        encoding="utf-8",
    )
    adversarial = tmp_path / "adversarial-copy.html"
    adversarial.write_text(
        """
<!doctype html>
<style>
  html { font-size: 200%; }
  #zoom-copy, #localized-action {
    display: block;
    width: 120px;
    overflow: hidden;
    white-space: nowrap;
  }
</style>
<main>
  <p id="zoom-copy">Zoomed text must remain completely readable</p>
  <button id="localized-action">Änderungen unwiderruflich speichern</button>
</main>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    boundary_observation = observe_frontend(
        f"{origin}/{boundary.name}",
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        source_root=tmp_path,
        settle_ms=0,
    )
    discovery = boundary_observation.viewport_discovery
    assert discovery is not None
    assert discovery.total_boundaries == 1
    assert {page.viewport.width for page in boundary_observation.pages} == {
        639,
        641,
        1440,
    }
    assert all(
        page.viewport.boundary_px == 640
        for page in boundary_observation.pages
        if page.viewport.kind == "boundary"
    )

    copy_observation = observe_frontend(
        f"{origin}/{adversarial.name}",
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        settle_ms=0,
    )
    elements = {
        element.selector: element for element in copy_observation.pages[0].elements
    }
    assert elements["#zoom-copy"].measurements["fontSize"] == 32
    assert "runtime-text-clipped" in _finding_codes(elements["#zoom-copy"])
    assert "runtime-text-clipped" in _finding_codes(
        elements["#localized-action"]
    )


@pytest.mark.browser
def test_readiness_distinguishes_slow_hydration_from_polling_degradation(
    tmp_path: Path,
    local_http_server,
) -> None:
    hydrated = tmp_path / "hydrated.html"
    hydrated.write_text(
        """
<!doctype html>
<main id="root">Hydrating</main>
<script>
  setTimeout(() => {
    document.querySelector("#root").textContent = "Ready";
    document.querySelector("#root").dataset.ready = "true";
  }, 75);
</script>
""".strip(),
        encoding="utf-8",
    )
    polling = tmp_path / "polling.html"
    polling.write_text(
        """
<!doctype html>
<main>Streaming</main>
<script>setInterval(() => fetch("/poll"), 25);</script>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)
    scenarios = (
        RuntimeScenario(
            name="hydrated",
            url=f"{origin}/{hydrated.name}",
            readiness=RuntimeReadinessPolicy(
                selector='[data-ready="true"]',
                request_idle_ms=0,
                settle_ms=0,
            ),
        ),
        RuntimeScenario(
            name="polling",
            url=f"{origin}/{polling.name}",
            readiness=RuntimeReadinessPolicy(
                request_idle_ms=200,
                settle_ms=0,
            ),
        ),
    )

    observation = observe_frontend(
        tuple(scenario.url for scenario in scenarios),
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        scenarios=scenarios,
        timeout_ms=1_000,
        settle_ms=0,
    )

    readiness = {
        capture.scenario: capture.readiness.status
        for capture in observation.captures
    }
    assert readiness == {"hydrated": "current", "polling": "degraded"}
    assert observation.status == "degraded"


@pytest.mark.browser
def test_capture_then_failure_finalizes_exact_semantic_state_diagnostic(
    tmp_path: Path,
    local_http_server,
) -> None:
    from uidetox.frontend_map import map_frontend

    fixture = tmp_path / "late-failure.html"
    fixture.write_text(
        '<main><button id="ready">Ready</button></main>',
        encoding="utf-8",
    )
    url = f"{local_http_server(tmp_path)}/{fixture.name}"
    scenario = RuntimeScenario(
        name="late-failure",
        url=url,
        actions=(
            RuntimeScenarioAction(kind="capture", state="ready"),
            RuntimeScenarioAction(
                kind="wait-for-state",
                selector="#ready",
                state="visible",
                timeout_ms=500,
            ),
            RuntimeScenarioAction(
                kind="click",
                selector="#missing",
                timeout_ms=100,
            ),
        ),
        readiness=RuntimeReadinessPolicy(request_idle_ms=0, settle_ms=0),
    )

    observation = observe_frontend(
        url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        scenarios=(scenario,),
        timeout_ms=1_000,
        settle_ms=0,
    )

    assert observation.status == "partial"
    assert len(observation.captures) == 1
    capture = observation.captures[0]
    assert capture.state == "ready"
    action_failures = [
        diagnostic
        for diagnostic in capture.diagnostics
        if diagnostic.code == "browser-action-failed"
    ]
    assert len(action_failures) == 1
    assert action_failures[0].scenario == scenario.name
    assert action_failures[0].state == capture.state
    frontend_map = map_frontend(tmp_path, runtime=observation)
    finding = next(
        item
        for item in frontend_map.evidence["runtime_findings"]
        if item["code"] == "browser-action-failed"
    )
    assert finding["runtime_anchor"]["capture_id"] == capture.capture_id
    assert finding["runtime_anchor"]["scenario"] == scenario.name
    assert finding["runtime_anchor"]["state"] == capture.state
