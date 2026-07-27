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
PROMPT = ROOT / "benchmarks" / "handoff-qualification-prompt.md"


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


def test_controller_prompt_preserves_exact_agent_report_and_runtime_contract() -> None:
    prompt = PROMPT.read_text(encoding="utf-8")

    assert _sha256(PROMPT) == (
        "a013bad95f9e961577768271c88a748112c3eb59af9624e40d56c109ac7bf266"
    )
    for required in (
        "blocked-stale-source",
        "completed-with-runtime-capture-blocker",
        "checked_source_paths",
        "source_freshness_status",
        "preserved_contracts",
        "named_source_anchors",
        '"source"',
        "feasibility_blockers",
        "runtime_unknowns",
        "output_file_count",
        "output_bytes",
        "inline `data:` favicon",
        "zero console errors or warnings",
        "at most one localhost launch/browser-capture attempt",
    ):
        assert required in prompt

    assert (
        prompt.index("`mobile`") < prompt.index("`tablet`") < prompt.index("`desktop`")
    )
