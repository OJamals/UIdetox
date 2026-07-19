"""JSON-only protocol and trust-boundary validation for visual workers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from uidetox.visual_evidence import (
    VISUAL_EVIDENCE_SCHEMA_VERSION,
    ArtifactEvidence,
    FreshnessEvidence,
    ImageEvidence,
    RegionEvidence,
    VisualComparison,
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceManifest,
    VisualEvidenceRequest,
    VisualMetrics,
    VisualRegion,
    validate_visual_evidence_request,
    visual_evidence_request_hash_from_payload,
)


WORKER_PROTOCOL_VERSION = 1
DEFAULT_WORKER_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_REQUEST_BYTES = 256 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_STDERR_BYTES = 64 * 1024
DEFAULT_MAX_MEMORY_BYTES = 1024 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 128 * 1024 * 1024
DEFAULT_CPU_SECONDS = 30
HARD_MAX_REQUEST_BYTES = 1024 * 1024
HARD_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
HARD_MAX_STDERR_BYTES = 1024 * 1024
HARD_MAX_MEMORY_BYTES = 4 * 1024 * 1024 * 1024
HARD_MAX_FILE_BYTES = 512 * 1024 * 1024
HARD_MAX_CPU_SECONDS = 300
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class VisualWorkerPolicy:
    """Resource and path policy enforced by both parent and worker."""

    allowed_roots: tuple[Path, ...]
    timeout_seconds: float = DEFAULT_WORKER_TIMEOUT_SECONDS
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES
    max_memory_bytes: int = DEFAULT_MAX_MEMORY_BYTES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    cpu_seconds: int = DEFAULT_CPU_SECONDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_roots": [str(path) for path in self.allowed_roots],
            "timeout_seconds": self.timeout_seconds,
            "max_request_bytes": self.max_request_bytes,
            "max_output_bytes": self.max_output_bytes,
            "max_stderr_bytes": self.max_stderr_bytes,
            "max_memory_bytes": self.max_memory_bytes,
            "max_file_bytes": self.max_file_bytes,
            "cpu_seconds": self.cpu_seconds,
        }


def normalize_worker_policy(
    policy: VisualWorkerPolicy,
) -> VisualWorkerPolicy:
    roots = tuple(
        dict.fromkeys(path.expanduser().resolve() for path in policy.allowed_roots)
    )
    if not roots:
        raise VisualEvidenceError(
            "worker_policy",
            "Isolated visual evidence requires at least one allowed root.",
        )
    if any(not root.is_dir() for root in roots):
        raise VisualEvidenceError(
            "worker_policy",
            "Every isolated visual-evidence allowed root must be a directory.",
        )
    numeric_limits = (
        ("timeout_seconds", policy.timeout_seconds, 0.1, 300.0),
        (
            "max_request_bytes",
            policy.max_request_bytes,
            1024,
            HARD_MAX_REQUEST_BYTES,
        ),
        (
            "max_output_bytes",
            policy.max_output_bytes,
            1024,
            HARD_MAX_OUTPUT_BYTES,
        ),
        (
            "max_stderr_bytes",
            policy.max_stderr_bytes,
            1024,
            HARD_MAX_STDERR_BYTES,
        ),
        (
            "max_memory_bytes",
            policy.max_memory_bytes,
            64 * 1024 * 1024,
            HARD_MAX_MEMORY_BYTES,
        ),
        (
            "max_file_bytes",
            policy.max_file_bytes,
            1024 * 1024,
            HARD_MAX_FILE_BYTES,
        ),
        ("cpu_seconds", policy.cpu_seconds, 1, HARD_MAX_CPU_SECONDS),
    )
    for name, value, minimum, maximum in numeric_limits:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not minimum <= value <= maximum
        ):
            raise VisualEvidenceError(
                "worker_policy",
                f"Worker {name} must be between {minimum} and {maximum}.",
            )
    integer_limits = (
        ("max_request_bytes", policy.max_request_bytes),
        ("max_output_bytes", policy.max_output_bytes),
        ("max_stderr_bytes", policy.max_stderr_bytes),
        ("max_memory_bytes", policy.max_memory_bytes),
        ("max_file_bytes", policy.max_file_bytes),
        ("cpu_seconds", policy.cpu_seconds),
    )
    for name, value in integer_limits:
        if not isinstance(value, int) or isinstance(value, bool):
            raise VisualEvidenceError(
                "worker_policy",
                f"Worker {name} must be an integer.",
            )
    return replace(policy, allowed_roots=roots)


def worker_policy_from_dict(payload: object) -> VisualWorkerPolicy:
    value = _mapping(payload, "worker policy")
    roots = tuple(
        Path(_string(item, "allowed root"))
        for item in _sequence(value.get("allowed_roots"), "allowed roots")
    )
    policy = VisualWorkerPolicy(
        allowed_roots=roots,
        timeout_seconds=_number(
            value.get("timeout_seconds"),
            "timeout_seconds",
        ),
        max_request_bytes=_integer(
            value.get("max_request_bytes"),
            "max_request_bytes",
        ),
        max_output_bytes=_integer(
            value.get("max_output_bytes"),
            "max_output_bytes",
        ),
        max_stderr_bytes=_integer(
            value.get("max_stderr_bytes"),
            "max_stderr_bytes",
        ),
        max_memory_bytes=_integer(
            value.get("max_memory_bytes"),
            "max_memory_bytes",
        ),
        max_file_bytes=_integer(
            value.get("max_file_bytes"),
            "max_file_bytes",
        ),
        cpu_seconds=_integer(value.get("cpu_seconds"), "cpu_seconds"),
    )
    return normalize_worker_policy(policy)


def visual_request_to_dict(
    request: VisualEvidenceRequest,
) -> dict[str, Any]:
    return {
        "comparisons": [
            {
                "case_id": case.case_id,
                "before_path": str(case.before_path),
                "after_path": str(case.after_path),
                "viewport": (
                    list(case.viewport) if case.viewport is not None else None
                ),
                "semantic_regions": [
                    _visual_region_to_dict(region) for region in case.semantic_regions
                ],
                "ignore_regions": [
                    _visual_region_to_dict(region) for region in case.ignore_regions
                ],
            }
            for case in request.comparisons
        ],
        "output_dir": str(request.output_dir),
        "threshold": request.threshold,
        "max_pixels": request.max_pixels,
        "amplification": request.amplification,
        "alpha_background": list(request.alpha_background),
        "dimension_policy": request.dimension_policy,
        "color_policy": request.color_policy,
        "reviewer_artifacts": request.reviewer_artifacts,
        "crop_padding": request.crop_padding,
        "expected_viewports": list(request.expected_viewports),
        "png_compress_level": request.png_compress_level,
        "png_optimize": request.png_optimize,
        "context_sha256s": request.context_sha256s,
        "context": request.context,
    }


def visual_request_from_dict(payload: object) -> VisualEvidenceRequest:
    value = _mapping(payload, "visual request")
    comparisons = tuple(
        _visual_case_from_dict(item)
        for item in _sequence(value.get("comparisons"), "comparisons")
    )
    alpha = tuple(
        _integer(item, "alpha channel")
        for item in _sequence(
            value.get("alpha_background"),
            "alpha_background",
        )
    )
    context_hashes = {
        _string(key, "context key"): _string(item, "context hash")
        for key, item in _mapping(
            value.get("context_sha256s"),
            "context_sha256s",
        ).items()
    }
    context = dict(_mapping(value.get("context"), "context"))
    request = VisualEvidenceRequest(
        comparisons=comparisons,
        output_dir=Path(_string(value.get("output_dir"), "output_dir")),
        manifest_path=None,
        threshold=_integer(value.get("threshold"), "threshold"),
        max_pixels=_integer(value.get("max_pixels"), "max_pixels"),
        amplification=_integer(
            value.get("amplification"),
            "amplification",
        ),
        alpha_background=alpha,  # type: ignore[arg-type]
        dimension_policy=_string(
            value.get("dimension_policy"),
            "dimension_policy",
        ),
        color_policy=_string(value.get("color_policy"), "color_policy"),
        reviewer_artifacts=_boolean(
            value.get("reviewer_artifacts"),
            "reviewer_artifacts",
        ),
        crop_padding=_integer(value.get("crop_padding"), "crop_padding"),
        expected_viewports=tuple(
            _string(item, "expected viewport")
            for item in _sequence(
                value.get("expected_viewports"),
                "expected_viewports",
            )
        ),
        png_compress_level=_integer(
            value.get("png_compress_level"),
            "png_compress_level",
        ),
        png_optimize=_boolean(
            value.get("png_optimize"),
            "png_optimize",
        ),
        context_sha256s=context_hashes,
        context=context,
    )
    validate_visual_evidence_request(request)
    return request


def assert_request_paths_allowed(
    request: VisualEvidenceRequest,
    policy: VisualWorkerPolicy,
) -> None:
    normalized = normalize_worker_policy(policy)
    output_dir = _allowed_path(
        request.output_dir,
        normalized.allowed_roots,
        role="output directory",
    )
    if request.manifest_path is not None:
        _allowed_path(
            request.manifest_path,
            normalized.allowed_roots,
            role="manifest",
        )
    for case in request.comparisons:
        for role, path in (
            ("before image", case.before_path),
            ("after image", case.after_path),
        ):
            resolved = _allowed_path(
                path,
                normalized.allowed_roots,
                role=role,
            )
            if not resolved.is_file():
                raise VisualEvidenceError(
                    "worker_path",
                    f"Isolated visual-evidence {role} is not a file: {resolved}",
                    path=resolved,
                )
            try:
                size = resolved.stat().st_size
            except OSError as error:
                raise VisualEvidenceError(
                    "worker_path",
                    f"Could not inspect isolated visual-evidence input: {error}",
                    path=resolved,
                ) from error
            if size > normalized.max_file_bytes:
                raise VisualEvidenceError(
                    "worker_input_too_large",
                    (
                        f"Input file has {size:,} bytes; worker limit is "
                        f"{normalized.max_file_bytes:,}: {resolved}"
                    ),
                    path=resolved,
                )
    if not _is_within(output_dir, normalized.allowed_roots):
        raise VisualEvidenceError(
            "worker_path",
            f"Output directory escapes allowed roots: {output_dir}",
        )


def validate_worker_manifest(
    payload: object,
    *,
    request: VisualEvidenceRequest,
    policy: VisualWorkerPolicy,
) -> VisualEvidenceManifest:
    """Treat worker output as untrusted and return a typed manifest."""

    normalized = normalize_worker_policy(policy)
    value = _mapping(payload, "worker manifest")
    manifest = visual_manifest_from_dict(value)
    if manifest.schema_version != VISUAL_EVIDENCE_SCHEMA_VERSION:
        raise VisualEvidenceError(
            "worker_response",
            "Worker returned an unsupported visual-evidence schema.",
        )
    if manifest.status != "complete":
        raise VisualEvidenceError(
            "worker_response",
            "Worker returned an incomplete visual-evidence manifest.",
        )
    expected_parameters = {
        "algorithm": "rgb-sum-v1",
        "threshold": request.threshold,
        "max_pixels": request.max_pixels,
        "amplification": request.amplification,
        "alpha_background": list(request.alpha_background),
        "dimension_policy": request.dimension_policy,
        "color_policy": request.color_policy,
        "reviewer_artifacts": request.reviewer_artifacts,
        "crop_padding": request.crop_padding,
        "expected_viewports": list(request.expected_viewports),
        "png_compress_level": request.png_compress_level,
        "png_optimize": request.png_optimize,
    }
    for key, expected in expected_parameters.items():
        if manifest.parameters.get(key) != expected:
            raise VisualEvidenceError(
                "worker_response",
                f"Worker manifest parameter {key!r} does not match the request.",
            )
    if not (
        isinstance(manifest.parameters.get("pillow_version"), str)
        and manifest.parameters["pillow_version"].strip()
    ):
        raise VisualEvidenceError(
            "worker_response",
            "Worker manifest lacks a Pillow version.",
        )
    if len(manifest.comparisons) != len(request.comparisons):
        raise VisualEvidenceError(
            "worker_response",
            "Worker returned an unexpected comparison count.",
        )
    raw_hashes: list[str] = []
    output_dir = request.output_dir.expanduser().resolve()
    for case, comparison in zip(
        request.comparisons,
        manifest.comparisons,
        strict=True,
    ):
        if comparison.case_id != case.case_id or comparison.viewport != case.viewport:
            raise VisualEvidenceError(
                "worker_response",
                "Worker comparison identity does not match the request.",
            )
        for expected_path, image in (
            (case.before_path, comparison.before),
            (case.after_path, comparison.after),
        ):
            resolved = _allowed_path(
                image.path,
                normalized.allowed_roots,
                role="worker image",
            )
            if resolved != expected_path.expanduser().resolve():
                raise VisualEvidenceError(
                    "worker_response",
                    "Worker returned an unexpected source image path.",
                )
            _validate_hash(image.sha256, "source image")
            _validate_hash(image.normalized_sha256, "normalized image")
            _validate_image_evidence(
                image,
                max_pixels=request.max_pixels,
            )
            if resolved.stat().st_size > normalized.max_file_bytes:
                raise VisualEvidenceError(
                    "worker_response",
                    f"Worker source image exceeds the file limit: {resolved}",
                )
            if _sha256_file(resolved) != image.sha256:
                raise VisualEvidenceError(
                    "worker_response",
                    f"Worker source image hash is invalid: {resolved}",
                )
            raw_hashes.append(image.sha256)
        if (
            comparison.before.width,
            comparison.before.height,
        ) != (
            comparison.after.width,
            comparison.after.height,
        ):
            raise VisualEvidenceError(
                "worker_response",
                "Worker comparison image dimensions do not match.",
            )
        _validate_metrics(
            comparison.metrics,
            comparison.before,
            threshold=request.threshold,
        )
        _validate_regions(case, comparison)
        for artifact in comparison.artifacts:
            _validate_artifact(
                artifact,
                output_dir=output_dir,
                allowed_roots=normalized.allowed_roots,
                max_file_bytes=normalized.max_file_bytes,
            )
    for artifact in manifest.artifacts:
        _validate_artifact(
            artifact,
            output_dir=output_dir,
            allowed_roots=normalized.allowed_roots,
            max_file_bytes=normalized.max_file_bytes,
        )
    expected_incomplete = tuple(
        viewport
        for viewport in request.expected_viewports
        if viewport not in {case.case_id for case in request.comparisons}
    )
    if manifest.incomplete_viewports != expected_incomplete:
        raise VisualEvidenceError(
            "worker_response",
            "Worker incomplete-viewport evidence does not match the request.",
        )
    if manifest.freshness.source_sha256s != tuple(raw_hashes):
        raise VisualEvidenceError(
            "worker_response",
            "Worker freshness source hashes do not match comparison inputs.",
        )
    if manifest.freshness.context_sha256s != dict(
        sorted(request.context_sha256s.items())
    ):
        raise VisualEvidenceError(
            "worker_response",
            "Worker freshness context hashes do not match the request.",
        )
    if _canonical_json(manifest.context) != _canonical_json(request.context):
        raise VisualEvidenceError(
            "worker_response",
            "Worker manifest context does not match the request.",
        )
    expected_request_hash = visual_evidence_request_hash_from_payload(value)
    if manifest.freshness.request_sha256 != expected_request_hash:
        raise VisualEvidenceError(
            "worker_response",
            "Worker visual-evidence request hash is invalid.",
        )
    return manifest


def visual_manifest_from_dict(payload: object) -> VisualEvidenceManifest:
    value = _mapping(payload, "visual manifest")
    parameters = dict(_mapping(value.get("parameters"), "parameters"))
    comparisons = tuple(
        _visual_comparison_from_dict(item)
        for item in _sequence(value.get("comparisons"), "comparisons")
    )
    freshness_value = _mapping(value.get("freshness"), "freshness")
    freshness = FreshnessEvidence(
        request_sha256=_string(
            freshness_value.get("request_sha256"),
            "request_sha256",
        ),
        source_sha256s=tuple(
            _string(item, "source hash")
            for item in _sequence(
                freshness_value.get("source_sha256s"),
                "source_sha256s",
            )
        ),
        context_sha256s={
            _string(key, "context key"): _string(item, "context hash")
            for key, item in _mapping(
                freshness_value.get("context_sha256s"),
                "context_sha256s",
            ).items()
        },
    )
    return VisualEvidenceManifest(
        schema_version=_integer(
            value.get("schema_version"),
            "schema_version",
        ),
        generated_at=_string(value.get("generated_at"), "generated_at"),
        status=_string(value.get("status"), "status"),
        parameters=parameters,
        comparisons=comparisons,
        freshness=freshness,
        context=dict(_mapping(value.get("context", {}), "context")),
        artifacts=tuple(
            _artifact_from_dict(item)
            for item in _sequence(value.get("artifacts", []), "artifacts")
        ),
        incomplete_viewports=tuple(
            _string(item, "incomplete viewport")
            for item in _sequence(
                value.get("incomplete_viewports", []),
                "incomplete_viewports",
            )
        ),
        warnings=tuple(
            _string(item, "warning")
            for item in _sequence(value.get("warnings", []), "warnings")
        ),
    )


def _visual_case_from_dict(payload: object) -> VisualEvidenceCase:
    value = _mapping(payload, "comparison")
    viewport_value = value.get("viewport")
    viewport = None
    if viewport_value is not None:
        viewport_items = _sequence(viewport_value, "viewport")
        if len(viewport_items) != 2:
            raise VisualEvidenceError(
                "worker_request",
                "Viewport must contain width and height.",
            )
        viewport = (
            _integer(viewport_items[0], "viewport width"),
            _integer(viewport_items[1], "viewport height"),
        )
    return VisualEvidenceCase(
        case_id=_string(value.get("case_id"), "case_id"),
        before_path=Path(_string(value.get("before_path"), "before_path")),
        after_path=Path(_string(value.get("after_path"), "after_path")),
        viewport=viewport,
        semantic_regions=tuple(
            _visual_region_from_dict(item)
            for item in _sequence(
                value.get("semantic_regions", []),
                "semantic_regions",
            )
        ),
        ignore_regions=tuple(
            _visual_region_from_dict(item)
            for item in _sequence(
                value.get("ignore_regions", []),
                "ignore_regions",
            )
        ),
    )


def _visual_region_to_dict(region: VisualRegion) -> dict[str, Any]:
    return {
        "region_id": region.region_id,
        "bounds": list(region.bounds),
        "kind": region.kind,
        "provenance": region.provenance,
        "reason": region.reason,
        "source_targets": list(region.source_targets),
        "intent_fields": list(region.intent_fields),
        "preserve_contracts": list(region.preserve_contracts),
    }


def _visual_region_from_dict(payload: object) -> VisualRegion:
    value = _mapping(payload, "visual region")
    bounds = tuple(
        _number(item, "region bound")
        for item in _sequence(value.get("bounds"), "region bounds")
    )
    return VisualRegion(
        region_id=_string(value.get("region_id"), "region_id"),
        bounds=bounds,  # type: ignore[arg-type]
        kind=_string(value.get("kind"), "region kind"),
        provenance=_string(value.get("provenance"), "region provenance"),
        reason=_string(value.get("reason", ""), "region reason"),
        source_targets=_string_tuple(
            value.get("source_targets", []),
            "source_targets",
        ),
        intent_fields=_string_tuple(
            value.get("intent_fields", []),
            "intent_fields",
        ),
        preserve_contracts=_string_tuple(
            value.get("preserve_contracts", []),
            "preserve_contracts",
        ),
    )


def _visual_comparison_from_dict(payload: object) -> VisualComparison:
    value = _mapping(payload, "visual comparison")
    viewport_value = value.get("viewport")
    viewport = None
    if viewport_value is not None:
        items = _sequence(viewport_value, "viewport")
        if len(items) != 2:
            raise VisualEvidenceError(
                "worker_response",
                "Worker viewport must contain two integers.",
            )
        viewport = (
            _integer(items[0], "viewport width"),
            _integer(items[1], "viewport height"),
        )
    metrics_value = _mapping(value.get("metrics"), "metrics")
    changed_bounds_value = metrics_value.get("changed_bounds")
    changed_bounds = None
    if changed_bounds_value is not None:
        changed_bounds_items = tuple(
            _integer(item, "changed bound")
            for item in _sequence(changed_bounds_value, "changed_bounds")
        )
        if len(changed_bounds_items) != 4:
            raise VisualEvidenceError(
                "worker_response",
                "Worker changed bounds must contain four coordinates.",
            )
        changed_bounds = changed_bounds_items
        if len(changed_bounds) != 4:
            raise VisualEvidenceError(
                "worker_response",
                "Changed bounds must contain four integers.",
            )
    metrics = VisualMetrics(
        threshold=_integer(metrics_value.get("threshold"), "threshold"),
        raw_pixels_changed=_integer(
            metrics_value.get("raw_pixels_changed"),
            "raw_pixels_changed",
        ),
        ignored_changed_pixels=_integer(
            metrics_value.get("ignored_changed_pixels"),
            "ignored_changed_pixels",
        ),
        ignored_ratio=_number(
            metrics_value.get("ignored_ratio"),
            "ignored_ratio",
        ),
        pixels_changed=_integer(
            metrics_value.get("pixels_changed"),
            "pixels_changed",
        ),
        total_pixels=_integer(
            metrics_value.get("total_pixels"),
            "total_pixels",
        ),
        change_percentage=_number(
            metrics_value.get("change_percentage"),
            "change_percentage",
        ),
        changed_ratio=_number(
            metrics_value.get("changed_ratio"),
            "changed_ratio",
        ),
        coverage_band=_string(
            metrics_value.get("coverage_band"),
            "coverage_band",
        ),
        changed_bounds=changed_bounds,  # type: ignore[arg-type]
        changed_bounds_ratio=_number(
            metrics_value.get("changed_bounds_ratio"),
            "changed_bounds_ratio",
        ),
        exact_match=_boolean(
            metrics_value.get("exact_match"),
            "exact_match",
        ),
        mean_channel_delta=_number_triplet(
            metrics_value.get("mean_channel_delta"),
            "mean_channel_delta",
        ),
        rms_channel_delta=_number_triplet(
            metrics_value.get("rms_channel_delta"),
            "rms_channel_delta",
        ),
        stddev_channel_delta=_number_triplet(
            metrics_value.get("stddev_channel_delta"),
            "stddev_channel_delta",
        ),
        extrema=tuple(
            tuple(
                _integer(item, "extrema value")
                for item in _sequence(pair, "extrema pair")
            )
            for pair in _sequence(metrics_value.get("extrema"), "extrema")
        ),  # type: ignore[arg-type]
    )
    return VisualComparison(
        case_id=_string(value.get("case_id"), "case_id"),
        viewport=viewport,
        before=_image_from_dict(value.get("before")),
        after=_image_from_dict(value.get("after")),
        metrics=metrics,
        regions=tuple(
            _region_from_dict(item)
            for item in _sequence(value.get("regions", []), "regions")
        ),
        ignored_regions=tuple(
            _region_from_dict(item)
            for item in _sequence(
                value.get("ignored_regions", []),
                "ignored_regions",
            )
        ),
        artifacts=tuple(
            _artifact_from_dict(item)
            for item in _sequence(value.get("artifacts", []), "artifacts")
        ),
    )


def _image_from_dict(payload: object) -> ImageEvidence:
    value = _mapping(payload, "image evidence")
    return ImageEvidence(
        path=Path(_string(value.get("path"), "image path")),
        sha256=_string(value.get("sha256"), "image sha256"),
        normalized_sha256=_string(
            value.get("normalized_sha256"),
            "normalized sha256",
        ),
        width=_integer(value.get("width"), "image width"),
        height=_integer(value.get("height"), "image height"),
        format=_string(value.get("format"), "image format"),
        source_mode=_string(value.get("source_mode"), "source mode"),
        normalized_mode=_string(
            value.get("normalized_mode"),
            "normalized mode",
        ),
        frames=_integer(value.get("frames"), "frames"),
        icc_profile_present=_boolean(
            value.get("icc_profile_present", False),
            "icc_profile_present",
        ),
        color_conversion=_string(
            value.get("color_conversion", "native"),
            "color_conversion",
        ),
        warnings=_string_tuple(value.get("warnings", []), "warnings"),
    )


def _artifact_from_dict(payload: object) -> ArtifactEvidence:
    value = _mapping(payload, "artifact evidence")
    path_value = value.get("path")
    return ArtifactEvidence(
        kind=_string(value.get("kind"), "artifact kind"),
        path=(
            Path(_string(path_value, "artifact path"))
            if path_value is not None
            else None
        ),
        sha256=_string(value.get("sha256", ""), "artifact sha256"),
        width=_integer(value.get("width"), "artifact width"),
        height=_integer(value.get("height"), "artifact height"),
        status=_string(value.get("status", "generated"), "artifact status"),
        reason=_string(value.get("reason", ""), "artifact reason"),
    )


def _region_from_dict(payload: object) -> RegionEvidence:
    value = _mapping(payload, "region evidence")
    return RegionEvidence(
        region_id=_string(value.get("region_id"), "region_id"),
        kind=_string(value.get("kind"), "region kind"),
        requested_bounds=tuple(
            _number(item, "requested bound")
            for item in _sequence(
                value.get("requested_bounds"),
                "requested_bounds",
            )
        ),  # type: ignore[arg-type]
        bounds=tuple(
            _integer(item, "region bound")
            for item in _sequence(value.get("bounds"), "bounds")
        ),  # type: ignore[arg-type]
        pixels_changed=_integer(
            value.get("pixels_changed"),
            "region pixels_changed",
        ),
        total_pixels=_integer(
            value.get("total_pixels"),
            "region total_pixels",
        ),
        changed_ratio=_number(
            value.get("changed_ratio"),
            "region changed_ratio",
        ),
        reason=_string(value.get("reason", ""), "region reason"),
        provenance=_string(value.get("provenance"), "region provenance"),
        source_targets=_string_tuple(
            value.get("source_targets", []),
            "source_targets",
        ),
        intent_fields=_string_tuple(
            value.get("intent_fields", []),
            "intent_fields",
        ),
        preserve_contracts=_string_tuple(
            value.get("preserve_contracts", []),
            "preserve_contracts",
        ),
    )


def _validate_image_evidence(
    image: ImageEvidence,
    *,
    max_pixels: int,
) -> None:
    if (
        image.width <= 0
        or image.height <= 0
        or image.width * image.height > max_pixels
        or image.frames != 1
        or image.format != "PNG"
        or not image.source_mode
        or image.normalized_mode != "RGB"
        or not image.color_conversion
    ):
        raise VisualEvidenceError(
            "worker_response",
            "Worker returned invalid source-image evidence.",
        )


def _validate_metrics(
    metrics: VisualMetrics,
    image: ImageEvidence,
    *,
    threshold: int,
) -> None:
    total = image.width * image.height
    percentage = metrics.pixels_changed / total * 100
    expected_ignored_ratio = (
        metrics.ignored_changed_pixels / metrics.raw_pixels_changed
        if metrics.raw_pixels_changed
        else 0.0
    )
    expected_bounds_ratio = 0.0
    if metrics.changed_bounds is not None:
        left, top, right, bottom = metrics.changed_bounds
        expected_bounds_ratio = (right - left) * (bottom - top) / total
    extrema_valid = len(metrics.extrema) == 3 and all(
        len(bounds) == 2 and 0 <= bounds[0] <= bounds[1] <= 255
        for bounds in metrics.extrema
    )
    deltas_valid = all(
        math.isfinite(value) and 0.0 <= value <= 255.0
        for values in (
            metrics.mean_channel_delta,
            metrics.rms_channel_delta,
            metrics.stddev_channel_delta,
        )
        for value in values
    )
    if (
        metrics.threshold != threshold
        or metrics.total_pixels != total
        or not 0 <= metrics.pixels_changed <= metrics.raw_pixels_changed <= total
        or metrics.ignored_changed_pixels
        != metrics.raw_pixels_changed - metrics.pixels_changed
        or not 0.0 <= metrics.changed_ratio <= 1.0
        or not 0.0 <= metrics.change_percentage <= 100.0
        or not 0.0 <= metrics.ignored_ratio <= 1.0
        or not 0.0 <= metrics.changed_bounds_ratio <= 1.0
        or not extrema_valid
        or not deltas_valid
        or metrics.exact_match != all(bounds[1] == 0 for bounds in metrics.extrema)
        or metrics.coverage_band != _coverage_band(percentage)
        or (metrics.pixels_changed == 0) != (metrics.changed_bounds is None)
    ):
        raise VisualEvidenceError(
            "worker_response",
            "Worker returned out-of-range visual metrics.",
        )
    expected_ratio = metrics.pixels_changed / total
    if (
        not math.isclose(
            metrics.changed_ratio,
            round(expected_ratio, 8),
            abs_tol=1e-8,
        )
        or not math.isclose(
            metrics.change_percentage,
            round(expected_ratio * 100, 2),
            abs_tol=0.01,
        )
        or not math.isclose(
            metrics.ignored_ratio,
            round(expected_ignored_ratio, 8),
            abs_tol=1e-8,
        )
        or not math.isclose(
            metrics.changed_bounds_ratio,
            round(expected_bounds_ratio, 8),
            abs_tol=1e-8,
        )
    ):
        raise VisualEvidenceError(
            "worker_response",
            "Worker visual metrics are internally inconsistent.",
        )
    if metrics.changed_bounds is not None:
        left, top, right, bottom = metrics.changed_bounds
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise VisualEvidenceError(
                "worker_response",
                "Worker changed bounds are outside the image.",
            )


def _coverage_band(change_percentage: float) -> str:
    if change_percentage < 0.1:
        return "trace"
    if change_percentage < 5:
        return "localized"
    if change_percentage < 20:
        return "noticeable"
    if change_percentage < 50:
        return "broad"
    return "extensive"


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise VisualEvidenceError(
            "worker_response",
            "Worker manifest context must be finite JSON data.",
        ) from error


def _validate_regions(
    case: VisualEvidenceCase,
    comparison: VisualComparison,
) -> None:
    for requested, measured in (
        (case.semantic_regions, comparison.regions),
        (case.ignore_regions, comparison.ignored_regions),
    ):
        if len(requested) != len(measured):
            raise VisualEvidenceError(
                "worker_response",
                "Worker region count does not match the request.",
            )
        for source, result in zip(requested, measured, strict=True):
            if len(result.requested_bounds) != 4 or len(result.bounds) != 4:
                raise VisualEvidenceError(
                    "worker_response",
                    "Worker region bounds must contain four coordinates.",
                )
            expected = (
                source.region_id,
                source.kind,
                tuple(float(item) for item in source.bounds),
                source.reason,
                source.provenance,
                source.source_targets,
                source.intent_fields,
                source.preserve_contracts,
            )
            actual = (
                result.region_id,
                result.kind,
                result.requested_bounds,
                result.reason,
                result.provenance,
                result.source_targets,
                result.intent_fields,
                result.preserve_contracts,
            )
            if expected != actual or not (
                0 <= result.pixels_changed <= result.total_pixels
                and 0.0 <= result.changed_ratio <= 1.0
                and math.isclose(
                    result.changed_ratio,
                    round(
                        result.pixels_changed / result.total_pixels
                        if result.total_pixels
                        else 0.0,
                        8,
                    ),
                    abs_tol=1e-8,
                )
            ):
                raise VisualEvidenceError(
                    "worker_response",
                    "Worker region evidence does not match the request.",
                )
            left, top, right, bottom = result.bounds
            region_area = (right - left) * (bottom - top)
            if not (
                0 <= left <= right <= comparison.before.width
                and 0 <= top <= bottom <= comparison.before.height
                and result.total_pixels <= region_area
            ):
                raise VisualEvidenceError(
                    "worker_response",
                    "Worker region bounds are outside the source image.",
                )


def _validate_artifact(
    artifact: ArtifactEvidence,
    *,
    output_dir: Path,
    allowed_roots: tuple[Path, ...],
    max_file_bytes: int,
) -> None:
    if artifact.status == "omitted":
        if artifact.path is not None or artifact.sha256 or not artifact.reason:
            raise VisualEvidenceError(
                "worker_response",
                "Worker returned an invalid omitted artifact.",
            )
        return
    if artifact.status != "generated" or artifact.path is None:
        raise VisualEvidenceError(
            "worker_response",
            "Worker returned an invalid artifact status.",
        )
    resolved = _allowed_path(
        artifact.path,
        allowed_roots,
        role="artifact",
    )
    if not _is_within(resolved, (output_dir,)):
        raise VisualEvidenceError(
            "worker_response",
            f"Worker artifact escapes the output directory: {resolved}",
        )
    if artifact.width <= 0 or artifact.height <= 0:
        raise VisualEvidenceError(
            "worker_response",
            "Worker artifact dimensions must be positive.",
        )
    _validate_hash(artifact.sha256, "artifact")
    if not resolved.is_file():
        raise VisualEvidenceError(
            "worker_response",
            f"Worker artifact is missing: {resolved}",
        )
    if resolved.stat().st_size > max_file_bytes:
        raise VisualEvidenceError(
            "worker_response",
            (
                f"Worker artifact exceeds the configured "
                f"{max_file_bytes:,}-byte limit: {resolved}"
            ),
        )
    if _sha256_file(resolved) != artifact.sha256:
        raise VisualEvidenceError(
            "worker_response",
            f"Worker artifact hash is invalid: {resolved}",
        )


def _allowed_path(
    value: Path,
    allowed_roots: tuple[Path, ...],
    *,
    role: str,
) -> Path:
    raw = str(value)
    if "://" in raw or raw.startswith(("http:", "https:", "ftp:")):
        raise VisualEvidenceError(
            "worker_network_unsupported",
            f"URL fetching is unsupported for the visual worker: {raw}",
        )
    resolved = value.expanduser().resolve()
    if not _is_within(resolved, allowed_roots):
        raise VisualEvidenceError(
            "worker_path",
            f"Isolated visual-evidence {role} escapes allowed roots: {resolved}",
            path=resolved,
        )
    return resolved


def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_hash(value: str, role: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise VisualEvidenceError(
            "worker_response",
            f"Worker returned an invalid {role} SHA-256.",
        )


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must be a JSON object.",
        )
    return value


def _sequence(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must be a JSON array.",
        )
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must be a string.",
        )
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must be an integer.",
        )
    return value


def _number(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must be a finite number.",
        )
    return float(value)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must be a boolean.",
        )
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    return tuple(_string(item, name) for item in _sequence(value, name))


def _number_triplet(
    value: object,
    name: str,
) -> tuple[float, float, float]:
    items = tuple(_number(item, name) for item in _sequence(value, name))
    if len(items) != 3:
        raise VisualEvidenceError(
            "worker_protocol",
            f"{name} must contain three numbers.",
        )
    return items  # type: ignore[return-value]
