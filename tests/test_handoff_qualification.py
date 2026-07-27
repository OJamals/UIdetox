from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "benchmarks" / "handoff_qualification.py"
SCHEMA = ROOT / "benchmarks" / "handoff-qualification.schema.json"
V1_REPORT_SCHEMA = "uidetox.disposable-agent-attempt.v1"


def _load_harness():
    spec = importlib.util.spec_from_file_location("handoff_qualification", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png(path: Path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def _fixture(tmp_path: Path) -> dict[str, Path]:
    source_hashes = {
        "src/App.tsx": "a" * 64,
        "backend/app.py": "b" * 64,
    }
    source_manifest = {
        "files": {"src/App.tsx": source_hashes["src/App.tsx"]},
        "project_files": {"backend/app.py": source_hashes["backend/app.py"]},
        "target": ".",
    }
    viewport_discovery = {
        "boundaries": [],
        "total_boundaries": 0,
        "truncated": False,
        "viewports": [
            {
                "boundary_px": None,
                "height": 844,
                "kind": "registry",
                "name": "mobile",
                "relation": "",
                "sources": [],
                "width": 390,
            }
        ],
    }
    redesigns = {
        "schema_version": 3,
        "unknowns": ["Triggered states remain unknown."],
        "proposals": [
            {
                "id": "REDESIGN-01",
                "preserved_contracts": [
                    "Route remains reachable: /",
                    "Data contract remains functional: /api/projects",
                ],
                "source_targets": ["src/App.tsx", "backend/app.py"],
                "feasibility_blockers": ["Resolve contract lineage: /api/projects."],
                "evidence_freshness": {
                    "source": {"status": "current", "manifest": source_manifest},
                    "runtime": {
                        "status": "current",
                        "generated_at": "2026-07-27T00:00:00Z",
                        "urls": ["http://127.0.0.1:4173"],
                        "viewports": ["mobile"],
                        "viewport_discovery": viewport_discovery,
                        "screenshots": ["runtime/mobile.png"],
                        "stale_reason": None,
                    },
                },
            }
        ],
    }
    redesign_path = tmp_path / "redesigns.json"
    redesign_path.write_text(json.dumps(redesigns), encoding="utf-8")

    evidence = [
        "BEGIN_UIDETOX_EVIDENCE",
        "Source targets:",
        "- src/App.tsx",
        "- backend/app.py",
        "Preserved contracts:",
        "- Route remains reachable: /",
        "- Data contract remains functional: /api/projects",
        "Evidence freshness:",
        "- Source: current",
        "- Source manifest: "
        + json.dumps(
            source_manifest,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "- Runtime: current",
        '- Runtime URLs: ["http://127.0.0.1:4173"]',
        '- Runtime viewports: ["mobile"]',
        "- Runtime viewport discovery: "
        + json.dumps(
            viewport_discovery,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        '- Runtime screenshots: ["runtime/mobile.png"]',
        "Feasibility blockers and unknowns:",
        "- Resolve contract lineage: /api/projects.",
        "Runtime unknowns:",
        "- Triggered states remain unknown.",
        "END_UIDETOX_EVIDENCE",
    ]
    brief_path = tmp_path / "brief.md"
    brief_path.write_text("\n".join(evidence) + "\n", encoding="utf-8")

    screenshot_path = tmp_path / "prototype" / "screenshots" / "mobile.png"
    _png(screenshot_path, 390, 1027)

    report = {
        "status": "completed",
        "brief_sha256": _sha256(brief_path),
        "implementation_attempt_count": 1,
        "retry_count": 0,
        "checked_source_paths": [
            {
                "relative_path": path,
                "expected_hash": digest,
                "actual_hash": digest,
                "freshness_status": "fresh",
            }
            for path, digest in source_hashes.items()
        ],
        "source_freshness_status": "fresh",
        "preserved_contracts": [
            {
                "identity": identity,
                "disposition": "preserved",
                "evidence": "prototype/src/main.tsx",
            }
            for identity in redesigns["proposals"][0]["preserved_contracts"]
        ],
        "named_source_anchors": [
            {
                "source": source,
                "existence_status": "exists",
                "preservation_status": "unchanged",
            }
            for source in redesigns["proposals"][0]["source_targets"]
        ],
        "feasibility_blockers": [
            {
                "identity": "Resolve contract lineage: /api/projects.",
                "disposition": "acknowledged and unresolved",
            }
        ],
        "runtime_unknowns": [
            {
                "identity": "Triggered states remain unknown.",
                "disposition": "remains unknown",
            }
        ],
        "viewports": [
            {
                "name": "mobile",
                "width": 390,
                "height": 844,
                "prototype_screenshot": "prototype/screenshots/mobile.png",
            }
        ],
        "output_file_count": 4,
        "output_bytes": 4096,
        "decision": "pursue",
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    attempt = {
        "schema_version": 1,
        "name": "final",
        "brief": "brief.md",
        "agent_report": "report.json",
        "metrics": {
            "wall_seconds": 12.5,
            "input_tokens": 1000,
            "cached_input_tokens": 800,
            "cache_write_input_tokens": 100,
            "output_tokens": 200,
            "reasoning_output_tokens": 50,
        },
        "runtime": {
            "http_status": 200,
            "console_errors_or_warnings": 0,
            "horizontal_overflow_viewports": 0,
            "screenshots": [
                {
                    "name": "mobile",
                    "path": "prototype/screenshots/mobile.png",
                    "viewport_width": 390,
                    "viewport_height": 844,
                    "png_width": 390,
                    "png_height": 1027,
                    "sha256": _sha256(screenshot_path),
                }
            ],
        },
    }
    attempt_path = tmp_path / "final-attempt.json"
    attempt_path.write_text(json.dumps(attempt), encoding="utf-8")
    return {
        "redesigns": redesign_path,
        "brief": brief_path,
        "report": report_path,
        "attempt": attempt_path,
        "screenshot": screenshot_path,
    }


def _v1_fixture(tmp_path: Path) -> dict[str, Path]:
    fixture = _fixture(tmp_path)
    redesigns = json.loads(fixture["redesigns"].read_text(encoding="utf-8"))
    runtime = redesigns["proposals"][0]["evidence_freshness"]["runtime"]
    viewport_specs = [
        ("mobile", 390, 844),
        ("tablet", 768, 1024),
        ("desktop", 1440, 900),
    ]
    viewports = [
        {
            "boundary_px": None,
            "height": height,
            "kind": "registry",
            "name": name,
            "relation": "",
            "sources": [],
            "width": width,
        }
        for name, width, height in viewport_specs
    ]
    capture_specs = [
        ("qualification-authenticated", "authenticated", viewports[0]),
        ("qualification-triggered", "triggered", viewports[1]),
        ("qualification-empty", "empty", viewports[2]),
        ("qualification-error", "error", viewports[2]),
    ]
    captures = [
        {
            "capture_id": capture_id,
            "completed_at": "2026-07-27T00:00:01Z",
            "coverage": {
                "budget": 10,
                "candidates": 1,
                "eligible": 1,
                "emitted": 1,
                "total": 1,
                "truncated": False,
            },
            "diagnostics": [],
            "readiness": {
                "detail": "",
                "duration_ms": 1,
                "status": "current",
                "strategy": "request-idle",
            },
            "scenario": "qualification",
            "started_at": "2026-07-27T00:00:00Z",
            "state": state,
            "status": "completed",
            "url": "http://127.0.0.1:4173/",
            "viewport": viewport,
        }
        for capture_id, state, viewport in capture_specs
    ]
    discovery = {
        "boundaries": [],
        "total_boundaries": 0,
        "truncated": False,
        "viewports": viewports,
    }
    runtime.update(
        {
            "runtime_capture_matrix": captures,
            "runtime_coverage": {
                "candidates": 4,
                "completed": 4,
                "eligible": 4,
                "emitted": 4,
                "failed": 0,
                "requested": 4,
                "total": 4,
                "truncated": 0,
            },
            "runtime_diagnostics": [],
            "runtime_semantic_coverage": {
                "elements": 4,
                "equivalence_grouped": 0,
                "paint_resolved": 4,
                "paint_unobserved": 0,
                "paint_unresolved": 0,
            },
            "screenshots": [
                f"runtime/{name}.png" for name, _width, _height in viewport_specs
            ],
            "viewport_discovery": discovery,
            "viewports": [name for name, _width, _height in viewport_specs],
        }
    )
    fixture["redesigns"].write_text(json.dumps(redesigns), encoding="utf-8")

    def compact(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    brief = fixture["brief"].read_text(encoding="utf-8")
    brief = brief.replace(
        compact(
            {
                "boundaries": [],
                "total_boundaries": 0,
                "truncated": False,
                "viewports": [viewports[0]],
            }
        ),
        compact(discovery),
    )
    brief = brief.replace('["mobile"]', compact(runtime["viewports"]))
    brief = brief.replace(
        '["runtime/mobile.png"]',
        compact(runtime["screenshots"]),
    )
    brief = brief.replace(
        "END_UIDETOX_EVIDENCE",
        "- Runtime capture matrix: " + compact(captures) + "\nEND_UIDETOX_EVIDENCE",
    )
    brief += (
        "\n## Disposable-agent qualification contract (v1)\n\n"
        f"Report schema: `{V1_REPORT_SCHEMA}`.\n"
    )
    fixture["brief"].write_text(brief, encoding="utf-8")

    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    for row, path in zip(
        report["checked_source_paths"],
        redesigns["proposals"][0]["evidence_freshness"]["source"]["manifest"]["files"]
        | redesigns["proposals"][0]["evidence_freshness"]["source"]["manifest"][
            "project_files"
        ],
        strict=True,
    ):
        row["group"] = "files" if path == "src/App.tsx" else "project_files"
    report.update(
        {
            "schema_version": V1_REPORT_SCHEMA,
            "brief_sha256": _sha256(fixture["brief"]),
            "runtime_state_handoffs": [
                {
                    "capture_id": capture["capture_id"],
                    "scenario": capture["scenario"],
                    "state": capture["state"],
                    "url": capture["url"],
                    "viewport": capture["viewport"],
                    "disposition": "captured by isolated controller",
                    "evidence": f"runtime state {capture['capture_id']}",
                }
                for capture in captures
            ],
            "commands": [
                {
                    "command": "verify source manifest",
                    "exit_code": 0,
                    "wall_time_ms": 100,
                    "evidence": "2/2 source paths fresh",
                }
            ],
            "failures": [
                {
                    "stage": "runtime-capture",
                    "command": "playwright chromium.launch({ headless: true })",
                    "exit_code": 1,
                    "wall_time_ms": 96,
                    "exact_error": "browser executable unavailable",
                    "disposition": "bounded runtime-capture blocker",
                }
            ],
            "recoveries": [],
            "status": "completed-with-runtime-capture-blocker",
            "decision": "pursue",
            "decision_evidence": "state-specific prototype passed",
            "runnable_prototype_path": "prototype/index.html",
            "launch_command": "python -m http.server",
            "canonical_url": "http://127.0.0.1:4173/",
            "runtime_acceptance": {
                "status": "blocked",
                "http_200": "unknown: browser launch failed",
                "console_errors_or_warnings": "unknown: browser launch failed",
                "failed_or_error_resource_requests": ("unknown: browser launch failed"),
                "horizontal_overflow": "unknown: browser launch failed",
                "controller_capture_required": True,
            },
        }
    )
    report["named_source_anchors"] = [
        {
            **row,
            "preservation_status": "preserved unchanged",
        }
        for row in report["named_source_anchors"]
    ]
    report["viewports"] = [
        {
            "name": name,
            "width": width,
            "height": height,
            "reference_screenshot": f"runtime/{name}.png",
            "prototype_screenshot": f"prototype/screenshots/{name}.png",
        }
        for name, width, height in viewport_specs
    ]
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")

    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    normalized_screenshots = []
    for name, width, height in viewport_specs:
        screenshot = tmp_path / "prototype" / "screenshots" / f"{name}.png"
        _png(screenshot, width, height)
        normalized_screenshots.append(
            {
                "name": name,
                "path": f"prototype/screenshots/{name}.png",
                "viewport_width": width,
                "viewport_height": height,
                "png_width": width,
                "png_height": height,
                "sha256": _sha256(screenshot),
            }
        )

    nodes = []
    for capture_id, state, viewport in capture_specs:
        screenshot = tmp_path / "runtime-state-screenshots" / f"{capture_id}.png"
        _png(screenshot, viewport["width"], viewport["height"])
        nodes.append(
            {
                "id": f"runtime_page:{capture_id}",
                "kind": "runtime_page",
                "name": "http://127.0.0.1:4173/",
                "file": "",
                "line": 0,
                "metadata": {
                    "capture_id": capture_id,
                    "scenario": "qualification",
                    "state": state,
                    "runtime_url": "http://127.0.0.1:4173/",
                    "viewport": {
                        "name": viewport["name"],
                        "width": viewport["width"],
                        "height": viewport["height"],
                    },
                    "screenshot": str(screenshot),
                },
            }
        )
    frontend_map = {
        "schema_version": 3,
        "root": str(tmp_path),
        "target": ".",
        "nodes": nodes,
        "edges": [],
        "contracts": [],
        "project_map": {},
        "evidence": {
            "runtime_capture_matrix": captures,
            "runtime_diagnostics": [],
            "runtime_errors": [],
            "runtime_status": "current",
        },
        "fingerprint": "f" * 64,
        "generated_at": "2026-07-27T00:00:01Z",
    }
    frontend_map_path = tmp_path / "runtime-frontend-map.json"
    frontend_map_path.write_text(json.dumps(frontend_map), encoding="utf-8")
    attempt["runtime"].update(
        {
            "failed_or_error_resources": 0,
            "frontend_map": frontend_map_path.name,
            "frontend_map_sha256": _sha256(frontend_map_path),
            "screenshots": normalized_screenshots,
        }
    )
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")
    fixture["frontend_map"] = frontend_map_path
    return fixture


def test_schema_declares_strict_tool_agnostic_attempt_contract() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["required"] == [
        "schema_version",
        "name",
        "brief",
        "agent_report",
        "metrics",
    ]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["runtime"]["additionalProperties"] is False
    runtime = schema["properties"]["runtime"]
    assert runtime["dependentRequired"] == {
        "frontend_map": ["frontend_map_sha256", "failed_or_error_resources"],
        "frontend_map_sha256": ["frontend_map", "failed_or_error_resources"],
    }
    assert set(runtime["properties"]) >= {
        "failed_or_error_resources",
        "frontend_map",
        "frontend_map_sha256",
    }


def test_v1_report_requires_exact_ordered_runtime_state_handoffs(tmp_path) -> None:
    harness = _load_harness()
    fixture = _v1_fixture(tmp_path)

    passed = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    attempt = passed["attempts"][0]
    assert attempt["passed"] is True
    handoffs = attempt["identities"]["runtime_state_handoffs"]
    assert handoffs["actual"] == 4
    assert handoffs["expected"] == 4
    assert handoffs["verified"] == 4

    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report["runtime_state_handoffs"].reverse()
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    reordered = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )
    assert "runtime_state_handoffs:reordered" in reordered["attempts"][0]["issues"]

    report["runtime_state_handoffs"].pop()
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    missing = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )
    assert "runtime_state_handoffs:missing" in missing["attempts"][0]["issues"]


def test_v1_report_rejects_schema_field_and_nested_row_drift(tmp_path) -> None:
    harness = _load_harness()
    fixture = _v1_fixture(tmp_path)
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report["schema_version"] = "uidetox.disposable-agent-attempt.v2"
    report["unexpected"] = True
    report["preserved_contracts"][0]["unexpected"] = True
    report["commands"][0]["exit_code"] = True
    report["failures"][0]["unexpected"] = True
    report["runtime_acceptance"]["controller_capture_required"] = False
    report["viewports"][0]["reference_screenshot"] = "wrong.png"
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    assert set(result["attempts"][0]["issues"]) >= {
        "report:v1-fields",
        "report:v1-schema",
        "preserved_contracts:row-fields",
        "commands:invalid",
        "failures:row-fields",
        "runtime_acceptance:invalid",
        "viewports:handoff",
    }


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        ("acceptance-status", "runtime_acceptance:status"),
        ("boolean-zero", "runtime_acceptance:invalid"),
        ("canonical-url", "decision:canonical-url"),
        ("prototype-traversal", "decision:prototype-path"),
        ("screenshot-traversal", "viewports:prototype-path"),
    ],
)
def test_v1_report_rejects_cross_field_and_path_drift(
    tmp_path,
    mutation,
    issue,
) -> None:
    harness = _load_harness()
    fixture = _v1_fixture(tmp_path)
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    if mutation == "acceptance-status":
        report["status"] = "completed"
    elif mutation == "boolean-zero":
        report["status"] = "completed"
        report["runtime_acceptance"] = {
            "status": "passed",
            "http_200": True,
            "console_errors_or_warnings": False,
            "failed_or_error_resource_requests": 0,
            "horizontal_overflow": 0,
            "controller_capture_required": False,
        }
    elif mutation == "canonical-url":
        report["canonical_url"] = "http://127.0.0.1:9999/"
    elif mutation == "prototype-traversal":
        report["runnable_prototype_path"] = "../prototype/index.html"
    else:
        report["viewports"][0]["prototype_screenshot"] = "../mobile.png"
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    assert issue in result["attempts"][0]["issues"]


def test_v1_stale_report_requires_exact_schema_and_fields(tmp_path) -> None:
    harness = _load_harness()
    fixture = _v1_fixture(tmp_path)
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    attempt.pop("runtime")
    attempt["name"] = "stale"
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    source_paths = [row["relative_path"] for row in report["checked_source_paths"]]
    stale_report = {
        "schema_version": V1_REPORT_SCHEMA,
        "status": "blocked-stale-source",
        "brief_sha256": report["brief_sha256"],
        "checked_source_paths": source_paths,
        "checked_source_path_count": len(source_paths),
        "fresh_source_path_count": len(source_paths) - 1,
        "stale_source_path_count": 1,
        "mismatches": [
            {
                "manifest_group": "files",
                "path": "src/App.tsx",
                "expected_sha256": "a" * 64,
                "actual_sha256": "c" * 64,
                "freshness_status": "mismatched",
            }
        ],
        "implementation_attempt_count": 0,
        "retry_count": 0,
        "prototype_file_count": 0,
        "prototype_output_bytes": 0,
    }
    fixture["report"].write_text(json.dumps(stale_report), encoding="utf-8")

    passed = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )
    assert passed["attempts"][0]["passed"] is True

    stale_report["schema_version"] = "uidetox.disposable-agent-attempt.v2"
    stale_report["unexpected"] = True
    fixture["report"].write_text(json.dumps(stale_report), encoding="utf-8")
    failed = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )
    assert set(failed["attempts"][0]["issues"]) >= {
        "report:v1-fields",
        "report:v1-schema",
    }


