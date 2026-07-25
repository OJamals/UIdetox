from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

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
    if set(manifest) != {"schema_version", "fixture_root", "cases"}:
        errors.append("manifest keys must be schema_version, fixture_root, and cases")
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


def _load_manifest(path: Path = MANIFEST_PATH) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_calibration_manifest_is_valid() -> None:
    validate_manifest(_load_manifest())


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
