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
from uidetox.findings import Finding
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
    runtime_capture_id,
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
    *,
    status: str,
    readiness: str = "current",
    scenario: str = "default",
    state: str = "initial",
    url: str = "https://example.invalid",
) -> RuntimeCaptureRecord:
    viewport = VIEWPORT_REGISTRY["desktop"]
    return RuntimeCaptureRecord(
        capture_id=runtime_capture_id(scenario, state, url, viewport),
        scenario=scenario,
        state=state,
        url=url,
        viewport=viewport,
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


def test_runtime_capture_record_requires_executable_identity() -> None:
    viewport = VIEWPORT_REGISTRY["desktop"]
    fields = {
        "scenario": "checkout",
        "state": "ready",
        "url": "https://example.invalid/checkout",
        "viewport": viewport,
        "status": "completed",
        "readiness": RuntimeReadiness("current", "selector", 1),
        "coverage": RuntimeCoverage(1, 1, 1, 1, 10),
        "started_at": "2026-07-27T00:00:00Z",
        "completed_at": "2026-07-27T00:00:01Z",
    }
    expected = runtime_capture_id(
        fields["scenario"],
        fields["state"],
        fields["url"],
        viewport,
    )

    with pytest.raises(
        ValueError,
        match=rf"expected '{expected}', got 'checkout-ready'",
    ):
        RuntimeCaptureRecord(capture_id="checkout-ready", **fields)

    canonical = RuntimeCaptureRecord(capture_id=expected, **fields)
    serialized = asdict(canonical)
    serialized["capture_id"] = "persisted-label"
    with pytest.raises(
        ValueError,
        match=rf"expected '{expected}', got 'persisted-label'",
    ):
        RuntimeCaptureRecord.from_dict(serialized)


def test_page_only_observation_replaces_descriptive_capture_identity() -> None:
    viewport = VIEWPORT_REGISTRY["desktop"]
    page = RuntimePage(
        url="https://example.invalid/checkout",
        title="Checkout",
        viewport=viewport,
        elements=(),
        capture_id="checkout-ready",
        scenario="checkout",
        state="ready",
    )
    expected = runtime_capture_id(
        page.scenario,
        page.state,
        page.url,
        page.viewport,
    )

    observation = RuntimeObservation(
        generated_at="2026-07-27T00:00:00Z",
        requested_urls=(page.url,),
        pages=(page,),
    )

    assert observation.pages[0].capture_id == expected
    assert observation.captures[0].capture_id == expected


def test_observation_rejects_page_identity_without_matching_capture() -> None:
    page = RuntimePage(
        url="https://example.invalid/checkout",
        title="Checkout",
        viewport=VIEWPORT_REGISTRY["desktop"],
        elements=(),
        capture_id="checkout-ready",
        scenario="checkout",
        state="ready",
    )
    capture = _capture_record(
        status="completed",
        scenario=page.scenario,
        state=page.state,
        url=page.url,
    )

    with pytest.raises(
        ValueError,
        match="Runtime page capture identity has no matching record: 'checkout-ready'",
    ):
        RuntimeObservation(
            generated_at="2026-07-27T00:00:00Z",
            requested_urls=(page.url,),
            pages=(page,),
            captures=(capture,),
        )


def test_observation_rejects_duplicate_capture_identity() -> None:
    capture = _capture_record(status="completed")

    with pytest.raises(
        ValueError,
        match=rf"Runtime observation has duplicate capture identity: "
        rf"'{capture.capture_id}'",
    ):
        RuntimeObservation(
            generated_at="2026-07-27T00:00:00Z",
            requested_urls=(capture.url,),
            pages=(),
            captures=(capture, capture),
        )


def test_observation_rejects_duplicate_page_identity() -> None:
    capture = _capture_record(status="completed")
    page = RuntimePage(
        url="https://example.invalid/resolved",
        title="Resolved",
        viewport=capture.viewport,
        elements=(),
        capture_id=capture.capture_id,
        scenario=capture.scenario,
        state=capture.state,
    )

    with pytest.raises(
        ValueError,
        match=rf"Runtime observation has duplicate page identity: "
        rf"'{capture.capture_id}'",
    ):
        RuntimeObservation(
            generated_at="2026-07-27T00:00:00Z",
            requested_urls=(capture.url,),
            pages=(page, page),
            captures=(capture,),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scenario", "other"),
        ("state", "other"),
        ("viewport", VIEWPORT_REGISTRY["mobile"]),
    ),
)
def test_observation_rejects_page_metadata_drift_from_capture(
    field: str,
    value: object,
) -> None:
    capture = _capture_record(status="completed")
    page = replace(
        RuntimePage(
            url="https://example.invalid/resolved",
            title="Resolved",
            viewport=capture.viewport,
            elements=(),
            capture_id=capture.capture_id,
            scenario=capture.scenario,
            state=capture.state,
        ),
        **{field: value},
    )

    with pytest.raises(
        ValueError,
        match=rf"Runtime page capture metadata does not match record: "
        rf"'{capture.capture_id}'",
    ):
        RuntimeObservation(
            generated_at="2026-07-27T00:00:00Z",
            requested_urls=(capture.url,),
            pages=(page,),
            captures=(capture,),
        )


def test_observation_rejects_capture_url_outside_requested_urls() -> None:
    capture = _capture_record(status="completed")

    with pytest.raises(
        ValueError,
        match=rf"Runtime capture URL was not requested: '{capture.url}'",
    ):
        RuntimeObservation(
            generated_at="2026-07-27T00:00:00Z",
            requested_urls=("https://example.invalid/other",),
            pages=(),
            captures=(capture,),
        )


def test_observation_from_dict_rejects_non_object_capture() -> None:
    with pytest.raises(
        TypeError,
        match="Runtime observation contains an invalid capture row",
    ):
        RuntimeObservation.from_dict({"captures": ["invalid"]})


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
        RuntimeScenarioAction.from_dict({"kind": "fill", "selector": "#nickname"})
    with pytest.raises(ValueError, match="Unknown runtime action fields: key"):
        RuntimeScenarioAction.from_dict(
            {"kind": "click", "selector": "#save", "key": "Enter"}
        )
    with pytest.raises(ValueError, match="must be one of"):
        RuntimeScenarioAction.from_dict({"kind": "wait-for-state", "state": "visible"})
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

    action_events: list[tuple[str, int]] = []
    state_locator = SimpleNamespace(
        hover=lambda **kwargs: action_events.append(("hover", kwargs["timeout"])),
        focus=lambda **kwargs: action_events.append(("focus", kwargs["timeout"])),
        evaluate=lambda _script: action_events.append(("stabilize", 0)),
    )
    for kind in ("hover", "focus"):
        parsed = RuntimeScenarioAction.from_dict(
            {"kind": kind, "selector": "#account", "timeout_ms": 250}
        )
        runtime_observer._perform_action(
            SimpleNamespace(locator=lambda _selector: state_locator),
            parsed,
        )
    assert action_events == [("hover", 250), ("focus", 250), ("stabilize", 0)]

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