@pytest.mark.parametrize(
    ("mutation", "issue"),
    [
        ("hash", "runtime:frontend-map-hash"),
        ("capture", "runtime:frontend-map-captures:missing"),
        ("page", "runtime:state-page"),
        ("screenshot", "runtime:state-screenshot"),
        ("root", "runtime:frontend-map-root"),
    ],
)
def test_runtime_frontend_map_rejects_state_evidence_drift(
    tmp_path,
    mutation,
    issue,
) -> None:
    harness = _load_harness()
    fixture = _v1_fixture(tmp_path)
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    frontend_map = json.loads(fixture["frontend_map"].read_text(encoding="utf-8"))
    if mutation == "hash":
        attempt["runtime"]["frontend_map_sha256"] = "0" * 64
    elif mutation == "capture":
        frontend_map["evidence"]["runtime_capture_matrix"].pop()
    elif mutation == "page":
        frontend_map["nodes"].pop()
    elif mutation == "root":
        frontend_map["root"] = "/"
    else:
        Path(frontend_map["nodes"][0]["metadata"]["screenshot"]).unlink()
    fixture["frontend_map"].write_text(json.dumps(frontend_map), encoding="utf-8")
    if mutation != "hash":
        attempt["runtime"]["frontend_map_sha256"] = _sha256(fixture["frontend_map"])
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    assert issue in result["attempts"][0]["issues"]


