from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from uidetox.runtime_scenarios import RuntimeCoverage

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "benchmarks" / "runtime_observer.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("runtime_benchmark", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sample(
    version: str,
    *,
    wall_seconds: float,
    evaluator_seconds: float,
    result_digest: str = "same",
) -> dict[str, object]:
    return {
        "version": version,
        "fixture": "generic",
        "wall_seconds": wall_seconds,
        "evaluator_seconds": evaluator_seconds,
        "evaluate_count": 1,
        "result_digest": result_digest,
        "coverage": {
            "total": 6_401,
            "candidates": 6_401,
            "eligible": 6_401,
            "emitted": 3_000,
            "budget": 3_000,
            "truncated": True,
        },
        "element_count": 3_000,
        "status": "degraded",
        "import": {
            "safe_path": True,
            "expected_root": f"/tmp/{version}",
            "package_file": f"/tmp/{version}/uidetox/__init__.py",
            "module_files": {
                "uidetox": f"/tmp/{version}/uidetox/__init__.py",
                "uidetox.runtime_observer": (
                    f"/tmp/{version}/uidetox/runtime_observer.py"
                ),
            },
            "sys_path": [f"/tmp/{version}", "/venv/site-packages"],
            "cwd": "/tmp/neutral",
        },
    }


def test_worker_command_uses_safe_path_and_exact_roots(tmp_path):
    harness = _load_harness()
    command = harness.worker_command(
        Path("/venv/bin/python"),
        HARNESS,
        expected_root=tmp_path / "base",
        forbidden_root=tmp_path / "current",
        fixture="generic",
        node_count=3_200,
    )

    assert command[:3] == [
        "/venv/bin/python",
        "-P",
        str(HARNESS.resolve()),
    ]
    assert command[3:] == [
        "--worker",
        "--expected-root",
        str((tmp_path / "base").resolve()),
        "--forbidden-root",
        str((tmp_path / "current").resolve()),
        "--fixture",
        "generic",
        "--node-count",
        "3200",
    ]


def test_worker_environment_has_one_explicit_code_root(tmp_path, monkeypatch):
    harness = _load_harness()
    monkeypatch.setenv("PYTHONPATH", "/shadow")
    monkeypatch.setenv("PYTHONHOME", "/also-shadow")

    environment = harness.worker_environment(tmp_path / "base")

    assert environment["PYTHONPATH"] == str((tmp_path / "base").resolve())
    assert "PYTHONHOME" not in environment
    assert environment["PYTHONSAFEPATH"] == "1"


def test_import_provenance_rejects_shadowing_and_unsafe_paths(tmp_path):
    harness = _load_harness()
    base = (tmp_path / "base").resolve()
    current = (tmp_path / "current").resolve()
    neutral = (tmp_path / "neutral").resolve()
    valid = _sample("base", wall_seconds=1.0, evaluator_seconds=0.8)["import"]
    assert isinstance(valid, dict)
    valid.update(
        {
            "expected_root": str(base),
            "package_file": str(base / "uidetox" / "__init__.py"),
            "module_files": {
                "uidetox": str(base / "uidetox" / "__init__.py"),
                "uidetox.runtime_observer": str(
                    base / "uidetox" / "runtime_observer.py"
                ),
            },
            "sys_path": [str(base), "/venv/site-packages"],
            "cwd": str(neutral),
        }
    )

    harness.validate_import_provenance(valid, base, current)

    for field, value, message in (
        ("safe_path", False, "safe-path"),
        ("package_file", str(current / "uidetox" / "__init__.py"), "outside"),
        (
            "module_files",
            {"uidetox.runtime_observer": str(current / "runtime_observer.py")},
            "module.*outside",
        ),
        ("sys_path", [str(base), str(current)], "forbidden"),
        ("sys_path", [str(base), str(neutral)], "working directory"),
    ):
        invalid = dict(valid)
        invalid[field] = value
        with pytest.raises(ValueError, match=message):
            harness.validate_import_provenance(invalid, base, current)


