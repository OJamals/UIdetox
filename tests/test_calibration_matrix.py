from __future__ import annotations

import json
import hashlib
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from uidetox.analyzer import analyze_file
from uidetox.rule_registry import RULE_REGISTRY


CALIBRATION_ROOT = Path(__file__).parent / "calibration"
MANIFEST_PATH = CALIBRATION_ROOT / "manifest.json"
_STATUSES = {"positive", "negative", "degraded", "unsupported"}
_SEVERITIES = {"info", "warning", "error"}
_DETECTORS = {"static-analyzer", "frontend-map", "project-map", "runtime-layout"}
_REQUIRED_CASE_KEYS = {
    "id",
    "fixture",
    "framework",
    "language",
    "capability",
    "detector",
    "status",
    "expected_anchors",
    "severity",
    "rationale",
}


@dataclass(frozen=True)
class CalibrationReport:
    totals: Mapping[str, int]
    by_capability_framework: Mapping[str, Mapping[str, int]]
    failures: tuple[str, ...]


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_manifest(
    manifest: Mapping[str, object], calibration_root: Path = CALIBRATION_ROOT
) -> None:
    errors: list[str] = []
    if set(manifest) != {"schema_version", "fixture_root", "catalog", "cases"}:
        errors.append(
            "manifest keys must be schema_version, fixture_root, catalog, and cases"
        )
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    fixture_root_value = manifest.get("fixture_root")
    if not isinstance(fixture_root_value, str):
        errors.append("fixture_root must be a string")
        fixture_root = calibration_root
    else:
        fixture_root = calibration_root / fixture_root_value
        if not _inside(calibration_root, fixture_root):
            errors.append("fixture_root escapes calibration root")

    cases = manifest.get("cases")
    if not isinstance(cases, list):
        errors.append("cases must be a list")
        cases = []

    seen: set[str] = set()
    for index, raw_case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(raw_case, dict):
            errors.append(f"{label} must be an object")
            continue
        case = raw_case
        if set(case) - (_REQUIRED_CASE_KEYS | {"route", "state", "viewport", "rule_id"}):
            errors.append(f"{label} has unknown keys")
        missing = _REQUIRED_CASE_KEYS - set(case)
        if missing:
            errors.append(f"{label} missing keys: {', '.join(sorted(missing))}")
            continue

        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{label}.id must be a non-empty string")
        elif case_id in seen:
            errors.append(f"duplicate case id: {case_id}")
        else:
            seen.add(case_id)

        detector = case["detector"]
        if detector not in _DETECTORS:
            errors.append(f"{label} unknown detector: {detector}")
        rule_id = case.get("rule_id")
        if detector == "static-analyzer":
            if rule_id not in RULE_REGISTRY:
                errors.append(f"{label} unknown rule_id: {rule_id}")
        elif rule_id is not None:
            errors.append(f"{label}.rule_id is only valid for static-analyzer")

        status = case["status"]
        if status not in _STATUSES:
            errors.append(f"{label} unknown status: {status}")
        if case["severity"] not in _SEVERITIES:
            errors.append(f"{label} unknown severity: {case['severity']}")
        rationale = case["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(f"{label}.rationale must be non-empty")

        fixture = case["fixture"]
        if not isinstance(fixture, str):
            errors.append(f"{label}.fixture must be a string")
        else:
            fixture_path = fixture_root / fixture
            if not _inside(fixture_root, fixture_path):
                errors.append(f"{label}.fixture escapes fixture root")
            elif not fixture_path.is_file():
                errors.append(f"{label} missing fixture: {fixture}")

        anchors = case["expected_anchors"]
        if not isinstance(anchors, list):
            errors.append(f"{label}.expected_anchors must be a list")
            continue
        for anchor_index, anchor in enumerate(anchors):
            anchor_label = f"{label}.expected_anchors[{anchor_index}]"
            if not isinstance(anchor, dict) or set(anchor) != {"path", "contains"}:
                errors.append(f"{anchor_label} must contain path and contains")
                continue
            anchor_path = fixture_root / str(anchor["path"])
            if not _inside(fixture_root, anchor_path):
                errors.append(f"{anchor_label}.path escapes fixture root")
            elif not anchor_path.is_file():
                errors.append(f"{anchor_label} missing path: {anchor['path']}")
            elif str(anchor["contains"]) not in anchor_path.read_text(encoding="utf-8"):
                errors.append(f"{anchor_label}.contains not found")

    if errors:
        raise ValueError("Invalid calibration manifest:\n- " + "\n- ".join(errors))


def _catalog_fingerprint(rule_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(rule_ids).encode()).hexdigest()


def _qualification_partition(
    manifest: Mapping[str, object],
    registry: Mapping[str, object],
) -> tuple[set[str], list[str]]:
    cases = manifest.get("cases")
    assert isinstance(cases, list)
    statuses: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        if (
            case["detector"] == "static-analyzer"
            and case["status"] in {"positive", "negative"}
        ):
            statuses[str(case["rule_id"])].add(str(case["status"]))
    objective = {
        rule_id
        for rule_id in registry
        if statuses[rule_id] == {"positive", "negative"}
    }
    manual = [rule_id for rule_id in registry if rule_id not in objective]
    return objective, manual


def validate_catalog_contract(
    manifest: Mapping[str, object],
    registry: Mapping[str, object] = RULE_REGISTRY,
) -> None:
    catalog = manifest.get("catalog")
    if not isinstance(catalog, dict):
        raise ValueError("Invalid calibration catalog: catalog must be an object")
    if set(catalog) != {
        "rule_count",
        "fingerprint",
        "manual_rule_count",
        "manual_rule_fingerprint",
        "manual_rationale",
    }:
        raise ValueError("Invalid calibration catalog: unknown or missing keys")
    rule_ids = list(registry)
    _objective, manual_rule_ids = _qualification_partition(manifest, registry)
    errors = []
    if catalog["rule_count"] != len(rule_ids):
        errors.append(
            f"rule_count mismatch: expected {len(rule_ids)}, "
            f"found {catalog['rule_count']}"
        )
    if catalog["fingerprint"] != _catalog_fingerprint(rule_ids):
        errors.append("catalog fingerprint mismatch")
    if catalog["manual_rule_count"] != len(manual_rule_ids):
        errors.append(
            f"manual rule count mismatch: expected {len(manual_rule_ids)}, "
            f"found {catalog['manual_rule_count']}"
        )
    if catalog["manual_rule_fingerprint"] != _catalog_fingerprint(manual_rule_ids):
        errors.append("manual rule fingerprint mismatch")
    rationale = catalog["manual_rationale"]
    if not isinstance(rationale, str) or "plans/015-" not in rationale:
        errors.append("manual rationale must link plan 015")
    if errors:
        raise ValueError("Invalid calibration catalog:\n- " + "\n- ".join(errors))


def build_rule_qualifications(
    manifest: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    objective_rules, _manual_rules = _qualification_partition(manifest, RULE_REGISTRY)
    catalog = manifest["catalog"]
    assert isinstance(catalog, dict)
    qualifications = {}
    for rule_id, spec in RULE_REGISTRY.items():
        objective = rule_id in objective_rules
        qualifications[rule_id] = {
            "status": "objective" if objective else "manual",
            "owner_category": spec.category,
            "supported_extensions": spec.extensions,
            "occurrence_policy": (
                "detector-defined"
                if spec.analyzer_rule.get("_custom_check")
                else "first-per-file"
            ),
            "confidence": "high" if objective else "manual",
            "rationale": (
                "Paired positive and negative corpus cases."
                if objective
                else catalog["manual_rationale"]
            ),
        }
    return qualifications


def evaluate_cases(
    manifest: Mapping[str, object],
    *,
    analyzer: Callable[[Path], list[dict[str, Any]]] = analyze_file,
) -> CalibrationReport:
    cases = manifest["cases"]
    fixture_root = CALIBRATION_ROOT / str(manifest["fixture_root"])
    assert isinstance(cases, list)
    totals: Counter[str] = Counter()
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    failures: list[str] = []
    static_by_fixture: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for case in cases:
        status = str(case["status"])
        key = f"{case['capability']}::{case['framework']}"
        if status in {"degraded", "unsupported"}:
            totals[status] += 1
            grouped[key][status] += 1
        elif case["detector"] == "static-analyzer":
            static_by_fixture[str(case["fixture"])].append(case)

    for fixture, fixture_cases in static_by_fixture.items():
        actual = {str(issue["id"]) for issue in analyzer(fixture_root / fixture)}
        positive = {
            str(case["rule_id"])
            for case in fixture_cases
            if case["status"] == "positive"
        }
        negative = {
            str(case["rule_id"])
            for case in fixture_cases
            if case["status"] == "negative"
        }
        first = fixture_cases[0]
        key = f"{first['capability']}::{first['framework']}"

        for rule_id in sorted(positive & actual):
            totals["tp"] += 1
            grouped[key]["tp"] += 1
        for rule_id in sorted(positive - actual):
            totals["fn"] += 1
            grouped[key]["fn"] += 1
            failures.append(f"FN {fixture}: expected {rule_id}")
        false_positives = (actual - positive) | (actual & negative)
        for rule_id in sorted(false_positives):
            totals["fp"] += 1
            grouped[key]["fp"] += 1
            failures.append(f"FP {fixture}: unexpected {rule_id}")

    return CalibrationReport(
        totals=dict(totals),
        by_capability_framework={
            key: dict(counts) for key, counts in sorted(grouped.items())
        },
        failures=tuple(failures),
    )


def _load_manifest(path: Path = MANIFEST_PATH) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_calibration_manifest_is_valid() -> None:
    manifest = _load_manifest()
    validate_manifest(manifest)
    validate_catalog_contract(manifest)


def test_calibration_manifest_seeds_required_framework_and_boundary_shapes() -> None:
    cases = _load_manifest()["cases"]
    assert isinstance(cases, list)
    frameworks = {case["framework"] for case in cases}
    capabilities = {case["capability"] for case in cases}

    assert {"react-next", "vue", "svelte", "astro"} <= frameworks
    assert {
        "api-client",
        "css",
        "tailwind",
        "theme-colors",
        "python-backend",
        "typescript-backend",
        "openapi",
        "orm-schema",
    } <= capabilities


def test_calibration_signal_has_no_unclassified_fp_or_fn() -> None:
    report = evaluate_cases(_load_manifest())

    assert report.totals["tp"] > 0
    assert report.totals.get("fp", 0) == 0, report.failures
    assert report.totals.get("fn", 0) == 0, report.failures
    assert report.totals["degraded"] > 0
    assert report.totals["unsupported"] > 0
    assert report.by_capability_framework


def test_calibration_reports_one_injected_unexpected_result_as_one_fp() -> None:
    def inject(path: Path) -> list[dict[str, Any]]:
        issues = analyze_file(path)
        if path.name == "negative.tsx":
            return [*issues, {"id": "COLOR_BLACK_SLOP"}]
        return issues

    report = evaluate_cases(_load_manifest(), analyzer=inject)

    assert report.totals["fp"] == 1
    assert sum("COLOR_BLACK_SLOP" in failure for failure in report.failures) == 1


def test_calibration_reports_one_removed_expected_result_as_one_fn() -> None:
    def remove(path: Path) -> list[dict[str, Any]]:
        issues = analyze_file(path)
        if path.as_posix().endswith("react-next/positive.tsx"):
            return [issue for issue in issues if issue["id"] != "LOREM_IPSUM_SLOP"]
        return issues

    report = evaluate_cases(_load_manifest(), analyzer=remove)

    assert report.totals["fn"] == 1
    assert sum("LOREM_IPSUM_SLOP" in failure for failure in report.failures) == 1


def test_live_catalog_has_explicit_objective_or_manual_qualification() -> None:
    qualifications = build_rule_qualifications(_load_manifest())

    assert set(qualifications) == set(RULE_REGISTRY)
    assert all(
        record["status"] in {"objective", "manual"}
        and record["owner_category"]
        and record["supported_extensions"]
        and record["occurrence_policy"] in {"first-per-file", "detector-defined"}
        and record["confidence"] in {"high", "manual"}
        and record["rationale"]
        for record in qualifications.values()
    )
    assert any(record["status"] == "objective" for record in qualifications.values())
    assert any(record["status"] == "manual" for record in qualifications.values())


def test_new_catalog_rule_without_manifest_update_fails_collection_contract() -> None:
    expanded = dict(RULE_REGISTRY)
    expanded["UNQUALIFIED_NEW_RULE"] = next(iter(RULE_REGISTRY.values()))

    with pytest.raises(ValueError, match="rule_count mismatch|fingerprint mismatch"):
        validate_catalog_contract(_load_manifest(), expanded)


def test_new_rule_still_fails_after_global_catalog_fingerprint_refresh() -> None:
    expanded = dict(RULE_REGISTRY)
    expanded["UNQUALIFIED_NEW_RULE"] = next(iter(RULE_REGISTRY.values()))
    manifest = _load_manifest()
    catalog = manifest["catalog"]
    assert isinstance(catalog, dict)
    catalog["rule_count"] = len(expanded)
    catalog["fingerprint"] = _catalog_fingerprint(list(expanded))

    with pytest.raises(ValueError, match="manual rule"):
        validate_catalog_contract(manifest, expanded)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda cases: cases.append(dict(cases[0])), "duplicate case id"),
        (
            lambda cases: cases[0].__setitem__("fixture", "missing.tsx"),
            "missing fixture",
        ),
        (
            lambda cases: cases[0].__setitem__("detector", "unknown"),
            "unknown detector",
        ),
        (
            lambda cases: cases[0]["expected_anchors"][0].__setitem__(
                "path", "../../outside.tsx"
            ),
            "escapes fixture root",
        ),
    ),
)
def test_calibration_manifest_rejects_malformed_cases_readably(
    mutation, message: str
) -> None:
    manifest = _load_manifest()
    cases = manifest["cases"]
    assert isinstance(cases, list)
    mutation(cases)

    with pytest.raises(ValueError, match=message):
        validate_manifest(manifest)