def test_completed_attempt_exactly_matches_canonical_handoff(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    assert result["gates"] == {
        "all_attempts_passed": True,
        "completed_attempts": 1,
        "passed": True,
        "stale_stops": 0,
    }
    attempt = result["attempts"][0]
    assert attempt["passed"] is True
    assert attempt["issues"] == []
    assert attempt["source"]["verified"] == 2
    assert attempt["identities"]["preserved_contracts"]["verified"] == 2
    assert attempt["identities"]["named_source_anchors"]["verified"] == 2
    assert attempt["identities"]["feasibility_blockers"]["verified"] == 1
    assert attempt["identities"]["runtime_unknowns"]["verified"] == 1
    assert attempt["viewports"]["verified"] == 1
    assert attempt["runtime"]["passed"] is True
    assert attempt["artifacts"] == {
        "agent_report_sha256": _sha256(fixture["report"]),
        "brief_sha256": _sha256(fixture["brief"]),
    }
    assert attempt["measurements"] == {
        "contract_preservation_accuracy": 1.0,
        "implementation_attempt_count": 1,
        "output_bytes": 4096,
        "output_file_count": 4,
        "retry_count": 0,
    }


def test_completed_attempt_allows_named_blocker_and_external_manifest(
    tmp_path,
) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    brief = fixture["brief"].read_text(encoding="utf-8")
    fixture["brief"].write_text(
        "Treat `BEGIN_UIDETOX_EVIDENCE` and "
        "`END_UIDETOX_EVIDENCE` as boundary markers.\n"
        + brief.replace(
            "END_UIDETOX_EVIDENCE",
            "- Route remains reachable: /\nEND_UIDETOX_EVIDENCE",
        ),
        encoding="utf-8",
    )
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report["status"] = "completed-with-runtime-capture-blocker"
    report["brief_sha256"] = _sha256(fixture["brief"])
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    attempt["brief"] = str(fixture["brief"])
    attempt["agent_report"] = str(fixture["report"])
    external = tmp_path / "manifests" / "attempt.json"
    external.parent.mkdir()
    external.write_text(json.dumps(attempt), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [external],
    )

    assert result["gates"]["passed"] is True
    assert result["attempts"][0]["issues"] == []


def test_untrusted_evidence_cannot_enable_v1_report_validation(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    brief = (
        fixture["brief"]
        .read_text(encoding="utf-8")
        .replace(
            "END_UIDETOX_EVIDENCE",
            f"Report schema: `{V1_REPORT_SCHEMA}`.\nEND_UIDETOX_EVIDENCE",
        )
    )
    fixture["brief"].write_text(brief, encoding="utf-8")
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report["brief_sha256"] = _sha256(fixture["brief"])
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    assert result["attempts"][0]["passed"] is True
    assert result["attempts"][0]["issues"] == []


def test_exact_accounting_rejects_missing_reordered_and_empty_dispositions(
    tmp_path,
) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report["preserved_contracts"].reverse()
    report["preserved_contracts"][0]["disposition"] = ""
    report["preserved_contracts"][0]["evidence"] = ""
    report["named_source_anchors"].pop()
    report["named_source_anchors"][0]["existence_status"] = "missing"
    report["named_source_anchors"][0]["preservation_status"] = ""
    report["feasibility_blockers"][0]["disposition"] = ""
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    attempt = result["attempts"][0]
    assert attempt["passed"] is False
    assert "preserved_contracts:reordered" in attempt["issues"]
    assert "preserved_contracts:invalid-disposition" in attempt["issues"]
    assert "preserved_contracts:invalid-evidence" in attempt["issues"]
    assert "named_source_anchors:missing" in attempt["issues"]
    assert "named_source_anchors:invalid-existence-status" in attempt["issues"]
    assert "named_source_anchors:invalid-preservation-status" in attempt["issues"]
    assert "feasibility_blockers:invalid-disposition" in attempt["issues"]
    assert result["gates"]["passed"] is False


def test_contract_accuracy_requires_preserved_disposition_and_evidence(
    tmp_path,
) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report["preserved_contracts"][0]["disposition"] = ""
    report["preserved_contracts"][0]["evidence"] = ""
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    attempt = result["attempts"][0]
    assert attempt["identities"]["preserved_contracts"]["verified"] == 1
    assert attempt["measurements"]["contract_preservation_accuracy"] == 0.5


def test_stale_source_stop_requires_exact_mismatch_and_zero_writes(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report = {
        "status": "blocked-stale-source",
        "brief_sha256": report["brief_sha256"],
        "implementation_attempt_count": 0,
        "retry_count": 0,
        "prototype_file_count": 0,
        "prototype_output_bytes": 0,
        "checked_source_paths": ["src/App.tsx", "backend/app.py"],
        "checked_source_path_count": 2,
        "fresh_source_path_count": 1,
        "stale_source_path_count": 1,
        "mismatches": [
            {
                "manifest_group": "files",
                "path": "src/App.tsx",
                "expected_sha256": "a" * 64,
                "actual_sha256": "c" * 64,
                "freshness_status": "mismatched",
            }
        ],
        "decision": "reject",
    }
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    attempt.pop("runtime")
    attempt["name"] = "stale"
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    stale = result["attempts"][0]
    assert stale["kind"] == "stale-stop"
    assert stale["passed"] is True
    assert stale["source"]["verified"] == 1
    assert stale["source"]["mismatched"] == ["src/App.tsx"]
    assert result["gates"]["stale_stops"] == 1
    assert result["gates"]["passed"] is False

    report["prototype_file_count"] = 1
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    failed = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )
    assert "stale-stop:prototype-output" in failed["attempts"][0]["issues"]

    report["prototype_file_count"] = 0
    report["mismatches"][0]["manifest_group"] = "project_files"
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    wrong_group = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )
    assert "stale-stop:mismatch" in wrong_group["attempts"][0]["issues"]


def test_stale_stop_then_completed_attempt_records_recovery(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    completed_report = tmp_path / "completed-report.json"
    completed_report.write_bytes(fixture["report"].read_bytes())
    completed_attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    completed_attempt["agent_report"] = completed_report.name
    completed_attempt_path = tmp_path / "completed-attempt.json"
    completed_attempt_path.write_text(
        json.dumps(completed_attempt),
        encoding="utf-8",
    )

    report = json.loads(fixture["report"].read_text(encoding="utf-8"))
    report = {
        "status": "blocked-stale-source",
        "brief_sha256": report["brief_sha256"],
        "implementation_attempt_count": 0,
        "retry_count": 0,
        "prototype_file_count": 0,
        "prototype_output_bytes": 0,
        "checked_source_paths": ["src/App.tsx", "backend/app.py"],
        "checked_source_path_count": 2,
        "fresh_source_path_count": 1,
        "stale_source_path_count": 1,
        "mismatches": [
            {
                "manifest_group": "files",
                "path": "src/App.tsx",
                "expected_sha256": "a" * 64,
                "actual_sha256": "c" * 64,
                "freshness_status": "mismatched",
            }
        ],
        "decision": "reject",
    }
    fixture["report"].write_text(json.dumps(report), encoding="utf-8")
    stale_attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    stale_attempt.pop("runtime")
    stale_attempt["name"] = "stale"
    fixture["attempt"].write_text(json.dumps(stale_attempt), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"], completed_attempt_path],
    )

    assert result["gates"]["passed"] is True
    assert result["recovery"] == {
        "passed_completed_attempts": 1,
        "passed_stale_stops": 1,
        "stale_stop_followed_by_completed": True,
    }
    assert result["distributions"]["retry_count"]["samples"] == [0, 0]
    assert result["distributions"]["output_bytes"]["samples"] == [0, 4096]


def test_runtime_rejects_wrong_png_dimensions_and_hash(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    screenshot = attempt["runtime"]["screenshots"][0]
    screenshot["png_height"] = 900
    screenshot["sha256"] = "0" * 64
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    issues = result["attempts"][0]["issues"]
    assert "runtime:png-dimensions" in issues
    assert "runtime:screenshot-hash" in issues


def test_runtime_hash_and_dimensions_share_one_screenshot_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    original = Path.read_bytes
    screenshot_reads = 0

    def count_screenshot_reads(path: Path) -> bytes:
        nonlocal screenshot_reads
        if path == fixture["screenshot"]:
            screenshot_reads += 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", count_screenshot_reads)

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"]],
    )

    assert result["gates"]["passed"] is True
    assert screenshot_reads == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("wall_seconds", True),
        ("wall_seconds", float("inf")),
        ("input_tokens", -1),
    ],
)
def test_manifest_rejects_invalid_metrics(tmp_path, field, value) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    attempt["metrics"][field] = value
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")

    with pytest.raises(harness.QualificationError, match=field):
        harness.qualify(
            fixture["redesigns"],
            "REDESIGN-01",
            [fixture["attempt"]],
        )