def test_alternating_pairs_reverse_order_and_keep_every_sample():
    harness = _load_harness()

    assert list(harness.alternating_versions(5)) == [
        (1, ("base", "current")),
        (2, ("current", "base")),
        (3, ("base", "current")),
        (4, ("current", "base")),
        (5, ("base", "current")),
    ]


def test_fixture_html_includes_pathological_geometry_without_more_nodes():
    harness = _load_harness()

    generic = harness.fixture_html("generic", 3_200)
    controls = harness.fixture_html("controls", 3_200)
    geometry = harness.fixture_html("geometry", 3_200)

    assert generic.count("Item ") == 3_200
    assert controls.count("<button") == 3_200
    assert geometry.count('class="geometry-node"') == 3_200
    assert "100000000px" in geometry


def test_sample_validation_requires_exact_results_one_evaluate_and_dom_budget(
    tmp_path,
):
    harness = _load_harness()
    base_root = (tmp_path / "base").resolve()
    current_root = (tmp_path / "current").resolve()
    samples = [
        _sample("base", wall_seconds=1.0, evaluator_seconds=0.8),
        _sample("current", wall_seconds=1.01, evaluator_seconds=0.81),
    ]
    for sample, root, forbidden in (
        (samples[0], base_root, current_root),
        (samples[1], current_root, base_root),
    ):
        package_import = sample["import"]
        assert isinstance(package_import, dict)
        package_import.update(
            {
                "expected_root": str(root),
                "package_file": str(root / "uidetox" / "__init__.py"),
                "module_files": {
                    "uidetox": str(root / "uidetox" / "__init__.py"),
                    "uidetox.runtime_observer": str(
                        root / "uidetox" / "runtime_observer.py"
                    ),
                },
                "sys_path": [str(root), "/venv/site-packages"],
            }
        )
        harness.validate_sample(sample, root, forbidden, expected_emitted=3_000)

    for key, value, message in (
        ("evaluate_count", 2, "one page.evaluate"),
        ("result_digest", "different", "canonical result"),
        ("element_count", 2_999, "element count"),
    ):
        invalid = dict(samples[1])
        invalid[key] = value
        with pytest.raises(ValueError, match=message):
            harness.validate_pair(samples[0], invalid, expected_emitted=3_000)

    invalid_coverage = json.loads(json.dumps(samples[1]))
    invalid_coverage["coverage"]["budget"] = 2_999
    with pytest.raises(ValueError, match="DOM budget"):
        harness.validate_pair(
            samples[0],
            invalid_coverage,
            expected_emitted=3_000,
        )


def test_summary_keeps_distributions_and_reports_separate_gate_margins():
    harness = _load_harness()
    samples = [
        _sample("base", wall_seconds=1.00, evaluator_seconds=0.80),
        _sample("current", wall_seconds=1.04, evaluator_seconds=0.82),
        _sample("base", wall_seconds=1.02, evaluator_seconds=0.81),
        _sample("current", wall_seconds=1.06, evaluator_seconds=0.83),
        _sample("base", wall_seconds=0.98, evaluator_seconds=0.79),
        _sample("current", wall_seconds=1.02, evaluator_seconds=0.81),
    ]

    summary = harness.summarize_fixture(samples, gate_percent=10.0)

    assert summary["sample_count"] == {"base": 3, "current": 3}
    assert summary["wall_seconds"]["base"]["samples"] == [1.0, 1.02, 0.98]
    assert summary["wall_seconds"]["current"]["samples"] == [1.04, 1.06, 1.02]
    assert summary["wall_seconds"]["delta_percent"] == pytest.approx(4.0)
    assert summary["wall_seconds"]["gate_margin_percent"] == pytest.approx(6.0)
    assert summary["evaluator_seconds"]["delta_percent"] == pytest.approx(2.5)
    assert summary["evaluator_seconds"]["gate_margin_percent"] == pytest.approx(7.5)
    assert summary["passed"] is True