def test_runtime_plan_rejects_duplicate_capture_identities() -> None:
    scenario = RuntimeScenario(
        name="duplicate",
        url="https://example.invalid",
    )

    with pytest.raises(ValueError, match="duplicate capture identity"):
        validate_runtime_observation_plan(
            (scenario, scenario),
            (VIEWPORT_REGISTRY["desktop"],),
            timeout_ms=1_000,
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
    probes = [
        viewport for viewport in discovery.viewports if viewport.kind == "boundary"
    ]
    assert {viewport.width for viewport in probes} == {499, 501, 599, 601}
    assert all(viewport.sources == ("responsive.css",) for viewport in probes)


def test_observation_status_never_promotes_partial_or_degraded_to_current() -> None:
    url = "https://example.invalid"
    viewport = VIEWPORT_REGISTRY["desktop"]
    page = RuntimePage(
        url=url,
        title="Example",
        viewport=viewport,
        elements=(),
        capture_id=runtime_capture_id("default", "ok", url, viewport),
        state="ok",
    )
    partial = RuntimeObservation(
        generated_at="2026-07-26T00:00:00Z",
        requested_urls=(url,),
        pages=(page,),
        captures=(
            _capture_record(status="completed", state="ok"),
            _capture_record(status="failed", state="failed"),
        ),
    )
    degraded = RuntimeObservation(
        generated_at="2026-07-26T00:00:00Z",
        requested_urls=(url,),
        pages=(page,),
        captures=(
            _capture_record(status="completed", readiness="degraded", state="ok"),
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


def test_runtime_payload_normalizes_computed_paint_and_round_trips_semantics() -> None:
    element = RuntimeElement.from_dict(
        {
            "kind": "text",
            "tag": "p",
            "selector": "#copy",
            "bounds": {"x": 1, "y": 2, "width": 100, "height": 20},
            "styles": {"color": "rgba(0, 0, 0, 0.5)"},
            "measurements": {
                "layoutParentSelector": "main",
                "equivalenceGroup": "main:p:",
                "equivalenceEvidence": "same-parent-role",
                "paint": {
                    "foreground": {"raw": "rgba(0, 0, 0, 0.5)"},
                    "background_layers": [
                        {
                            "selector": "main",
                            "raw": "rgb(255, 255, 255)",
                        }
                    ],
                    "unresolved": [],
                },
            },
        }
    )

    assert element.measurements["paint"]["foreground"]["rgba"] == [
        0.0,
        0.0,
        0.0,
        0.5,
    ]
    assert element.measurements["paint"]["background_layers"][0]["rgba"] == [
        1.0,
        1.0,
        1.0,
        1.0,
    ]
    page = _design_page(element, state="hover")
    observation = RuntimeObservation(
        generated_at="2026-07-26T00:00:00Z",
        requested_urls=(page.url,),
        pages=(page,),
    )
    assert RuntimeObservation.from_dict(observation.to_dict()) == observation


def test_runtime_observation_projects_nested_findings_as_json_safe_dicts() -> None:
    first_finding = Finding.create(
        detector_id="runtime-json",
        category="layout",
        severity="warning",
        confidence=0.9,
        message="Rendered layout needs review.",
        provenance="runtime",
        evidence={"metrics": {"overflow": {"pixels": 8}}},
        runtime_anchor={"selector": "#save", "viewport": "desktop"},
        suppression_key="runtime-json",
        verifier={"kind": "runtime", "detector_id": "runtime-json"},
    )
    second_finding = Finding.create(
        detector_id="runtime-json-second",
        category="typography",
        severity="error",
        confidence=0.8,
        message="Rendered typography needs review.",
        provenance="runtime",
        evidence={"metrics": {"line_height": {"pixels": 12}}},
        runtime_anchor={"selector": "#save", "viewport": "desktop"},
        suppression_key="runtime-json-second",
        verifier={"kind": "runtime", "detector_id": "runtime-json-second"},
    )
    page = _design_page(
        replace(_measured_element(), findings=(first_finding, second_finding))
    )
    observation = RuntimeObservation(
        generated_at="2026-07-30T00:00:00Z",
        requested_urls=(page.url,),
        pages=(page,),
    )

    payload = observation.to_dict()

    json.dumps(payload)
    assert RuntimeObservation.from_dict(payload) == observation
    projected = payload["pages"][0]["elements"][0]["findings"]
    assert projected == [first_finding.to_dict(), second_finding.to_dict()]


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
        capture_id=runtime_capture_id(
            scenario.name,
            "initial",
            scenario.url,
            VIEWPORT_REGISTRY["desktop"],
        ),
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
            _capture_record(status="completed"),
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
        _capture_record(status="completed"),
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
        finding["code"] for finding in frontend_map.evidence["runtime_findings"]
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
        _capture_record(status="completed", scenario="checkout", state="closed"),
        diagnostics=(first_state,),
    )
    second_capture = replace(
        _capture_record(status="completed", scenario="checkout", state="open"),
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
    page = SimpleNamespace(
        on=lambda event, callback: callbacks.__setitem__(event, callback)
    )
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
    callbacks["console"](SimpleNamespace(type="error", text=f"token={console_secret}"))
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
    capture_id = runtime_capture_id(
        scenario.name,
        "initial",
        scenario.url,
        viewport,
    )
    page_evidence = RuntimePage(
        url=scenario.url,
        title="Safe",
        viewport=viewport,
        elements=(),
        capture_id=capture_id,
        scenario=scenario.name,
        state="initial",
    )
    capture = RuntimeCaptureRecord(
        capture_id=capture_id,
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


def test_detect_runtime_findings_reports_visual_content_collisions() -> None:
    element = _measured_element(
        chartBarCount=6,
        chartBarBaselineSpread=16.7,
        textCollisionCount=1,
        maxTextCollisionArea=120.0,
        collidingTextSelector="#neighbor",
        unseparatedTextBoundaryCount=1,
        minimumAdjacentTextGap=0.0,
    )

    codes = _finding_codes(element)

    assert "runtime-chart-baseline-misalignment" in codes
    assert "runtime-text-collision" in codes
    assert "runtime-text-separation" in codes


def test_detect_runtime_findings_ignores_baseline_for_multi_flow_container() -> None:
    element = _measured_element(
        isTextFlow=False,
        fontBaselineDeviation=5.0,
    )

    assert "runtime-font-misalignment" not in _finding_codes(element)


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


def test_detect_runtime_findings_ignores_descendant_scroll_region_clipping() -> None:
    element = _measured_element(
        hasText=True,
        clientWidth=200.0,
        scrollWidth=200.0,
        clientHeight=300.0,
        scrollHeight=900.0,
        overflowX="hidden",
        overflowY="hidden",
        descendantClipped=True,
        containsScrollRegionX=False,
        containsScrollRegionY=True,
        clippedByAncestor=True,
        insideScrollRegionY=True,
        ancestorClipOverflowBlockEnd=600.0,
    )

    codes = _finding_codes(element)

    assert "runtime-text-clipped" not in codes
    assert "runtime-component-clipped" not in codes


def test_detect_runtime_findings_reports_scroll_concealed_actions() -> None:
    element = _measured_element(
        isScrollRegionX=True,
        clientWidth=324.0,
        scrollWidth=720.0,
        concealedInteractiveDescendantCount=4,
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-interactive-scroll-concealment"}
    assert findings[0].metrics == {
        "concealed_action_count": 4.0,
        "client_width_px": 324.0,
        "scroll_width_px": 720.0,
        "scroll_width_ratio": pytest.approx(2.22, abs=0.01),
    }


def test_detect_runtime_findings_reports_navigation_choice_overload() -> None:
    element = replace(
        _measured_element(
            navigationLinkCount=30,
            isScrollRegionY=True,
            clientHeight=750.0,
            scrollHeight=2130.0,
        ),
        kind="region",
        tag="nav",
        role="navigation",
        selector="#primary-navigation",
    )

    findings = detect_runtime_findings(element)

    assert _finding_codes(element) == {"runtime-navigation-choice-overload"}
    assert findings[0].metrics["link_count"] == 30.0
    assert findings[0].metrics["scroll_height_ratio"] == pytest.approx(2.84, abs=0.01)


def test_detect_runtime_findings_ignores_grouped_navigation_choices() -> None:
    element = _measured_element(
        navigationLinkCount=30,
        navigationGroupCount=3,
        isScrollRegionY=True,
        clientHeight=750.0,
        scrollHeight=2130.0,
    )

    assert "runtime-navigation-choice-overload" not in _finding_codes(element)


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
        lineHeight=15.0,
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


def _design_findings(page: RuntimePage) -> dict[str, set[str]]:
    from uidetox.design_semantics import detect_design_findings

    return {
        element.selector: {finding.code for finding in findings}
        for element, findings in zip(
            page.elements,
            detect_design_findings(page),
            strict=True,
        )
    }


def _design_element(
    selector: str,
    *,
    kind: str = "text",
    tag: str = "p",
    role: str = "",
    order: int = 0,
    x: float = 0,
    y: float = 0,
    width: float = 100,
    height: float = 20,
    styles: dict[str, str] | None = None,
    states: dict[str, object] | None = None,
    measurements: dict[str, object] | None = None,
    source_hint: str = "",
) -> RuntimeElement:
    return RuntimeElement(
        kind=kind,
        tag=tag,
        role=role,
        name=selector,
        selector=selector,
        order=order,
        bounds={"x": x, "y": y, "width": width, "height": height},
        styles={
            "fontSize": "16px",
            "fontWeight": "400",
            "lineHeight": "24px",
            **(styles or {}),
        },
        states=states or {},
        measurements=measurements or {},
        source_hint=source_hint,
    )


def _design_page(*elements: RuntimeElement, state: str = "initial") -> RuntimePage:
    return RuntimePage(
        url="https://example.invalid/dashboard",
        title="Dashboard",
        viewport=VIEWPORT_REGISTRY["desktop"],
        elements=elements,
        capture_id=f"capture-{state}",
        scenario="quality",
        state=state,
    )


def _paint(
    foreground: tuple[float, float, float, float] | None,
    *backgrounds: tuple[float, float, float, float],
    unresolved: tuple[dict[str, str], ...] = (),
) -> dict[str, object]:
    return {
        "paintedText": True,
        "paint": {
            "foreground": {
                "raw": "computed-foreground",
                "rgba": list(foreground) if foreground is not None else None,
            },
            "background_layers": [
                {
                    "selector": f"layer-{index}",
                    "raw": "computed-background",
                    "rgba": list(color),
                }
                for index, color in enumerate(backgrounds)
            ],
            "unresolved": list(unresolved),
        },
    }


def test_rendered_contrast_uses_actual_inherited_alpha_pair_and_large_text_rule() -> (
    None
):
    inherited_alpha = _design_element(
        "#body",
        measurements=_paint(
            (0.0, 0.0, 0.0, 0.5),
            (0.0, 0.0, 0.0, 0.0),
            (1.0, 1.0, 1.0, 1.0),
        ),
    )
    large = _design_element(
        "#large",
        y=40,
        styles={"fontSize": "24px"},
        measurements=_paint(
            (0.28, 0.28, 0.28, 1.0),
            (1.0, 1.0, 1.0, 1.0),
        ),
    )
    normal = replace(
        large,
        selector="#normal",
        bounds={**large.bounds, "y": 80},
        styles={**large.styles, "fontSize": "23.99px"},
    )

    findings = _design_findings(_design_page(inherited_alpha, large, normal))

    assert "runtime-contrast" in findings["#body"]
    assert "runtime-contrast" not in findings["#large"]
    assert "runtime-contrast" in findings["#normal"]


def test_rendered_contrast_marks_gradient_image_and_blend_as_unresolved_not_clean() -> (
    None
):
    element = _design_element(
        "#hero",
        measurements=_paint(
            (0.0, 0.0, 0.0, 1.0),
            unresolved=(
                {
                    "selector": "#hero",
                    "property": "background-image",
                    "value": "linear-gradient(red, blue)",
                },
                {
                    "selector": "#hero",
                    "property": "mix-blend-mode",
                    "value": "multiply",
                },
            ),
        ),
    )

    findings = _design_findings(_design_page(element))["#hero"]

    assert findings == {"runtime-color-unresolved"}


def test_contrast_ignores_empty_containers_and_non_text_gradient_surfaces() -> None:
    empty = _design_element(
        "#empty",
        kind="region",
        measurements={
            **_paint(
                (0.7, 0.7, 0.7, 1.0),
                (1.0, 1.0, 1.0, 1.0),
            ),
            "paintedText": False,
        },
    )
    gradient_surface = _design_element(
        "#gradient-surface",
        kind="region",
        y=40,
        measurements={
            **_paint(
                (0.0, 0.0, 0.0, 1.0),
                unresolved=(
                    {
                        "selector": "#gradient-surface",
                        "property": "background-image",
                        "value": "linear-gradient(red, blue)",
                    },
                ),
            ),
            "paintedText": False,
        },
    )

    findings = _design_findings(_design_page(empty, gradient_surface))

    assert findings["#empty"] == set()
    assert findings["#gradient-surface"] == set()


def test_palette_role_and_component_drift_require_evidenced_equivalence_groups() -> (
    None
):
    common = {
        "equivalenceGroup": "toolbar:button",
        "equivalenceEvidence": "source-ownership",
        "sourceOwnershipKey": "src/Toolbar.tsx",
        "paletteRole": "action",
    }
    peers = [
        _design_element(
            f"#action-{index}",
            kind="action",
            tag="button",
            role="button",
            order=index,
            x=index * 120,
            width=100,
            height=32,
            styles={"color": "rgb(0, 0, 0)", "backgroundColor": "rgb(255, 255, 255)"},
            measurements={
                **common,
                **_paint(
                    (0.0, 0.0, 0.0, 1.0),
                    (1.0, 1.0, 1.0, 1.0),
                ),
            },
            source_hint="ToolbarAction",
        )
        for index in range(2)
    ]
    peers.append(
        _design_element(
            "#action-outlier",
            kind="action",
            tag="button",
            role="button",
            order=2,
            x=240,
            width=100,
            height=44,
            styles={"color": "rgb(255, 0, 0)", "backgroundColor": "rgb(255, 255, 255)"},
            measurements={
                **common,
                **_paint(
                    (1.0, 0.0, 0.0, 1.0),
                    (1.0, 1.0, 1.0, 1.0),
                ),
            },
            source_hint="ToolbarAction",
        )
    )
    unrelated = _design_element(
        "#unrelated",
        y=80,
        styles={"color": "rgb(255, 0, 0)"},
        measurements={
            "paletteRole": "action",
            **_paint(
                (1.0, 0.0, 0.0, 1.0),
                (1.0, 1.0, 1.0, 1.0),
            ),
        },
    )

    findings = _design_findings(_design_page(*peers, unrelated))

    assert "runtime-component-drift" in findings["#action-outlier"]
    assert "runtime-palette-role-drift" not in findings["#unrelated"]


def test_palette_drift_compares_only_elements_with_the_same_semantic_role() -> None:
    common = {
        "equivalenceGroup": "toolbar:item",
        "equivalenceEvidence": "source-ownership",
        "sourceOwnershipKey": "src/Toolbar.tsx",
    }
    elements = [
        _design_element(
            f"#action-{index}",
            order=index,
            styles={
                "color": "rgb(0, 0, 0)",
                "backgroundColor": "rgb(255, 255, 255)",
            },
            measurements={**common, "paletteRole": "action"},
        )
        for index in range(2)
    ]
    elements.append(
        _design_element(
            "#surface",
            order=2,
            styles={
                "color": "rgb(255, 255, 255)",
                "backgroundColor": "rgb(0, 0, 0)",
            },
            measurements={**common, "paletteRole": "surface"},
        )
    )

    findings = _design_findings(_design_page(*elements))

    assert "runtime-palette-role-drift" not in findings["#surface"]
    assert "runtime-component-drift" not in findings["#surface"]


def test_heading_hierarchy_and_spatial_rhythm_have_boundary_safe_negatives() -> None:
    heading_one = _design_element(
        "#h1",
        tag="h1",
        styles={"fontSize": "32px", "fontWeight": "700"},
        measurements={"layoutParentSelector": "main"},
    )
    heading_two = _design_element(
        "#h2",
        tag="h2",
        order=1,
        y=60,
        styles={"fontSize": "32px", "fontWeight": "700"},
        measurements={"layoutParentSelector": "main"},
    )
    rhythm = [
        _design_element(
            f"#item-{index}",
            order=index + 2,
            y=120 + (index * 40) + (20 if index == 3 else 0),
            height=20,
            measurements={
                "layoutParentSelector": "#list",
                "equivalenceGroup": "list:item",
                "equivalenceEvidence": "same-parent-role",
            },
        )
        for index in range(4)
    ]

    findings = _design_findings(_design_page(heading_one, heading_two, *rhythm))

    assert "runtime-type-hierarchy" in findings["#h2"]
    assert "runtime-spatial-rhythm" in findings["#item-3"]

    healthy_h2 = replace(
        heading_two,
        styles={**heading_two.styles, "fontSize": "24px", "fontWeight": "600"},
    )
    healthy_rhythm = tuple(
        replace(item, bounds={**item.bounds, "y": 120 + index * 40})
        for index, item in enumerate(rhythm)
    )
    healthy = _design_findings(_design_page(heading_one, healthy_h2, *healthy_rhythm))
    assert "runtime-type-hierarchy" not in healthy["#h2"]
    assert all("runtime-spatial-rhythm" not in codes for codes in healthy.values())

    overlapping = tuple(
        replace(
            item,
            bounds={**item.bounds, "y": 120 if index < 3 else 161},
        )
        for index, item in enumerate(rhythm)
    )
    overlap_findings = _design_findings(
        _design_page(heading_one, healthy_h2, *overlapping)
    )
    assert all(
        "runtime-spatial-rhythm" not in codes for codes in overlap_findings.values()
    )


def test_occlusion_offscreen_sticky_target_and_focus_are_causal_and_state_bound() -> (
    None
):
    sticky = _design_element(
        "#sticky",
        kind="region",
        y=0,
        width=1440,
        height=60,
        styles={"position": "sticky"},
        measurements={"layoutParentSelector": "body"},
    )
    occluded = _design_element(
        "#occluded",
        kind="action",
        tag="button",
        role="button",
        y=20,
        width=80,
        height=30,
        measurements={
            "occludedBy": "#sticky",
            "occludedFraction": 0.5,
            "layoutParentSelector": "body",
        },
    )
    offscreen = _design_element(
        "#offscreen",
        x=1435,
        width=30,
        measurements={"layoutParentSelector": "body"},
    )
    small = _design_element(
        "#small",
        kind="action",
        tag="button",
        role="button",
        x=200,
        y=100,
        width=23.99,
        height=24,
        measurements={
            "layoutParentSelector": "body",
            "targetSpacing": {
                "status": "intersects",
                "center_distance_px": 24.0,
                "shape_gap_px": 0.0,
                "neighbor_shape": "circle",
                "edge_gap_px": 4.0,
                "total_targets": 2,
                "indexed_targets": 2,
                "truncated": False,
            },
        },
    )
    focused = _design_element(
        "#focused",
        kind="action",
        tag="button",
        role="button",
        x=300,
        y=100,
        width=80,
        height=30,
        states={"focused": True},
        measurements={
            "focusIndicator": {
                "visible": True,
                "changed": False,
                "distinguishable": False,
                "area": 220,
                "minimum_area": 220,
            },
            "layoutParentSelector": "body",
        },
    )

    findings = _design_findings(
        _design_page(sticky, occluded, offscreen, small, focused, state="focus")
    )

    assert findings["#occluded"] == {"runtime-sticky-occlusion"}
    assert "runtime-offscreen" in findings["#offscreen"]
    assert "runtime-target-size" in findings["#small"]
    assert "runtime-focus-visible" in findings["#focused"]
    assert "runtime-focus-appearance-guidance" not in findings["#focused"]

    boundary = replace(small, bounds={**small.bounds, "width": 24.0})
    inline = replace(
        small,
        selector="#inline",
        bounds={**small.bounds, "width": 12.0},
        measurements={**small.measurements, "targetException": "inline"},
    )
    boundary_findings = _design_findings(_design_page(boundary, inline))
    assert "runtime-target-size" not in boundary_findings["#small"]
    assert "runtime-target-size" not in boundary_findings["#inline"]


def test_target_spacing_uses_shape_intersection_and_reports_truncation() -> None:
    intersecting = _design_element(
        "#intersecting",
        kind="action",
        tag="button",
        role="button",
        width=20,
        height=20,
        measurements={
            "targetSpacing": {
                "status": "intersects",
                "nearest_selector": "#peer",
                "center_distance_px": 24.0,
                "shape_gap_px": 0.0,
                "neighbor_shape": "circle",
                "edge_gap_px": 4.0,
                "total_targets": 2,
                "indexed_targets": 2,
                "truncated": False,
            },
        },
    )
    truncated = replace(
        intersecting,
        selector="#truncated",
        bounds={**intersecting.bounds, "x": 80},
        measurements={
            "targetSpacing": {
                "status": "unresolved",
                "total_targets": 5000,
                "indexed_targets": 4096,
                "truncated": True,
            },
        },
    )

    findings = _design_findings(_design_page(intersecting, truncated))

    assert "runtime-target-size" in findings["#intersecting"]
    assert "runtime-target-spacing-unresolved" in findings["#truncated"]


def test_focus_indicator_requires_focus_specific_distinguishable_delta() -> None:
    permanent_shadow = _design_element(
        "#permanent-shadow",
        kind="action",
        tag="button",
        role="button",
        width=80,
        height=30,
        states={"focused": True},
        measurements={
            "focusIndicator": {
                "visible": True,
                "changed": False,
                "distinguishable": True,
                "area": 220,
                "minimum_area": 220,
            },
        },
    )
    transparent_shadow = replace(
        permanent_shadow,
        selector="#transparent-shadow",
        bounds={**permanent_shadow.bounds, "x": 100},
        measurements={
            "focusIndicator": {
                "visible": True,
                "changed": True,
                "distinguishable": False,
                "area": 220,
                "minimum_area": 220,
            },
        },
    )
    focus_delta = replace(
        permanent_shadow,
        selector="#focus-delta",
        bounds={**permanent_shadow.bounds, "x": 200},
        measurements={
            "focusIndicator": {
                "visible": True,
                "changed": True,
                "distinguishable": True,
                "perceptibleProperties": ["outline"],
                "area": 220,
                "minimum_area": 220,
            },
        },
    )

    findings = _design_findings(
        _design_page(
            permanent_shadow,
            transparent_shadow,
            focus_delta,
            state="focus",
        )
    )

    assert "runtime-focus-visible" in findings["#permanent-shadow"]
    assert "runtime-focus-visible" in findings["#transparent-shadow"]
    assert "runtime-focus-visible" not in findings["#focus-delta"]


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
        self.events.append(("evaluate",))
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
    assert sum(event[0] == "evaluate" for event in events) == len(viewports)
    assert all(
        event[1]["reduced_motion"] == "reduce"
        for event in events
        if event[0] == "context"
    )
    assert len(observation.pages) == 2
    assert all(
        capture.url == "http://127.0.0.1:4173" for capture in observation.captures
    )
    assert all(
        page.url == "http://127.0.0.1:4173/projects" for page in observation.pages
    )
    assert all(
        (
            page.scenario,
            page.state,
            page.viewport,
        )
        == (
            capture.scenario,
            capture.state,
            capture.viewport,
        )
        and page.url != capture.url
        for page, capture in zip(
            observation.pages,
            observation.captures,
            strict=True,
        )
    )
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


def test_default_screenshot_namer_preserves_scenario_state_identity() -> None:
    scenario = RuntimeScenario(
        name="qualification",
        url="http://127.0.0.1:4173/",
    )
    viewport = VIEWPORT_REGISTRY["desktop"]

    empty = runtime_observer._stateful_screenshot_namer(None, scenario, "empty")
    error = runtime_observer._stateful_screenshot_namer(None, scenario, "error")
    base = Path(runtime_observer._screenshot_name(scenario.url, viewport))

    assert empty is not None
    assert error is not None
    assert empty(scenario.url, viewport) == (
        f"{base.stem}-qualification-empty{base.suffix}"
    )
    assert error(scenario.url, viewport) == (
        f"{base.stem}-qualification-error{base.suffix}"
    )
    assert (
        runtime_observer._stateful_screenshot_namer(
            None,
            RuntimeScenario(name="default", url=scenario.url),
            "initial",
        )
        is None
    )


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
def test_browser_emits_actual_paint_theme_interaction_and_semantic_evidence(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "design-semantics.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  html { color-scheme: light; }
  body { margin: 0; background: rgb(255, 255, 255); }
  #alpha { color: rgb(0 0 0 / 50%); background: transparent; }
  #modern { color: oklch(70% 0.1 250); background: hsl(0 0% 100%); }
  #gradient { color: white; background: linear-gradient(red, blue); }
  #empty-gradient { width: 80px; height: 20px; background: linear-gradient(red, blue); }
  #hover:hover { color: rgb(119, 119, 119); }
  #focus { box-shadow: 0 0 0 2px rgb(0, 0, 0); }
  #focus:focus { outline: none; box-shadow: 0 0 0 2px rgb(0, 0, 0); }
  #small, #near-small { width: 20px; height: 20px; padding: 0; }
  #small { position: absolute; left: 200px; top: 200px; }
  #near-small { position: absolute; left: 218px; top: 200px; }
  #sticky { position: fixed; z-index: 5; left: 0; top: 300px; width: 180px; height: 40px; }
  #covered { position: absolute; left: 20px; top: 310px; width: 80px; height: 30px; }
  .toolbar { display: flex; gap: 8px; margin-top: 380px; }
  .tool { width: 100px; height: 32px; }
  #tool-outlier { height: 44px; color: red; }
  h1, h2 { font-size: 32px; font-weight: 700; }
  .list { display: flex; flex-direction: column; gap: 20px; }
  .list > p { height: 20px; margin: 0; }
  .list > p:last-child { margin-top: 20px; }
</style>
<main data-theme="light">
  <p id="alpha">Inherited alpha text</p>
  <p id="modern">Modern computed color</p>
  <p id="gradient">Unknown gradient backdrop</p>
  <div id="empty-gradient" role="region"></div>
  <button id="hover">Hover target</button>
  <button id="focus">Focus target</button>
  <button id="disabled" disabled>Disabled target</button>
  <input id="error" aria-invalid="true" value="bad">
  <button id="small">A</button><button id="near-small">B</button>
  <div id="sticky">Sticky overlay</div><button id="covered">Covered</button>
  <div class="toolbar">
    <button class="tool" data-uidetox-source="ToolbarAction">One</button>
    <button class="tool" data-uidetox-source="ToolbarAction">Two</button>
    <button class="tool" id="tool-outlier" data-uidetox-source="ToolbarAction">Three</button>
  </div>
  <h1>Primary</h1><h2>Secondary</h2>
  <section class="list">
    <p>First</p><p>Second</p><p>Third</p><p id="rhythm-outlier">Fourth</p>
  </section>
</main>
""".strip(),
        encoding="utf-8",
    )
    url = f"{local_http_server(tmp_path)}/{fixture.name}"
    scenario = RuntimeScenario(
        name="states",
        url=url,
        actions=(
            RuntimeScenarioAction(kind="hover", selector="#hover"),
            RuntimeScenarioAction(kind="capture", state="hover"),
            RuntimeScenarioAction(kind="focus", selector="#focus"),
            RuntimeScenarioAction(kind="capture", state="focus"),
        ),
        expected_state="focus",
        readiness=RuntimeReadinessPolicy(request_idle_ms=0, settle_ms=0),
    )

    observation = observe_frontend(
        url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        scenarios=(scenario,),
        settle_ms=0,
    )

    assert observation.status == "current", observation.errors
    assert [page.state for page in observation.pages] == ["hover", "focus"]
    assert len(observation.captures) == 2
    hover = {element.selector: element for element in observation.pages[0].elements}
    focus = {element.selector: element for element in observation.pages[1].elements}
    assert hover["#hover"].states["hovered"] is True
    assert focus["#focus"].states["focused"] is True
    assert focus["#disabled"].states["disabled"] is True
    assert focus["#error"].states["error"] is True
    assert focus["#modern"].measurements["paint"]["foreground"]["rgba"] is not None
    assert focus["#modern"].measurements["theme"] == {
        "name": "light",
        "colorScheme": "light",
    }
    assert "runtime-contrast" in {finding.code for finding in focus["#alpha"].findings}
    assert {finding.code for finding in focus["#gradient"].findings} == {
        "runtime-color-unresolved"
    }
    assert "paint" not in focus["#empty-gradient"].measurements
    assert not {
        finding.code
        for finding in focus["#empty-gradient"].findings
        if finding.code in {"runtime-contrast", "runtime-color-unresolved"}
    }
    assert "runtime-focus-visible" in {
        finding.code for finding in focus["#focus"].findings
    }
    assert "runtime-target-size" in {
        finding.code for finding in focus["#small"].findings
    }
    assert focus["#small"].measurements["targetSpacing"] == {
        "status": "intersects",
        "nearest_selector": "#near-small",
        "center_distance_px": 18,
        "shape_gap_px": -6,
        "neighbor_shape": "circle",
        "edge_gap_px": 0,
        "total_targets": 10,
        "indexed_targets": 10,
        "truncated": False,
    }
    assert "runtime-sticky-occlusion" in {
        finding.code for finding in focus["#covered"].findings
    }
    assert "runtime-component-drift" not in {
        finding.code for finding in focus["#tool-outlier"].findings
    }
    rendered_h2 = next(
        element for element in observation.pages[1].elements if element.tag == "h2"
    )
    assert "runtime-type-hierarchy" in {
        finding.code for finding in rendered_h2.findings
    }
    assert "runtime-spatial-rhythm" in {
        finding.code for finding in focus["#rhythm-outlier"].findings
    }


@pytest.mark.browser
def test_browser_target_spacing_uses_circle_against_large_target_rectangle(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "target-spacing-shapes.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  body { margin: 0; }
  button {
    box-sizing: border-box;
    position: absolute;
    margin: 0;
    padding: 0;
  }
  .small { width: 20px; height: 20px; }
  .large { width: 100px; height: 60px; }
  #near-small { left: 100px; top: 100px; }
  #near-large { left: 121px; top: 80px; }
  #clear-small { left: 100px; top: 300px; }
  #clear-large { left: 123px; top: 280px; }
  #overlap-peer-a { left: 100px; top: 500px; }
  #overlap-peer-b { left: 123px; top: 500px; }
  #tangent-peer-a { left: 100px; top: 600px; }
  #tangent-peer-b { left: 124px; top: 600px; }
  #clear-peer-a { left: 100px; top: 700px; }
  #clear-peer-b { left: 125px; top: 700px; }
</style>
<main>
  <button class="small" id="near-small" aria-label="Near small"></button>
  <button class="large" id="near-large">Near large</button>
  <button class="small" id="clear-small" aria-label="Clear small"></button>
  <button class="large" id="clear-large">Clear large</button>
  <button class="small" id="overlap-peer-a" aria-label="Overlap A"></button>
  <button class="small" id="overlap-peer-b" aria-label="Overlap B"></button>
  <button class="small" id="tangent-peer-a" aria-label="Tangent A"></button>
  <button class="small" id="tangent-peer-b" aria-label="Tangent B"></button>
  <button class="small" id="clear-peer-a" aria-label="Clear peer A"></button>
  <button class="small" id="clear-peer-b" aria-label="Clear peer B"></button>
</main>
""".strip(),
        encoding="utf-8",
    )
    url = f"{local_http_server(tmp_path)}/{fixture.name}"

    observation = observe_frontend(
        url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        settle_ms=0,
    )

    assert observation.status == "current", observation.errors
    elements = {element.selector: element for element in observation.pages[0].elements}
    assert elements["#near-small"].measurements["targetSpacing"]["status"] == (
        "intersects"
    )
    assert (
        elements["#near-small"].measurements["targetSpacing"]["nearest_selector"]
        == "#near-large"
    )
    assert "runtime-target-size" in {
        finding.code for finding in elements["#near-small"].findings
    }
    assert elements["#clear-small"].measurements["targetSpacing"]["status"] == "clear"
    assert "runtime-target-size" not in {
        finding.code for finding in elements["#clear-small"].findings
    }
    assert (
        elements["#overlap-peer-a"].measurements["targetSpacing"]["status"]
        == "intersects"
    )
    assert "runtime-target-size" in {
        finding.code for finding in elements["#overlap-peer-a"].findings
    }
    for selector in ("#tangent-peer-a", "#clear-peer-a"):
        assert elements[selector].measurements["targetSpacing"]["status"] == "clear"
        assert "runtime-target-size" not in {
            finding.code for finding in elements[selector].findings
        }


@pytest.mark.browser
def test_browser_target_spacing_bounds_pathological_spatial_cells(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "target-spacing-budget.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  body { margin: 0; }
  button { position: absolute; height: 20px; }
  #wide { left: 0; top: 20px; width: 300000px; }
  #peer { left: 20px; top: 80px; width: 20px; }
</style>
<button id="wide">Wide</button>
<button id="peer">Peer</button>
""".strip(),
        encoding="utf-8",
    )
    url = f"{local_http_server(tmp_path)}/{fixture.name}"

    observation = observe_frontend(
        url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        settle_ms=0,
    )

    assert observation.status == "current", observation.errors
    elements = {element.selector: element for element in observation.pages[0].elements}
    spacing = elements["#wide"].measurements["targetSpacing"]
    assert spacing["status"] == "clear"
    assert spacing["index"] == "bounded-linear-fallback"
    assert spacing["truncated"] is False


@pytest.mark.browser
def test_browser_target_spacing_fallback_keeps_exact_global_minimum(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "target-spacing-exact-fallback.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  body { margin: 0; }
  button { box-sizing: border-box; position: absolute; margin: 0; padding: 0; }
  .large { left: 0; top: 20px; width: 300000px; height: 30px; }
  #small-peer { left: 149994px; top: 29px; width: 12px; height: 12px; }
</style>
<button class="large" id="wide">Wide</button>
<button class="large" id="large-peer">Large peer</button>
<button id="small-peer" aria-label="Small peer"></button>
""".strip(),
        encoding="utf-8",
    )
    url = f"{local_http_server(tmp_path)}/{fixture.name}"

    observation = observe_frontend(
        url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        settle_ms=0,
    )

    assert observation.status == "current", observation.errors
    elements = {element.selector: element for element in observation.pages[0].elements}
    spacing = elements["#wide"].measurements["targetSpacing"]
    assert spacing == {
        "status": "intersects",
        "nearest_selector": "#small-peer",
        "center_distance_px": 0,
        "shape_gap_px": -24,
        "neighbor_shape": "circle",
        "edge_gap_px": 0,
        "total_targets": 3,
        "indexed_targets": 3,
        "truncated": False,
        "index": "bounded-linear-fallback",
    }


@pytest.mark.browser
def test_browser_focus_evidence_requires_perceptible_computed_delta(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "focus-perceptibility.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  body { margin: 0; background: white; }
  button {
    display: block;
    width: 120px;
    height: 36px;
    margin: 12px;
    color: black;
    background: white;
    border: 2px solid transparent;
    outline: none;
    box-shadow: none;
  }
  #background:focus { background: black; }
  #border:focus { border-color: black; }
  #faint-shadow:focus { box-shadow: 0 0 0 2px rgb(0 0 0 / 1%); }
  #outline:focus { outline: 2px solid black; }
  #visible-shadow:focus { box-shadow: 0 0 0 5px black; }
  #permanent-shadow { box-shadow: 0 0 0 2px black; }
</style>
<main>
  <button id="background">Background</button>
  <button id="border">Border</button>
  <button id="faint-shadow">Faint shadow</button>
  <button id="outline">Outline</button>
  <button id="visible-shadow">Visible shadow</button>
  <button id="permanent-shadow">Permanent shadow</button>
</main>
""".strip(),
        encoding="utf-8",
    )
    url = f"{local_http_server(tmp_path)}/{fixture.name}"
    focus_cases = (
        ("background", "#background"),
        ("border", "#border"),
        ("faint-shadow", "#faint-shadow"),
        ("outline", "#outline"),
        ("visible-shadow", "#visible-shadow"),
        ("permanent-shadow", "#permanent-shadow"),
    )
    actions = tuple(
        action
        for state, selector in focus_cases
        for action in (
            RuntimeScenarioAction(kind="focus", selector=selector),
            RuntimeScenarioAction(kind="capture", state=state),
        )
    )
    scenario = RuntimeScenario(
        name="focus-deltas",
        url=url,
        actions=actions,
        expected_state="permanent-shadow",
        readiness=RuntimeReadinessPolicy(request_idle_ms=0, settle_ms=0),
    )

    observation = observe_frontend(
        url,
        viewports=(VIEWPORT_REGISTRY["desktop"],),
        scenarios=(scenario,),
        settle_ms=0,
    )

    assert observation.status == "current", observation.errors
    pages = {page.state: page for page in observation.pages}
    expected_failures = {"faint-shadow", "permanent-shadow"}
    for state, selector in focus_cases:
        element = next(
            element for element in pages[state].elements if element.selector == selector
        )
        codes = {finding.code for finding in element.findings}
        if state in expected_failures:
            assert "runtime-focus-visible" in codes
        else:
            assert "runtime-focus-visible" not in codes
            assert element.measurements["focusIndicator"]["perceptibleProperties"]
        if state == "visible-shadow":
            assert "runtime-focus-appearance-guidance" not in codes


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
  #bar-chart { display: flex; align-items: end; gap: 8px; width: 300px; }
  .chart-column { display: grid; align-items: end; gap: 8px; height: 160px; }
  .chart-bar { width: 24px; background: black; }
  #collision-grid { display: grid; grid-template-columns: 100px 100px; }
  #overflow-text { margin: 0; white-space: nowrap; font-size: 40px; }
  #sibling-collision { position: relative; height: 32px; }
  #sibling-overflow, #sibling-peer {
    position: absolute;
    top: 0;
    white-space: nowrap;
    font-size: 20px;
  }
  #sibling-overflow { left: 0; }
  #sibling-peer { left: 32px; }
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
  <div id="bar-chart" aria-label="Fixture bar chart">
    <div class="chart-column"><span>20</span><span class="chart-bar" style="height: 20px"></span><small>A</small></div>
    <div class="chart-column"><span>60</span><span class="chart-bar" style="height: 60px"></span><small>B</small></div>
    <div class="chart-column"><span>100</span><span class="chart-bar" style="height: 100px"></span><small>C</small></div>
  </div>
  <div id="collision-grid">
    <div><h2 id="overflow-text">$123456789</h2></div>
    <div><span id="collision-peer">Next metric</span></div>
  </div>
  <div id="sibling-collision">
    <span id="sibling-overflow">Overlapping metric</span>
    <span id="sibling-peer">Direct sibling</span>
  </div>
  <label id="glued-label">Rollout<span>50%</span></label>
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
    assert "runtime-chart-baseline-misalignment" in findings_by_selector["#bar-chart"]
    assert "runtime-text-collision" in findings_by_selector["#overflow-text"]
    assert "runtime-text-collision" in findings_by_selector["#sibling-overflow"]
    assert "runtime-text-separation" in findings_by_selector["#glued-label"]
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
def test_observer_ignores_line_box_contact_and_semantic_token_fragments(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "valid-text-boundaries.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  #summary h2 { font-size: 40px; line-height: 0.9; margin: 0; }
  #summary p { font-size: 16px; line-height: 1.5; margin: 0; }
</style>
<main>
  <section id="summary">
    <h2 id="metric">58%</h2>
    <p id="detail">Across 1 active projects.</p>
  </section>
  <strong id="duration"></strong>
  <small id="status"></small>
  <label id="glued-label">Rollout<span>50%</span></label>
</main>
<script>
  document.querySelector("#duration").append(
    document.createTextNode("105"),
    document.createTextNode("m"),
  );
  document.querySelector("#status").append(
    document.createTextNode("open"),
    document.createTextNode(" · SLA "),
    document.createTextNode("15"),
    document.createTextNode("m"),
  );
</script>
""".strip(),
        encoding="utf-8",
    )

    origin = local_http_server(tmp_path)
    try:
        observation = observe_frontend(
            f"{origin}/{fixture.name}",
            viewports=(RuntimeViewport("mobile", 390, 844),),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    findings_by_selector = {
        element.selector: {finding.code for finding in element.findings}
        for element in observation.pages[0].elements
    }

    assert "runtime-text-collision" not in findings_by_selector["#metric"]
    assert "runtime-text-separation" not in findings_by_selector["#duration"]
    assert "runtime-text-separation" not in findings_by_selector["#status"]
    assert "runtime-text-separation" in findings_by_selector["#glued-label"]


@pytest.mark.browser
def test_observer_reports_navigation_overload_and_scroll_concealed_actions(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "responsive-ux-defects.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  #primary-navigation { width: 180px; height: 120px; overflow-y: auto; }
  #primary-navigation a { display: block; height: 24px; }
  #grouped-navigation { width: 180px; height: 120px; overflow-y: auto; }
  #grouped-navigation a { display: block; height: 24px; }
  #action-table { width: 300px; overflow-x: auto; }
  #action-row { width: 720px; height: 80px; position: relative; }
  #concealed-action { position: absolute; left: 640px; top: 12px; }
</style>
<nav id="primary-navigation">
  <a href="#1">One</a><a href="#2">Two</a><a href="#3">Three</a>
  <a href="#4">Four</a><a href="#5">Five</a><a href="#6">Six</a>
  <a href="#7">Seven</a><a href="#8">Eight</a><a href="#9">Nine</a>
  <a href="#10">Ten</a><a href="#11">Eleven</a><a href="#12">Twelve</a>
  <a href="#13">Thirteen</a>
</nav>
<nav id="grouped-navigation">
  <section><h2>Work</h2>
    <a href="#g1">One</a><a href="#g2">Two</a><a href="#g3">Three</a>
    <a href="#g4">Four</a><a href="#g5">Five</a><a href="#g6">Six</a>
    <a href="#g7">Seven</a>
  </section>
  <section><h2>Review</h2>
    <a href="#g8">Eight</a><a href="#g9">Nine</a><a href="#g10">Ten</a>
    <a href="#g11">Eleven</a><a href="#g12">Twelve</a><a href="#g13">Thirteen</a>
  </section>
</nav>
<main>
  <section id="action-table">
    <div id="action-row"><button id="concealed-action">Delete</button></div>
  </section>
</main>
""".strip(),
        encoding="utf-8",
    )

    origin = local_http_server(tmp_path)
    try:
        observation = observe_frontend(
            f"{origin}/{fixture.name}",
            viewports=(RuntimeViewport("mobile", 390, 844),),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    elements = {element.selector: element for element in observation.pages[0].elements}

    assert _finding_codes(elements["#primary-navigation"]) == {
        "runtime-navigation-choice-overload"
    }
    assert "runtime-navigation-choice-overload" not in _finding_codes(
        elements["#grouped-navigation"]
    )
    assert _finding_codes(elements["#action-table"]) == {
        "runtime-interactive-scroll-concealment"
    }


@pytest.mark.browser
def test_observer_excludes_framework_dev_ui(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "framework-dev-ui.html"
    fixture.write_text(
        """
<!doctype html>
<main><button id="app-action">App action</button></main>
<nextjs-portal><button id="next-dev-action">Next dev action</button></nextjs-portal>
<div id="vue-inspector-container">
  <button id="vue-inspector-action">Vue inspector action</button>
</div>
<div id="__vue-devtools-container__">
  <button id="vue-devtools-action">Vue DevTools action</button>
</div>
<astro-dev-toolbar>
  <button id="astro-dev-action">Astro dev action</button>
</astro-dev-toolbar>
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

    selectors = {element.selector for element in observation.pages[0].elements}
    assert "#app-action" in selectors
    assert selectors.isdisjoint(
        {
            "#next-dev-action",
            "#vue-inspector-action",
            "#vue-devtools-action",
            "#astro-dev-action",
        }
    )


@pytest.mark.browser
def test_observer_excludes_descendants_of_closed_details(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "details-visibility.html"
    fixture.write_text(
        """
<!doctype html>
<details>
  <summary id="closed-summary">Closed navigation</summary>
  <a id="closed-link" href="/hidden">Hidden destination</a>
</details>
<details open>
  <summary id="open-summary">Open navigation</summary>
  <a id="open-link" href="/visible">Visible destination</a>
</details>
<div style="width: 200px; overflow-x: auto">
  <button id="wide" style="width: 1800px">Wide scroll content</button>
</div>
<button id="mixed" style="line-height: 24px">
  <span style="font-family: monospace">NO</span> Northstar Operator
</button>
<h2 id="wrapped" style="width: 200px; font-size: 24px; line-height: 1.1">
  Normal wrapped heading remains readable
</h2>
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

    selectors = {element.selector for element in observation.pages[0].elements}
    assert {"#closed-summary", "#open-summary", "#open-link"} <= selectors
    assert "#closed-link" not in selectors
    by_selector = {
        element.selector: {finding.code for finding in element.findings}
        for element in observation.pages[0].elements
    }
    assert "runtime-offscreen" not in by_selector["#wide"]
    assert "runtime-line-spacing" not in by_selector["#mixed"]
    assert "runtime-line-spacing" not in by_selector["#wrapped"]


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
    assert any(
        element.selector == "#modal" for element in observation.pages[0].elements
    )
    assert {diagnostic.code for diagnostic in observation.captures[0].diagnostics} >= {
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
    elements = {element.selector: element for element in observation.pages[0].elements}

    assert elements["#tail-aligned"].measurements["layoutPeerCount"] == 25
    assert "runtime-layout-misalignment" not in _finding_codes(
        elements["#tail-aligned"]
    )
    assert elements["#tail-outlier"].measurements["layoutPeerCount"] == 25
    assert "runtime-layout-misalignment" in _finding_codes(elements["#tail-outlier"])


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
    assert "runtime-text-clipped" in _finding_codes(elements["#localized-action"])


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
        capture.scenario: capture.readiness.status for capture in observation.captures
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


def test_dialog_modality_requires_top_layer_and_contained_focus() -> None:
    proper = _design_element(
        "#proper-dialog",
        kind="region",
        tag="dialog",
        measurements={
            "openDialog": True,
            "dialogModalIntent": True,
            "modalDialog": True,
            "dialogFocusContained": True,
        },
    )
    broken = _design_element(
        "#broken-dialog",
        kind="region",
        tag="dialog",
        measurements={
            "openDialog": True,
            "dialogModalIntent": True,
            "modalDialog": False,
            "dialogFocusContained": False,
        },
    )

    findings = _design_findings(_design_page(proper, broken))

    assert "runtime-dialog-modality" not in findings["#proper-dialog"]
    assert findings["#broken-dialog"] == {"runtime-dialog-modality"}


def test_parent_owned_surface_does_not_require_child_padding() -> None:
    element = _measured_element(
        hasText=True,
        isVisualContainer=True,
        isBoxControl=False,
        isTextFlow=True,
        hasVisualSurface=False,
        textInsetInlineStart=0,
        textInsetInlineEnd=0,
        textInsetBlockStart=0,
        textInsetBlockEnd=0,
        paddingInlineStart=0,
        paddingInlineEnd=0,
        paddingBlockStart=0,
        paddingBlockEnd=0,
    )

    assert "runtime-horizontal-padding" not in _finding_codes(element)
    assert "runtime-vertical-padding" not in _finding_codes(element)


def test_pathological_text_wrap_reports_narrow_reading_column() -> None:
    element = replace(
        _measured_element(
            hasText=True,
            paintedText=True,
            lineCount=12,
            fontSize=16,
            lineHeight=24,
        ),
        tag="strong",
        name="Acme Global Transformation Holdings and Associated Operating Companies",
    )

    finding = next(
        item
        for item in detect_runtime_findings(element)
        if item.code == "runtime-pathological-text-wrap"
    )

    assert finding.metrics == {
        "character_count": 63,
        "line_count": 12,
        "characters_per_line": 5.25,
    }


def test_modal_obscured_background_has_no_runtime_layout_findings() -> None:
    element = _measured_element(
        obscuredByModal=True,
        isScrollRegionX=True,
        concealedInteractiveDescendantCount=4,
        clientWidth=320,
        scrollWidth=720,
    )

    assert detect_runtime_findings(element) == ()


@pytest.mark.browser
def test_browser_modal_context_suppresses_backdrop_noise_and_flags_fake_modal(
    tmp_path: Path,
    local_http_server,
) -> None:
    proper = tmp_path / "proper-modal.html"
    proper.write_text(
        """
<!doctype html>
<style>
  #behind { position: fixed; left: calc(50% - 60px); top: calc(50% - 20px); }
  #proper-dialog { width: 240px; height: 120px; }
</style>
<button id="behind">Background action</button>
<dialog id="proper-dialog" class="modal-card" aria-labelledby="proper-title">
  <h1 id="proper-title">Create project</h1>
  <button id="inside" autofocus>Continue</button>
</dialog>
<script>document.querySelector('#proper-dialog').showModal()</script>
""".strip(),
        encoding="utf-8",
    )
    broken = tmp_path / "broken-modal.html"
    broken.write_text(
        """
<!doctype html>
<button id="trigger" autofocus>Invite member</button>
<dialog id="broken-dialog" class="modal-card" open aria-labelledby="broken-title">
  <h1 id="broken-title">Invite team member</h1>
  <input aria-label="Email address">
</dialog>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    try:
        observation = observe_frontend(
            (f"{origin}/{proper.name}", f"{origin}/{broken.name}"),
            viewports=(RuntimeViewport("mobile", 390, 844),),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    pages = {Path(page.url).name: page for page in observation.pages}
    proper_elements = {
        element.selector: element for element in pages[proper.name].elements
    }
    broken_elements = {
        element.selector: element for element in pages[broken.name].elements
    }

    def finding_codes(element: RuntimeElement) -> set[str]:
        return {finding.code for finding in element.findings}

    assert "runtime-element-occluded" not in finding_codes(proper_elements["#behind"])
    assert "runtime-dialog-modality" not in finding_codes(
        proper_elements["#proper-dialog"]
    )
    assert finding_codes(broken_elements["#broken-dialog"]) == {
        "runtime-dialog-modality"
    }


@pytest.mark.browser
def test_browser_ignores_content_outside_visible_scrollport(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "scrollport.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  #scrollport { width: 240px; height: 40px; overflow-y: auto; }
  #spacer { height: 80px; }
  #hidden-link { display: block; }
  #underlay { position: fixed; top: 88px; left: 8px; }
</style>
<div id="scrollport">
  <div id="spacer"></div>
  <a id="hidden-link" href="#hidden">Hidden navigation item</a>
</div>
<p id="underlay">Visible page content</p>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    try:
        observation = observe_frontend(
            f"{origin}/{fixture.name}",
            viewports=(RuntimeViewport("mobile", 390, 844),),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    selectors = {element.selector for element in observation.pages[0].elements}

    assert "#hidden-link" not in selectors


@pytest.mark.browser
def test_browser_reports_pathologically_short_text_lines(
    tmp_path: Path,
    local_http_server,
) -> None:
    fixture = tmp_path / "pathological-wrap.html"
    fixture.write_text(
        """
<!doctype html>
<style>
  strong { display: block; line-height: 24px; overflow-wrap: anywhere; }
  #narrow { width: 78px; }
  #healthy { width: 360px; }
</style>
<strong id="narrow">Acme Global Transformation Holdings and Associated Operating Companies</strong>
<strong id="healthy">Acme Global Transformation Holdings and Associated Operating Companies</strong>
""".strip(),
        encoding="utf-8",
    )
    origin = local_http_server(tmp_path)

    try:
        observation = observe_frontend(
            f"{origin}/{fixture.name}",
            viewports=(RuntimeViewport("mobile", 390, 844),),
            settle_ms=0,
        )
    except RuntimeError as exc:
        _skip_missing_browser(exc)
        raise

    elements = {element.selector: element for element in observation.pages[0].elements}
    codes = {
        selector: {finding.code for finding in element.findings}
        for selector, element in elements.items()
    }

    assert "runtime-pathological-text-wrap" in codes["#narrow"]
    assert "runtime-pathological-text-wrap" not in codes["#healthy"]
