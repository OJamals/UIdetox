"""Deterministic qualification of disposable-agent handoff attempts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from collections.abc import Sequence
from pathlib import Path
from statistics import mean, median
from typing import Any

SCHEMA_VERSION = 1
METRIC_FIELDS = (
    "wall_seconds",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
REPORT_METRIC_FIELDS = (
    "retry_count",
    "implementation_attempt_count",
    "output_file_count",
    "output_bytes",
)
_ATTEMPT_FIELDS = {
    "schema_version",
    "name",
    "brief",
    "agent_report",
    "metrics",
    "runtime",
}
_RUNTIME_FIELDS = {
    "http_status",
    "console_errors_or_warnings",
    "horizontal_overflow_viewports",
    "screenshots",
}
_SCREENSHOT_FIELDS = {
    "name",
    "path",
    "viewport_width",
    "viewport_height",
    "png_width",
    "png_height",
    "sha256",
}
_SHA256_LENGTH = 64


class QualificationError(ValueError):
    """Raised when qualification input cannot be evaluated safely."""


def _load_json_artifact(
    path: Path,
    label: str,
) -> tuple[dict[str, Any], str]:
    content = _read_bytes(path, label)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"{label}: cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"{label}: expected JSON object")
    return value, _sha256(content)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    value, _digest = _load_json_artifact(path, label)
    return value


def _resolve(base: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise QualificationError(f"{field}: expected non-empty path")
    path = Path(value)
    return path if path.is_absolute() else base / path


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise QualificationError(f"cannot read {label} {path}: {exc}") from exc


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _non_negative_number(value: Any, field: str, *, integer: bool) -> None:
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected):
        raise QualificationError(f"{field}: expected non-negative number")
    if not math.isfinite(value) or value < 0:
        raise QualificationError(f"{field}: expected finite non-negative number")


def _exact_object(
    value: Any,
    fields: set[str] | tuple[str, ...],
    label: str,
    *,
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualificationError(f"{label}: expected object")
    optional = optional or set()
    required = set(fields) - optional
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - set(fields))
    if missing or extra:
        raise QualificationError(
            f"{label}: invalid fields; missing={missing}, extra={extra}"
        )
    return value


def _validate_attempt(attempt: dict[str, Any], path: Path) -> None:
    _exact_object(
        attempt,
        _ATTEMPT_FIELDS,
        path.name,
        optional={"runtime"},
    )
    if (
        isinstance(attempt["schema_version"], bool)
        or attempt["schema_version"] != SCHEMA_VERSION
    ):
        raise QualificationError(
            f"schema_version: expected {SCHEMA_VERSION}, "
            f"got {attempt['schema_version']!r}"
        )
    for field in ("name", "brief", "agent_report"):
        if not isinstance(attempt[field], str) or not attempt[field]:
            raise QualificationError(f"{field}: expected non-empty string")

    metrics = _exact_object(attempt["metrics"], METRIC_FIELDS, "metrics")
    for field in METRIC_FIELDS:
        _non_negative_number(
            metrics[field],
            field,
            integer=field != "wall_seconds",
        )

    runtime = attempt.get("runtime")
    if runtime is None:
        return
    runtime = _exact_object(runtime, _RUNTIME_FIELDS, "runtime")
    for field in (
        "http_status",
        "console_errors_or_warnings",
        "horizontal_overflow_viewports",
    ):
        _non_negative_number(runtime[field], field, integer=True)
    screenshots = runtime["screenshots"]
    if not isinstance(screenshots, list):
        raise QualificationError("runtime.screenshots: expected list")
    for index, screenshot in enumerate(screenshots):
        screenshot = _exact_object(
            screenshot,
            _SCREENSHOT_FIELDS,
            f"runtime.screenshots[{index}]",
        )
        for field in ("name", "path", "sha256"):
            if not isinstance(screenshot[field], str) or not screenshot[field]:
                raise QualificationError(
                    f"runtime.screenshots[{index}].{field}: expected string"
                )
        for field in (
            "viewport_width",
            "viewport_height",
            "png_width",
            "png_height",
        ):
            _non_negative_number(
                screenshot[field],
                f"runtime.screenshots[{index}].{field}",
                integer=True,
            )
            if screenshot[field] == 0:
                raise QualificationError(
                    f"runtime.screenshots[{index}].{field}: expected positive integer"
                )
        digest = screenshot["sha256"]
        if len(digest) != _SHA256_LENGTH or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise QualificationError(
                f"runtime.screenshots[{index}].sha256: invalid digest"
            )


def _proposal(redesigns: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    proposals = redesigns.get("proposals")
    if not isinstance(proposals, list):
        raise QualificationError("redesigns.proposals: expected list")
    matches = [
        proposal
        for proposal in proposals
        if isinstance(proposal, dict) and proposal.get("id") == proposal_id
    ]
    if len(matches) != 1:
        raise QualificationError(
            f"proposal_id: expected one {proposal_id!r}, found {len(matches)}"
        )
    return matches[0]


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise QualificationError(f"{field}: expected non-empty strings")
    return value


def _canonical(redesigns: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    freshness = proposal.get("evidence_freshness")
    if not isinstance(freshness, dict):
        raise QualificationError("evidence_freshness: expected object")
    source = freshness.get("source")
    runtime = freshness.get("runtime")
    if not isinstance(source, dict) or not isinstance(runtime, dict):
        raise QualificationError("evidence_freshness: source/runtime missing")
    manifest = source.get("manifest")
    if not isinstance(manifest, dict):
        raise QualificationError("source manifest: expected object")

    source_hashes: dict[str, str] = {}
    source_groups: dict[str, str] = {}
    for group in ("files", "project_files"):
        entries = manifest.get(group, {})
        if not isinstance(entries, dict):
            raise QualificationError(f"source manifest {group}: expected object")
        for path, digest in entries.items():
            if not isinstance(path, str) or not isinstance(digest, str):
                raise QualificationError(f"source manifest {group}: invalid entry")
            if path in source_hashes:
                raise QualificationError(f"source manifest: duplicate path {path}")
            source_hashes[path] = digest
            source_groups[path] = group

    discovery = runtime.get("viewport_discovery")
    if not isinstance(discovery, dict):
        raise QualificationError("runtime viewport discovery: expected object")
    viewports = discovery.get("viewports")
    if not isinstance(viewports, list):
        raise QualificationError("runtime viewport discovery: expected viewports")
    normalized_viewports = []
    for viewport in viewports:
        if not isinstance(viewport, dict):
            raise QualificationError("runtime viewport: expected object")
        name = viewport.get("name")
        width = viewport.get("width")
        height = viewport.get("height")
        if not isinstance(name, str) or not name:
            raise QualificationError("runtime viewport name: expected string")
        _non_negative_number(width, f"viewport {name} width", integer=True)
        _non_negative_number(height, f"viewport {name} height", integer=True)
        normalized_viewports.append({"name": name, "width": width, "height": height})

    return {
        "preserved_contracts": _string_list(
            proposal.get("preserved_contracts"),
            "preserved_contracts",
        ),
        "named_source_anchors": _string_list(
            proposal.get("source_targets"),
            "source_targets",
        ),
        "feasibility_blockers": _string_list(
            proposal.get("feasibility_blockers"),
            "feasibility_blockers",
        ),
        "runtime_unknowns": _string_list(
            redesigns.get("unknowns", []),
            "unknowns",
        ),
        "source_hashes": source_hashes,
        "source_groups": source_groups,
        "source_manifest": manifest,
        "source_status": source.get("status"),
        "runtime": runtime,
        "viewports": normalized_viewports,
        "viewport_discovery": discovery,
    }


def _compact_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _brief_issues(text: str, canonical: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    lines = text.splitlines()
    if (
        lines.count("BEGIN_UIDETOX_EVIDENCE") != 1
        or lines.count("END_UIDETOX_EVIDENCE") != 1
    ):
        issues.append("brief:evidence-boundary")
        return issues
    start = lines.index("BEGIN_UIDETOX_EVIDENCE")
    end = lines.index("END_UIDETOX_EVIDENCE")
    if end <= start:
        issues.append("brief:evidence-boundary")
        return issues
    evidence = "\n".join(lines[start + 1 : end])

    for label, values in (
        ("source-targets", canonical["named_source_anchors"]),
        ("preserved-contracts", canonical["preserved_contracts"]),
        ("blockers", canonical["feasibility_blockers"]),
        ("unknowns", canonical["runtime_unknowns"]),
    ):
        if any(f"- {value}" not in evidence for value in values):
            issues.append(f"brief:{label}")
    for label, value in (
        ("source-manifest", canonical["source_manifest"]),
        ("viewport-discovery", canonical["viewport_discovery"]),
    ):
        if _compact_json(value) not in evidence:
            issues.append(f"brief:{label}")
    runtime = canonical["runtime"]
    for label, value in (
        ("runtime-urls", runtime.get("urls")),
        ("runtime-viewports", runtime.get("viewports")),
        ("runtime-screenshots", runtime.get("screenshots")),
    ):
        if _compact_json(value) not in evidence:
            issues.append(f"brief:{label}")
    if f"- Source: {canonical['source_status']}" not in evidence:
        issues.append("brief:source-freshness")
    if f"- Runtime: {runtime.get('status')}" not in evidence:
        issues.append("brief:runtime-freshness")
    return issues


def _actual_identities(
    value: Any,
    key: str,
    field: str,
    issues: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(value, list):
        issues.append(f"{field}:invalid")
        return [], []
    rows: list[dict[str, Any]] = []
    identities: list[str] = []
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get(key), str):
            issues.append(f"{field}:invalid")
            continue
        rows.append(row)
        identities.append(row[key])
    return identities, rows


def _account(
    expected: list[str],
    actual: list[str],
    field: str,
    issues: list[str],
) -> dict[str, Any]:
    missing = [identity for identity in expected if identity not in actual]
    extra = [identity for identity in actual if identity not in expected]
    duplicates = sorted({identity for identity in actual if actual.count(identity) > 1})
    reordered = not missing and not extra and not duplicates and actual != expected
    if missing:
        issues.append(f"{field}:missing")
    if extra:
        issues.append(f"{field}:extra")
    if duplicates:
        issues.append(f"{field}:duplicate")
    if reordered:
        issues.append(f"{field}:reordered")
    verified = sum(
        1
        for index, identity in enumerate(expected)
        if index < len(actual) and actual[index] == identity
    )
    return {
        "expected": len(expected),
        "actual": len(actual),
        "verified": verified,
        "missing": missing,
        "extra": extra,
        "duplicates": duplicates,
        "reordered": reordered,
    }


def _valid_row_field(
    row: dict[str, Any],
    row_field: str,
    prefixes: tuple[str, ...] = (),
) -> bool:
    value = row.get(row_field)
    return (
        isinstance(value, str)
        and bool(value.strip())
        and (not prefixes or value.startswith(prefixes))
    )


def _require_row_field(
    rows: list[dict[str, Any]],
    field: str,
    row_field: str,
    issues: list[str],
    *,
    prefixes: tuple[str, ...] = (),
) -> None:
    if any(not _valid_row_field(row, row_field, prefixes) for row in rows):
        issue_name = row_field.replace("_", "-")
        issues.append(f"{field}:invalid-{issue_name}")


def _report_count(
    report: dict[str, Any],
    source_field: str,
    output_field: str,
    issues: list[str],
) -> int:
    value = report.get(source_field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        issues.append(f"measurements:{output_field}")
        return 0
    return value


def _report_measurements(
    report: dict[str, Any],
    issues: list[str],
    *,
    output_prefix: str = "",
    contract_accuracy: float | None = None,
) -> dict[str, int | float]:
    fields = {
        "implementation_attempt_count": "implementation_attempt_count",
        "output_bytes": f"{output_prefix}output_bytes",
        "output_file_count": (
            "prototype_file_count" if output_prefix else "output_file_count"
        ),
        "retry_count": "retry_count",
    }
    measurements: dict[str, int | float] = {
        output: _report_count(report, source, output, issues)
        for output, source in fields.items()
    }
    if contract_accuracy is not None:
        measurements["contract_preservation_accuracy"] = contract_accuracy
    return dict(sorted(measurements.items()))


def _completed_source(
    report: dict[str, Any],
    canonical: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    expected = list(canonical["source_hashes"])
    rows = report.get("checked_source_paths")
    if not isinstance(rows, list):
        issues.append("source:invalid")
        rows = []
    actual: list[str] = []
    verified = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(
            row.get("relative_path"),
            str,
        ):
            issues.append("source:invalid")
            continue
        path = row["relative_path"]
        actual.append(path)
        expected_hash = canonical["source_hashes"].get(path)
        if (
            expected_hash is not None
            and row.get("expected_hash") == expected_hash
            and row.get("actual_hash") == expected_hash
            and row.get("freshness_status") == "fresh"
        ):
            verified += 1
        else:
            issues.append("source:hash-or-freshness")
    accounting = _account(expected, actual, "source", issues)
    accounting["verified"] = verified
    if report.get("source_freshness_status") != "fresh":
        issues.append("source:freshness-status")
    return accounting


def _png_dimensions(content: bytes, path: Path) -> tuple[int, int]:
    header = content[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise QualificationError(f"invalid PNG header: {path}")
    return struct.unpack(">II", header[16:24])


def _runtime_result(
    attempt: dict[str, Any],
    artifact_dir: Path,
    report: dict[str, Any],
    canonical: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    runtime = attempt.get("runtime")
    if not isinstance(runtime, dict):
        issues.append("runtime:missing")
        return {"passed": False, "screenshots_verified": 0}
    runtime_issue_count = len(issues)
    if not 200 <= runtime["http_status"] < 300:
        issues.append("runtime:http-status")
    if runtime["console_errors_or_warnings"] != 0:
        issues.append("runtime:console")
    if runtime["horizontal_overflow_viewports"] != 0:
        issues.append("runtime:horizontal-overflow")

    expected_viewports = canonical["viewports"]
    expected_by_name = {viewport["name"]: viewport for viewport in expected_viewports}
    report_viewports = {
        row.get("name"): row
        for row in report.get("viewports", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    screenshots = runtime["screenshots"]
    names = [
        screenshot["name"] for screenshot in screenshots if isinstance(screenshot, dict)
    ]
    _account(
        [viewport["name"] for viewport in expected_viewports],
        names,
        "runtime:screenshots",
        issues,
    )
    verified = 0
    for screenshot in screenshots:
        name = screenshot["name"]
        viewport = expected_by_name.get(name)
        report_viewport = report_viewports.get(name)
        if viewport is None or report_viewport is None:
            continue
        if (
            screenshot["viewport_width"] != viewport["width"]
            or screenshot["viewport_height"] != viewport["height"]
            or report_viewport.get("width") != viewport["width"]
            or report_viewport.get("height") != viewport["height"]
            or report_viewport.get("prototype_screenshot") != screenshot["path"]
        ):
            issues.append("runtime:viewport-handoff")
        screenshot_path = _resolve(
            artifact_dir,
            screenshot["path"],
            f"runtime screenshot {name}",
        )
        screenshot_bytes = _read_bytes(screenshot_path, "screenshot")
        actual_dimensions = _png_dimensions(screenshot_bytes, screenshot_path)
        actual_digest = _sha256(screenshot_bytes)
        declared_dimensions = (
            screenshot["png_width"],
            screenshot["png_height"],
        )
        if actual_dimensions != declared_dimensions:
            issues.append("runtime:png-dimensions")
        if actual_digest != screenshot["sha256"]:
            issues.append("runtime:screenshot-hash")
        if (
            viewport["width"] == screenshot["viewport_width"]
            and viewport["height"] == screenshot["viewport_height"]
            and actual_dimensions == declared_dimensions
            and actual_digest == screenshot["sha256"]
        ):
            verified += 1
    return {
        "passed": len(issues) == runtime_issue_count,
        "screenshots_verified": verified,
        "http_status": runtime["http_status"],
        "console_errors_or_warnings": runtime["console_errors_or_warnings"],
        "horizontal_overflow_viewports": runtime["horizontal_overflow_viewports"],
    }


def _completed(
    name: str,
    report: dict[str, Any],
    attempt: dict[str, Any],
    artifact_dir: Path,
    canonical: dict[str, Any],
    brief_issues: list[str],
) -> dict[str, Any]:
    issues = list(brief_issues)
    status = report.get("status")
    if not isinstance(status, str) or not (
        status == "completed" or status.startswith("completed-")
    ):
        issues.append("report:status")
    if report.get("implementation_attempt_count") != 1:
        issues.append("report:implementation-attempt-count")

    source = _completed_source(report, canonical, issues)
    identities: dict[str, dict[str, Any]] = {}
    specs = (
        ("preserved_contracts", "identity"),
        ("named_source_anchors", "source"),
        ("feasibility_blockers", "identity"),
        ("runtime_unknowns", "identity"),
    )
    identity_rows: dict[str, list[dict[str, Any]]] = {}
    for field, key in specs:
        actual, rows = _actual_identities(
            report.get(field),
            key,
            field,
            issues,
        )
        identities[field] = _account(
            canonical[field],
            actual,
            field,
            issues,
        )
        identity_rows[field] = rows
    _require_row_field(
        identity_rows["preserved_contracts"],
        "preserved_contracts",
        "disposition",
        issues,
        prefixes=("preserved",),
    )
    _require_row_field(
        identity_rows["preserved_contracts"],
        "preserved_contracts",
        "evidence",
        issues,
    )
    _require_row_field(
        identity_rows["named_source_anchors"],
        "named_source_anchors",
        "existence_status",
        issues,
        prefixes=("exists",),
    )
    _require_row_field(
        identity_rows["named_source_anchors"],
        "named_source_anchors",
        "preservation_status",
        issues,
        prefixes=("preserved", "unchanged"),
    )
    for field in ("feasibility_blockers", "runtime_unknowns"):
        _require_row_field(
            identity_rows[field],
            field,
            "disposition",
            issues,
        )
    semantic_requirements = {
        "preserved_contracts": (
            ("disposition", ("preserved",)),
            ("evidence", ()),
        ),
        "named_source_anchors": (
            ("existence_status", ("exists",)),
            ("preservation_status", ("preserved", "unchanged")),
        ),
        "feasibility_blockers": (("disposition", ()),),
        "runtime_unknowns": (("disposition", ()),),
    }
    for field, key in specs:
        rows = identity_rows[field]
        identities[field]["verified"] = sum(
            index < len(rows)
            and rows[index].get(key) == identity
            and all(
                _valid_row_field(rows[index], row_field, prefixes)
                for row_field, prefixes in semantic_requirements[field]
            )
            for index, identity in enumerate(canonical[field])
        )

    report_viewports = report.get("viewports")
    viewport_names = (
        [
            row.get("name")
            for row in report_viewports
            if isinstance(row, dict) and isinstance(row.get("name"), str)
        ]
        if isinstance(report_viewports, list)
        else []
    )
    viewports = _account(
        [viewport["name"] for viewport in canonical["viewports"]],
        viewport_names,
        "viewports",
        issues,
    )
    runtime = _runtime_result(
        attempt,
        artifact_dir,
        report,
        canonical,
        issues,
    )
    contract_accounting = identities["preserved_contracts"]
    contract_expected = contract_accounting["expected"]
    measurements = _report_measurements(
        report,
        issues,
        contract_accuracy=(
            contract_accounting["verified"] / contract_expected
            if contract_expected
            else 1.0
        ),
    )
    return {
        "name": name,
        "kind": "completed",
        "passed": not issues,
        "issues": list(dict.fromkeys(issues)),
        "source": source,
        "identities": identities,
        "viewports": viewports,
        "runtime": runtime,
        "measurements": measurements,
    }


def _stale_stop(
    name: str,
    report: dict[str, Any],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    if report.get("implementation_attempt_count") != 0:
        issues.append("stale-stop:implementation-attempt")
    if (
        report.get("prototype_file_count") != 0
        or report.get("prototype_output_bytes") != 0
    ):
        issues.append("stale-stop:prototype-output")

    expected_paths = list(canonical["source_hashes"])
    checked = report.get("checked_source_paths")
    if checked != expected_paths:
        issues.append("stale-stop:checked-source-paths")
    if report.get("checked_source_path_count") != len(expected_paths):
        issues.append("stale-stop:checked-source-count")

    mismatches = report.get("mismatches")
    if not isinstance(mismatches, list) or not mismatches:
        issues.append("stale-stop:mismatch")
        mismatches = []
    mismatched_paths: list[str] = []
    verified = 0
    for mismatch in mismatches:
        if not isinstance(mismatch, dict):
            issues.append("stale-stop:mismatch")
            continue
        path = mismatch.get("path")
        expected_hash = canonical["source_hashes"].get(path)
        actual_hash = mismatch.get("actual_sha256")
        if (
            isinstance(path, str)
            and mismatch.get("manifest_group") == canonical["source_groups"].get(path)
            and mismatch.get("expected_sha256") == expected_hash
            and isinstance(actual_hash, str)
            and actual_hash != expected_hash
            and mismatch.get("freshness_status") == "mismatched"
        ):
            mismatched_paths.append(path)
            verified += 1
        else:
            issues.append("stale-stop:mismatch")
    if report.get("stale_source_path_count") != len(mismatched_paths):
        issues.append("stale-stop:stale-count")
    if report.get("fresh_source_path_count") != (
        len(expected_paths) - len(mismatched_paths)
    ):
        issues.append("stale-stop:fresh-count")
    measurements = _report_measurements(
        report,
        issues,
        output_prefix="prototype_",
    )
    return {
        "name": name,
        "kind": "stale-stop",
        "passed": not issues,
        "issues": list(dict.fromkeys(issues)),
        "source": {
            "expected": len(expected_paths),
            "verified": verified,
            "mismatched": mismatched_paths,
        },
        "identities": {},
        "viewports": {"expected": 0, "actual": 0, "verified": 0},
        "runtime": {"passed": True, "screenshots_verified": 0},
        "measurements": measurements,
    }


def _percentile(values: list[int | float], percentile: float) -> int | float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _stable_number(value: float) -> int | float:
    return round(value, 9) if isinstance(value, float) else value


def _distribution(values: list[int | float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "max": _stable_number(max(ordered)),
        "mean": _stable_number(mean(ordered)),
        "median": _stable_number(median(ordered)),
        "min": _stable_number(min(ordered)),
        "p90": _stable_number(_percentile(ordered, 0.9)),
        "samples": values,
    }


def qualify(
    redesigns_path: str | Path,
    proposal_id: str,
    attempt_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Qualify ordered attempts against one canonical redesign proposal."""

    if not attempt_paths:
        raise QualificationError("attempt: provide at least one manifest")
    redesigns = _load_json(Path(redesigns_path), "redesigns")
    proposal = _proposal(redesigns, proposal_id)
    canonical = _canonical(redesigns, proposal)

    results: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    distribution_values: dict[str, list[int | float]] = {
        field: [] for field in (*METRIC_FIELDS, *REPORT_METRIC_FIELDS)
    }
    distribution_values["contract_preservation_accuracy"] = []
    for raw_path in attempt_paths:
        attempt_path = Path(raw_path)
        attempt = _load_json(attempt_path, "attempt")
        _validate_attempt(attempt, attempt_path)
        if attempt["name"] in seen_names:
            raise QualificationError(f"duplicate attempt name: {attempt['name']!r}")
        seen_names.add(attempt["name"])
        attempt_dir = attempt_path.parent
        brief_path = _resolve(attempt_dir, attempt["brief"], "brief")
        report_path = _resolve(
            attempt_dir,
            attempt["agent_report"],
            "agent_report",
        )
        report, report_hash = _load_json_artifact(
            report_path,
            "agent_report",
        )
        brief_bytes = _read_bytes(brief_path, "brief")
        brief_hash = _sha256(brief_bytes)
        hash_issues = (
            [] if report.get("brief_sha256") == brief_hash else ["brief:sha256"]
        )
        if report.get("status") == "blocked-stale-source":
            result = _stale_stop(attempt["name"], report, canonical)
            result["issues"] = hash_issues + result["issues"]
            result["passed"] = not result["issues"]
        else:
            try:
                text = brief_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise QualificationError(
                    f"brief: expected UTF-8 text: {brief_path}"
                ) from exc
            result = _completed(
                attempt["name"],
                report,
                attempt,
                report_path.parent,
                canonical,
                hash_issues + _brief_issues(text, canonical),
            )
        result["artifacts"] = {
            "agent_report_sha256": report_hash,
            "brief_sha256": brief_hash,
        }
        results.append(result)
        for field in METRIC_FIELDS:
            distribution_values[field].append(attempt["metrics"][field])
        for field, value in result["measurements"].items():
            distribution_values[field].append(value)

    completed = sum(result["kind"] == "completed" for result in results)
    stale_stops = sum(result["kind"] == "stale-stop" for result in results)
    all_passed = all(result["passed"] for result in results)
    passed_completed = sum(
        result["kind"] == "completed" and result["passed"] for result in results
    )
    passed_stale = sum(
        result["kind"] == "stale-stop" and result["passed"] for result in results
    )
    stale_before_completed = any(
        stale["kind"] == "stale-stop"
        and stale["passed"]
        and any(
            completed["kind"] == "completed" and completed["passed"]
            for completed in results[index + 1 :]
        )
        for index, stale in enumerate(results)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "proposal_id": proposal_id,
        "attempts": results,
        "distributions": {
            field: _distribution(values)
            for field, values in distribution_values.items()
            if values
        },
        "recovery": {
            "passed_completed_attempts": passed_completed,
            "passed_stale_stops": passed_stale,
            "stale_stop_followed_by_completed": stale_before_completed,
        },
        "gates": {
            "all_attempts_passed": all_passed,
            "completed_attempts": completed,
            "passed": all_passed and completed > 0,
            "stale_stops": stale_stops,
        },
    }


def write_report(result: dict[str, Any], output: str | Path) -> None:
    """Write stable JSON with no clock- or host-dependent fields."""

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + os.linesep,
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Qualify disposable-agent handoff attempts.",
    )
    parser.add_argument("--redesigns", type=Path, required=True)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument(
        "--attempt",
        action="append",
        type=Path,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = qualify(args.redesigns, args.proposal_id, args.attempt)
    except QualificationError as exc:
        print(f"Qualification failed: {exc}")
        return 2
    write_report(result, args.output)
    return 0 if result["gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