def test_summary_rejects_either_distribution_above_regression_gate():
    harness = _load_harness()
    samples = [
        _sample("base", wall_seconds=1.0, evaluator_seconds=0.8),
        _sample("current", wall_seconds=1.11, evaluator_seconds=0.8),
    ]

    summary = harness.summarize_fixture(samples, gate_percent=10.0)

    assert summary["wall_seconds"]["delta_percent"] == pytest.approx(11.0)
    assert summary["wall_seconds"]["gate_margin_percent"] == pytest.approx(-1.0)
    assert summary["passed"] is False


def test_json_report_preserves_measured_order_and_is_deterministic(tmp_path):
    harness = _load_harness()
    report = {
        "schema_version": 1,
        "samples": [
            {"sequence": 1, "version": "base"},
            {"sequence": 2, "version": "current"},
        ],
        "summary": {"passed": True},
    }
    output = tmp_path / "report.json"

    harness.write_report(report, output)

    assert output.read_text(encoding="utf-8") == (
        json.dumps(report, indent=2, sort_keys=True) + os.linesep
    )


def test_cli_parser_shares_node_count_between_controller_and_worker():
    harness = _load_harness()

    args = harness._parser().parse_args(
        [
            "--worker",
            "--expected-root",
            "/tmp/base",
            "--forbidden-root",
            "/tmp/current",
            "--fixture",
            "generic",
            "--node-count",
            "17",
        ]
    )

    assert args.node_count == 17


def test_worker_main_normalizes_single_fixture(monkeypatch):
    harness = _load_harness()
    seen = {}

    def fake_worker(args):
        seen["fixture"] = args.fixture
        return 0

    monkeypatch.setattr(harness, "_run_worker", fake_worker)

    assert (
        harness.main(
            [
                "--worker",
                "--expected-root",
                "/tmp/base",
                "--forbidden-root",
                "/tmp/current",
                "--fixture",
                "generic",
            ]
        )
        == 0
    )
    assert seen["fixture"] == "generic"


def test_runtime_coverage_serializes_without_parallel_model():
    harness = _load_harness()
    coverage = RuntimeCoverage(
        total=6_401,
        candidates=6_400,
        eligible=6_399,
        emitted=3_000,
        budget=3_000,
        truncated=True,
    )

    assert harness.coverage_payload(coverage) == {
        "total": 6_401,
        "candidates": 6_400,
        "eligible": 6_399,
        "emitted": 3_000,
        "budget": 3_000,
        "truncated": True,
    }


def test_canonical_result_removes_only_run_identity_and_timing():
    harness = _load_harness()
    origin = "http://127.0.0.1:49123"
    payload = MappingProxyType(
        {
            "generated_at": "now",
            "capture_id": "derived-from-port",
            "requested_urls": (f"{origin}/index.html",),
            "pages": (
                {
                    "url": f"{origin}/index.html",
                    "elements": ({"selector": "main > div", "width": 24},),
                },
            ),
        }
    )

    assert harness._canonicalize(payload, origin=origin) == {
        "requested_urls": ["http://benchmark.invalid/index.html"],
        "pages": [
            {
                "url": "http://benchmark.invalid/index.html",
                "elements": [{"selector": "main > div", "width": 24}],
            }
        ],
    }


def test_controller_preserves_virtualenv_interpreter_path(tmp_path, monkeypatch):
    harness = _load_harness()
    interpreter = tmp_path / ".venv" / "bin" / "python"
    monkeypatch.setattr(harness.sys, "executable", str(interpreter))

    assert harness.controller_python() == interpreter.absolute()


def test_controller_requires_frozen_base_ref():
    harness = _load_harness()

    with pytest.raises(ValueError, match="frozen --base-ref"):
        harness._run_controller(SimpleNamespace(base_ref=None))