def test_manifest_rejects_boolean_schema_version(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    attempt["schema_version"] = True
    fixture["attempt"].write_text(json.dumps(attempt), encoding="utf-8")

    with pytest.raises(harness.QualificationError, match="schema_version"):
        harness.qualify(
            fixture["redesigns"],
            "REDESIGN-01",
            [fixture["attempt"]],
        )


def test_duplicate_attempt_names_are_rejected(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)

    with pytest.raises(harness.QualificationError, match="duplicate attempt name"):
        harness.qualify(
            fixture["redesigns"],
            "REDESIGN-01",
            [fixture["attempt"], fixture["attempt"]],
        )


def test_report_is_deterministic_and_preserves_attempt_order(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    second_attempt = json.loads(fixture["attempt"].read_text(encoding="utf-8"))
    second_attempt["name"] = "second"
    second_attempt["metrics"]["wall_seconds"] = 17.5
    second_path = tmp_path / "second-attempt.json"
    second_path.write_text(json.dumps(second_attempt), encoding="utf-8")

    result = harness.qualify(
        fixture["redesigns"],
        "REDESIGN-01",
        [fixture["attempt"], second_path],
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    harness.write_report(result, first)
    harness.write_report(result, second)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == (
        json.dumps(result, indent=2, sort_keys=True) + os.linesep
    )
    assert [attempt["name"] for attempt in result["attempts"]] == [
        "final",
        "second",
    ]
    assert result["distributions"]["wall_seconds"] == {
        "max": 17.5,
        "mean": 15.0,
        "median": 15.0,
        "min": 12.5,
        "p90": 17.0,
        "samples": [12.5, 17.5],
    }
    assert result["distributions"]["retry_count"]["samples"] == [0, 0]
    assert result["distributions"]["output_bytes"]["samples"] == [4096, 4096]
    assert result["distributions"]["contract_preservation_accuracy"]["samples"] == [
        1.0,
        1.0,
    ]
    assert result["recovery"] == {
        "passed_completed_attempts": 2,
        "passed_stale_stops": 0,
        "stale_stop_followed_by_completed": False,
    }


def test_distribution_removes_binary_float_noise() -> None:
    harness = _load_harness()

    distribution = harness._distribution([148011, 972854])

    assert distribution["p90"] == 890369.7
    assert distribution["samples"] == [148011, 972854]


def test_cli_writes_report_and_returns_gate_status(tmp_path) -> None:
    harness = _load_harness()
    fixture = _fixture(tmp_path)
    output = tmp_path / "qualification.json"

    exit_code = harness.main(
        [
            "--redesigns",
            str(fixture["redesigns"]),
            "--proposal-id",
            "REDESIGN-01",
            "--attempt",
            str(fixture["attempt"]),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["gates"]["passed"] is True
