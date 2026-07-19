"""Safe, deterministic pixel evidence built on optional Pillow support.

The public boundary is deliberately Pillow-free: callers submit paths and receive
immutable metadata. Image objects never escape this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import warnings
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from uidetox.utils import now_iso


VISUAL_EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_PIXEL_THRESHOLD = 30
DEFAULT_MAX_PIXELS = 40_000_000
DEFAULT_DIFF_AMPLIFICATION = 8
_PNG_FORMAT = "PNG"
_NORMALIZED_MODE = "RGB"
_CASE_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_ICC_TRANSFORM_CACHE: dict[str, Any] = {}
_SRGB_PROFILE: Any | None = None
_CAPTURE_INSTALL_GUIDANCE = (
    "Install capture support with: pip install 'uidetox[capture]'"
)


class VisualEvidenceError(RuntimeError):
    """A structured, actionable visual-evidence failure."""

    def __init__(self, code: str, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass(frozen=True)
class VisualRegion:
    """One explicit semantic or ignored rectangle and its evidence links."""

    region_id: str
    bounds: tuple[float, float, float, float]
    kind: str
    provenance: str
    reason: str = ""
    source_targets: tuple[str, ...] = ()
    intent_fields: tuple[str, ...] = ()
    preserve_contracts: tuple[str, ...] = ()


@dataclass(frozen=True)
class VisualEvidenceCase:
    """One before/after comparison within a visual-evidence request."""

    case_id: str
    before_path: Path
    after_path: Path
    viewport: tuple[int, int] | None = None
    semantic_regions: tuple[VisualRegion, ...] = ()
    ignore_regions: tuple[VisualRegion, ...] = ()


@dataclass(frozen=True)
class VisualEvidenceRequest:
    """Pillow-free request for one or more exact visual comparisons."""

    comparisons: tuple[VisualEvidenceCase, ...]
    output_dir: Path
    manifest_path: Path | None = None
    threshold: int = DEFAULT_PIXEL_THRESHOLD
    max_pixels: int = DEFAULT_MAX_PIXELS
    amplification: int = DEFAULT_DIFF_AMPLIFICATION
    alpha_background: tuple[int, int, int] = (255, 255, 255)
    dimension_policy: str = "strict"
    color_policy: str = "native"
    reviewer_artifacts: bool = False
    crop_padding: int = 16
    expected_viewports: tuple[str, ...] = ()
    png_compress_level: int = 6
    png_optimize: bool = False
    context_sha256s: dict[str, str] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageEvidence:
    """Decoded source facts without retaining a live image object."""

    path: Path
    sha256: str
    normalized_sha256: str
    width: int
    height: int
    format: str
    source_mode: str
    normalized_mode: str
    frames: int
    icc_profile_present: bool = False
    color_conversion: str = "native"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "normalized_sha256": self.normalized_sha256,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "source_mode": self.source_mode,
            "normalized_mode": self.normalized_mode,
            "frames": self.frames,
            "icc_profile_present": self.icc_profile_present,
            "color_conversion": self.color_conversion,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ArtifactEvidence:
    """One persisted image artifact."""

    kind: str
    path: Path | None
    sha256: str
    width: int
    height: int
    status: str = "generated"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path) if self.path is not None else None,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class VisualMetrics:
    """Exact comparison measurements; these are not aesthetic quality scores."""

    threshold: int
    raw_pixels_changed: int
    ignored_changed_pixels: int
    ignored_ratio: float
    pixels_changed: int
    total_pixels: int
    change_percentage: float
    changed_ratio: float
    coverage_band: str
    changed_bounds: tuple[int, int, int, int] | None
    changed_bounds_ratio: float
    exact_match: bool
    mean_channel_delta: tuple[float, float, float]
    rms_channel_delta: tuple[float, float, float]
    stddev_channel_delta: tuple[float, float, float]
    extrema: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "raw_pixels_changed": self.raw_pixels_changed,
            "ignored_changed_pixels": self.ignored_changed_pixels,
            "ignored_ratio": self.ignored_ratio,
            "pixels_changed": self.pixels_changed,
            "total_pixels": self.total_pixels,
            "change_percentage": self.change_percentage,
            "changed_ratio": self.changed_ratio,
            "coverage_band": self.coverage_band,
            "changed_bounds": (
                list(self.changed_bounds) if self.changed_bounds is not None else None
            ),
            "changed_bounds_ratio": self.changed_bounds_ratio,
            "exact_match": self.exact_match,
            "mean_channel_delta": list(self.mean_channel_delta),
            "rms_channel_delta": list(self.rms_channel_delta),
            "stddev_channel_delta": list(self.stddev_channel_delta),
            "extrema": [list(bounds) for bounds in self.extrema],
        }


@dataclass(frozen=True)
class VisualComparison:
    """Evidence for one requested before/after case."""

    case_id: str
    viewport: tuple[int, int] | None
    before: ImageEvidence
    after: ImageEvidence
    metrics: VisualMetrics
    regions: tuple["RegionEvidence", ...]
    ignored_regions: tuple["RegionEvidence", ...]
    artifacts: tuple[ArtifactEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "viewport": list(self.viewport) if self.viewport is not None else None,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "metrics": self.metrics.to_dict(),
            "regions": [region.to_dict() for region in self.regions],
            "ignored_regions": [
                region.to_dict() for region in self.ignored_regions
            ],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True)
class RegionEvidence:
    """Measured changed pixels within one clipped explicit region."""

    region_id: str
    kind: str
    requested_bounds: tuple[float, float, float, float]
    bounds: tuple[int, int, int, int]
    pixels_changed: int
    total_pixels: int
    changed_ratio: float
    reason: str
    provenance: str
    source_targets: tuple[str, ...]
    intent_fields: tuple[str, ...]
    preserve_contracts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "kind": self.kind,
            "requested_bounds": list(self.requested_bounds),
            "bounds": list(self.bounds),
            "pixels_changed": self.pixels_changed,
            "total_pixels": self.total_pixels,
            "changed_ratio": self.changed_ratio,
            "reason": self.reason,
            "provenance": self.provenance,
            "source_targets": list(self.source_targets),
            "intent_fields": list(self.intent_fields),
            "preserve_contracts": list(self.preserve_contracts),
        }


@dataclass(frozen=True)
class FreshnessEvidence:
    """Content-addressed inputs used to detect stale visual evidence."""

    request_sha256: str
    source_sha256s: tuple[str, ...]
    context_sha256s: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_sha256": self.request_sha256,
            "source_sha256s": list(self.source_sha256s),
            "context_sha256s": dict(sorted(self.context_sha256s.items())),
        }


@dataclass(frozen=True)
class VisualEvidenceManifest:
    """Versioned result of a complete visual-evidence request."""

    schema_version: int
    generated_at: str
    status: str
    parameters: dict[str, Any]
    comparisons: tuple[VisualComparison, ...]
    freshness: FreshnessEvidence
    context: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[ArtifactEvidence, ...] = field(default_factory=tuple)
    incomplete_viewports: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "status": self.status,
            "parameters": self.parameters,
            "comparisons": [
                comparison.to_dict() for comparison in self.comparisons
            ],
            "freshness": self.freshness.to_dict(),
            "context": self.context,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "incomplete_viewports": list(self.incomplete_viewports),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class VisualEvidenceStatus:
    """Freshness/gate result safe for CLI, workflow, and history consumers."""

    state: str
    ready: bool
    required: bool
    manifest_path: Path
    reasons: tuple[str, ...] = ()
    comparisons: int = 0
    generated_at: str = ""
    reviewer_artifacts: tuple[dict[str, Any], ...] = ()
    top_changed_regions: tuple[dict[str, Any], ...] = ()
    incomplete_viewports: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "ready": self.ready,
            "required": self.required,
            "manifest_path": str(self.manifest_path),
            "reasons": list(self.reasons),
            "comparisons": self.comparisons,
            "generated_at": self.generated_at,
            "reviewer_artifacts": list(self.reviewer_artifacts),
            "top_changed_regions": list(self.top_changed_regions),
            "incomplete_viewports": list(self.incomplete_viewports),
            "warnings": list(self.warnings),
        }


@dataclass
class _LoadedImage:
    """Private decoded image plus its serializable source facts."""

    image: Any
    evidence: ImageEvidence
    warnings: tuple[str, ...] = ()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_sha256(image: Any) -> str:
    digest = hashlib.sha256()
    digest.update(str(image.mode).encode("ascii"))
    digest.update(f"{image.width}x{image.height}".encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()


def _pillow_version() -> str:
    try:
        from PIL import __version__ as pillow_version
    except ImportError as error:
        raise VisualEvidenceError(
            "missing_dependency",
            f"Pillow is required for visual evidence. {_CAPTURE_INSTALL_GUIDANCE}",
        ) from error
    return str(pillow_version)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_save_png(
    image: Any,
    path: Path,
    *,
    compress_level: int = 6,
    optimize: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        image.save(
            temporary,
            format=_PNG_FORMAT,
            compress_level=compress_level,
            optimize=optimize,
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_image(image: Any, image_module: Any, background: tuple[int, int, int]) -> Any:
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    if not has_alpha:
        return image.convert(_NORMALIZED_MODE)
    rgba = image.convert("RGBA")
    backdrop = image_module.new("RGBA", rgba.size, (*background, 255))
    return image_module.alpha_composite(backdrop, rgba).convert(_NORMALIZED_MODE)


def _convert_rgb_to_srgb(
    image: Any,
    icc_profile: object,
) -> tuple[Any, str, tuple[str, ...]]:
    """Convert embedded ICC RGB to sRGB with cached transforms."""

    if not icc_profile:
        return (
            image,
            "assumed_srgb",
            ("sRGB conversion requested but no embedded ICC profile; assumed sRGB.",),
        )
    if not isinstance(icc_profile, bytes):
        return (
            image,
            "native_fallback",
            ("sRGB conversion requested with an invalid ICC profile; used native pixels.",),
        )
    try:
        from PIL import ImageCms
    except ImportError:
        return (
            image,
            "native_fallback",
            ("sRGB conversion requested but ImageCms is unavailable; used native pixels.",),
        )
    try:
        global _SRGB_PROFILE
        if _SRGB_PROFILE is None:
            _SRGB_PROFILE = ImageCms.createProfile("sRGB")
        profile_hash = hashlib.sha256(icc_profile).hexdigest()
        transform = _ICC_TRANSFORM_CACHE.get(profile_hash)
        if transform is None:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
            transform = ImageCms.buildTransformFromOpenProfiles(
                source_profile,
                _SRGB_PROFILE,
                "RGB",
                "RGB",
            )
            _ICC_TRANSFORM_CACHE[profile_hash] = transform
        converted = ImageCms.applyTransform(image, transform)
    except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as error:
        return (
            image,
            "native_fallback",
            (
                "sRGB conversion requested with an invalid ICC profile; "
                f"used native pixels ({error}).",
            ),
        )
    return converted, "icc_to_srgb", ()


def _load_png(
    path: Path,
    *,
    max_pixels: int,
    alpha_background: tuple[int, int, int],
    color_policy: str,
) -> _LoadedImage:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as error:
        raise VisualEvidenceError(
            "missing_dependency",
            f"Pillow is required for visual evidence. {_CAPTURE_INSTALL_GUIDANCE}",
        ) from error

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise VisualEvidenceError(
            "missing_image",
            f"Visual evidence image does not exist: {resolved}",
            path=resolved,
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(resolved) as probe:
                image_format = str(probe.format or "").upper()
                width, height = probe.size
                frames = int(getattr(probe, "n_frames", 1))
                source_mode = str(probe.mode)
                if image_format != _PNG_FORMAT:
                    raise VisualEvidenceError(
                        "unsupported_format",
                        (
                            f"Expected a PNG visual-evidence image, got "
                            f"{image_format or 'unknown'}: {resolved}"
                        ),
                        path=resolved,
                    )
                if frames != 1:
                    raise VisualEvidenceError(
                        "animated_image",
                        (
                            f"Animated or multi-frame images are unsupported "
                            f"({frames} frames): {resolved}"
                        ),
                        path=resolved,
                    )
                pixels = width * height
                if pixels > max_pixels:
                    raise VisualEvidenceError(
                        "image_too_large",
                        (
                            f"Image has {pixels:,} pixels; the configured limit is "
                            f"{max_pixels:,}: {resolved}"
                        ),
                        path=resolved,
                    )
                probe.verify()

            with Image.open(resolved) as decoded:
                decoded.load()
                icc_profile = decoded.info.get("icc_profile")
                normalized = _normalize_image(
                    decoded,
                    Image,
                    alpha_background,
                )
                color_conversion = "native"
                color_warnings: tuple[str, ...] = ()
                if color_policy == "srgb":
                    (
                        normalized,
                        color_conversion,
                        color_warnings,
                    ) = _convert_rgb_to_srgb(normalized, icc_profile)
                normalized = normalized.copy()
    except VisualEvidenceError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise VisualEvidenceError(
            "image_too_large",
            f"Pillow rejected a decompression-bomb image: {resolved}",
            path=resolved,
        ) from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise VisualEvidenceError(
            "invalid_image",
            f"Could not safely decode PNG image {resolved}: {error}",
            path=resolved,
        ) from error

    evidence = ImageEvidence(
        path=resolved,
        sha256=_sha256_file(resolved),
        normalized_sha256=_normalized_sha256(normalized),
        width=width,
        height=height,
        format=image_format,
        source_mode=source_mode,
        normalized_mode=_NORMALIZED_MODE,
        frames=frames,
        icc_profile_present=bool(icc_profile),
        color_conversion=color_conversion,
        warnings=tuple(
            f"{resolved}: {warning}" for warning in color_warnings
        ),
    )
    return _LoadedImage(
        image=normalized,
        evidence=evidence,
        warnings=evidence.warnings,
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


def _safe_case_id(case_id: str) -> str:
    safe = _CASE_ID_PATTERN.sub("-", case_id.strip()).strip("-_")
    if not safe:
        raise VisualEvidenceError(
            "invalid_request",
            "Every visual-evidence comparison needs a non-empty case_id.",
        )
    return safe


def _validate_request(request: VisualEvidenceRequest) -> None:
    if not request.comparisons:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual evidence requires at least one comparison.",
        )
    if not 0 <= request.threshold <= 254:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence threshold must be between 0 and 254.",
        )
    if request.max_pixels <= 0:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence max_pixels must be greater than zero.",
        )
    if not 1 <= request.amplification <= 16:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence amplification must be between 1 and 16.",
        )
    if request.dimension_policy != "strict":
        raise VisualEvidenceError(
            "invalid_request",
            "Only the strict visual-evidence dimension policy is supported.",
        )
    if request.color_policy not in {"native", "srgb"}:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence color policy must be 'native' or 'srgb'.",
        )
    if not 0 <= request.crop_padding <= 256:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence crop padding must be between 0 and 256.",
        )
    if not 0 <= request.png_compress_level <= 9:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence PNG compression level must be between 0 and 9.",
        )
    if any(
        not isinstance(viewport, str) or not viewport.strip()
        for viewport in request.expected_viewports
    ) or len(request.expected_viewports) != len(
        set(request.expected_viewports)
    ):
        raise VisualEvidenceError(
            "invalid_request",
            "Expected viewport names must be non-empty and unique.",
        )
    if (
        not isinstance(request.alpha_background, (tuple, list))
        or len(request.alpha_background) != 3
        or any(
            not isinstance(channel, int)
            or isinstance(channel, bool)
            or not 0 <= channel <= 255
            for channel in request.alpha_background
        )
    ):
        raise VisualEvidenceError(
            "invalid_request",
            (
                "Visual-evidence alpha background must contain exactly three "
                "integer channels between 0 and 255."
            ),
        )
    case_ids = [_safe_case_id(case.case_id) for case in request.comparisons]
    if len(case_ids) != len(set(case_ids)):
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence comparison case_ids must be unique.",
        )
    for case in request.comparisons:
        if case.viewport is not None and (
            len(case.viewport) != 2
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
                for value in case.viewport
            )
        ):
            raise VisualEvidenceError(
                "invalid_request",
                "Visual-evidence viewports require positive integer dimensions.",
            )
        for source_path in (case.before_path, case.after_path):
            normalized_path = str(source_path).strip().lower()
            if normalized_path.startswith(
                ("http:/", "https:/", "ftp:/", "data:")
            ):
                raise VisualEvidenceError(
                    "invalid_request",
                    (
                        "Visual evidence accepts local files only; URL fetching "
                        f"is unsupported: {source_path}"
                    ),
                )
        for region in (*case.semantic_regions, *case.ignore_regions):
            expected_kind = (
                "semantic" if region in case.semantic_regions else "ignore"
            )
            if region.kind != expected_kind:
                raise VisualEvidenceError(
                    "invalid_region",
                    (
                        f"Region {region.region_id!r} must use kind "
                        f"{expected_kind!r} in this collection."
                    ),
                )
            if (
                len(region.bounds) != 4
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    for value in region.bounds
                )
                or float(region.bounds[2]) <= 0
                or float(region.bounds[3]) <= 0
            ):
                raise VisualEvidenceError(
                    "invalid_region",
                    (
                        f"Region {region.region_id!r} requires finite "
                        "(x, y, width, height) bounds with positive size."
                    ),
                )
            if not region.region_id.strip() or not region.provenance.strip():
                raise VisualEvidenceError(
                    "invalid_region",
                    "Visual regions require non-empty id and provenance.",
                )
            if region.kind == "ignore" and not region.reason.strip():
                raise VisualEvidenceError(
                    "invalid_region",
                    f"Ignore region {region.region_id!r} requires a reason.",
                )
    if any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or not value
        for key, value in request.context_sha256s.items()
    ):
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence context hashes require non-empty string keys and values.",
        )
    try:
        json.dumps(
            request.context,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise VisualEvidenceError(
            "invalid_request",
            "Visual-evidence context must be finite JSON data.",
        ) from error


def validate_visual_evidence_request(
    request: VisualEvidenceRequest,
) -> None:
    """Validate a request without importing Pillow or decoding images."""

    _validate_request(request)


def _clip_region(
    region: VisualRegion,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x, y, region_width, region_height = region.bounds
    left = max(0, min(width, math.floor(x)))
    top = max(0, min(height, math.floor(y)))
    right = max(0, min(width, math.ceil(x + region_width)))
    bottom = max(0, min(height, math.ceil(y + region_height)))
    return (left, top, max(left, right), max(top, bottom))


def _rectangle_mask(
    image_module: Any,
    image_draw: Any,
    size: tuple[int, int],
    bounds: tuple[int, int, int, int],
) -> Any:
    mask = image_module.new("L", size, 0)
    left, top, right, bottom = bounds
    if right > left and bottom > top:
        image_draw.Draw(mask).rectangle(
            (left, top, right - 1, bottom - 1),
            fill=255,
        )
    return mask


def _mask_count(mask: Any) -> int:
    return int(mask.histogram()[255])


def _region_evidence(
    region: VisualRegion,
    *,
    bounds: tuple[int, int, int, int],
    changed_mask: Any,
    eligible_mask: Any,
    image_chops: Any,
) -> RegionEvidence:
    changed = _mask_count(image_chops.multiply(changed_mask, eligible_mask))
    total = _mask_count(eligible_mask)
    return RegionEvidence(
        region_id=region.region_id,
        kind=region.kind,
        requested_bounds=tuple(float(value) for value in region.bounds),
        bounds=bounds,
        pixels_changed=changed,
        total_pixels=total,
        changed_ratio=round(changed / total if total else 0.0, 8),
        reason=region.reason,
        provenance=region.provenance,
        source_targets=region.source_targets,
        intent_fields=region.intent_fields,
        preserve_contracts=region.preserve_contracts,
    )


def _saved_artifact(
    *,
    kind: str,
    image: Any,
    path: Path,
    request: VisualEvidenceRequest,
) -> ArtifactEvidence:
    _atomic_save_png(
        image,
        path,
        compress_level=request.png_compress_level,
        optimize=request.png_optimize,
    )
    return ArtifactEvidence(
        kind=kind,
        path=path,
        sha256=_sha256_file(path),
        width=image.width,
        height=image.height,
    )


def _omitted_artifact(kind: str, reason: str) -> ArtifactEvidence:
    return ArtifactEvidence(
        kind=kind,
        path=None,
        sha256="",
        width=0,
        height=0,
        status="omitted",
        reason=reason,
    )


def _reviewer_case_artifacts(
    *,
    case: VisualEvidenceCase,
    before: Any,
    after: Any,
    changed_mask: Any,
    changed_bounds: tuple[int, int, int, int] | None,
    request: VisualEvidenceRequest,
) -> tuple[ArtifactEvidence, ...]:
    try:
        from PIL import Image
    except ImportError as error:
        raise VisualEvidenceError(
            "missing_dependency",
            f"Pillow is required for visual evidence. {_CAPTURE_INSTALL_GUIDANCE}",
        ) from error

    safe_case_id = _safe_case_id(case.case_id)
    blend = Image.blend(before, after, 0.5)
    blend_artifact = _saved_artifact(
        kind="before_after_blend",
        image=blend,
        path=request.output_dir.resolve()
        / f"blend_{safe_case_id}.png",
        request=request,
    )
    if changed_bounds is None:
        for stale_name in (
            f"heat_{safe_case_id}.png",
            f"crop_{safe_case_id}.png",
        ):
            (request.output_dir.resolve() / stale_name).unlink(
                missing_ok=True
            )
        reason = "Omitted because no changed pixels exceeded the threshold."
        return (
            _omitted_artifact("heat_overlay", reason),
            _omitted_artifact("changed_crop", reason),
            blend_artifact,
        )

    heat = Image.new("RGBA", after.size, (255, 72, 32, 0))
    heat.putalpha(changed_mask.point([160 if value else 0 for value in range(256)]))
    overlay = Image.alpha_composite(after.convert("RGBA"), heat).convert("RGB")
    overlay_artifact = _saved_artifact(
        kind="heat_overlay",
        image=overlay,
        path=request.output_dir.resolve()
        / f"heat_{safe_case_id}.png",
        request=request,
    )
    left, top, right, bottom = changed_bounds
    crop_bounds = (
        max(0, left - request.crop_padding),
        max(0, top - request.crop_padding),
        min(after.width, right + request.crop_padding),
        min(after.height, bottom + request.crop_padding),
    )
    crop = overlay.crop(crop_bounds)
    crop_artifact = _saved_artifact(
        kind="changed_crop",
        image=crop,
        path=request.output_dir.resolve()
        / f"crop_{safe_case_id}.png",
        request=request,
    )
    return (overlay_artifact, crop_artifact, blend_artifact)


def _build_contact_sheet(
    loaded: list[tuple[VisualEvidenceCase, _LoadedImage, _LoadedImage]],
    request: VisualEvidenceRequest,
) -> ArtifactEvidence:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as error:
        raise VisualEvidenceError(
            "missing_dependency",
            f"Pillow is required for visual evidence. {_CAPTURE_INSTALL_GUIDANCE}",
        ) from error

    padding = 16
    gap = 12
    label_height = 30
    cell_width = 420
    cell_height = 420
    row_height = label_height + cell_height + gap
    width = padding * 2 + cell_width * 2 + gap
    height = padding * 2 + label_height + len(loaded) * row_height
    sheet = Image.new("RGB", (width, height), (246, 244, 239))
    draw = ImageDraw.Draw(sheet)
    draw.text((padding, padding), "BEFORE", fill=(28, 28, 28))
    draw.text(
        (padding + cell_width + gap, padding),
        "AFTER",
        fill=(28, 28, 28),
    )
    y = padding + label_height
    for case, before, after in loaded:
        viewport = (
            f"{case.viewport[0]}x{case.viewport[1]}"
            if case.viewport is not None
            else f"{before.evidence.width}x{before.evidence.height}"
        )
        label = f"{case.case_id} · {viewport}"
        draw.rectangle(
            (padding, y, width - padding, y + label_height),
            fill=(28, 28, 28),
        )
        draw.text(
            (padding + 8, y + 8),
            label,
            fill=(246, 244, 239),
        )
        image_y = y + label_height
        for column, source in enumerate((before.image, after.image)):
            preview = source
            if case.viewport is not None:
                preview = source.crop(
                    (
                        0,
                        0,
                        min(source.width, case.viewport[0]),
                        min(source.height, case.viewport[1]),
                    )
                )
            thumb = ImageOps.contain(
                preview,
                (cell_width, cell_height),
                method=Image.Resampling.LANCZOS,
            )
            cell_x = padding + column * (cell_width + gap)
            paste_x = cell_x + (cell_width - thumb.width) // 2
            paste_y = image_y + (cell_height - thumb.height) // 2
            sheet.paste(thumb, (paste_x, paste_y))
        y += row_height
    return _saved_artifact(
        kind="contact_sheet",
        image=sheet,
        path=request.output_dir.resolve() / "contact_sheet.png",
        request=request,
    )


def _compare_images(
    case: VisualEvidenceCase,
    before: _LoadedImage,
    after: _LoadedImage,
    request: VisualEvidenceRequest,
) -> VisualComparison:
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageStat
    except ImportError as error:
        raise VisualEvidenceError(
            "missing_dependency",
            f"Pillow is required for visual evidence. {_CAPTURE_INSTALL_GUIDANCE}",
        ) from error

    before_size = (before.evidence.width, before.evidence.height)
    after_size = (after.evidence.width, after.evidence.height)
    if before_size != after_size:
        raise VisualEvidenceError(
            "dimension_mismatch",
            (
                f"Visual-evidence dimensions differ: "
                f"{before_size[0]}x{before_size[1]} before vs "
                f"{after_size[0]}x{after_size[1]} after for {case.case_id!r}. "
                "Capture both images at the same viewport."
            ),
        )

    diff = ImageChops.difference(before.image, after.image)
    red, green, blue = diff.split()
    channel_sum = ImageChops.add(red, green)
    channel_sum = ImageChops.add(channel_sum, blue)
    threshold_lut = [
        255 if value > request.threshold else 0 for value in range(256)
    ]
    changed_mask = channel_sum.point(threshold_lut, mode="L")
    raw_pixels_changed = _mask_count(changed_mask)
    total_pixels = before.evidence.width * before.evidence.height
    image_size = (before.evidence.width, before.evidence.height)
    ignore_mask = Image.new("L", image_size, 0)
    clipped_ignore_regions: list[
        tuple[VisualRegion, tuple[int, int, int, int], Any]
    ] = []
    for region in case.ignore_regions:
        bounds = _clip_region(region, *image_size)
        mask = _rectangle_mask(Image, ImageDraw, image_size, bounds)
        ignore_mask = ImageChops.lighter(ignore_mask, mask)
        clipped_ignore_regions.append((region, bounds, mask))
    eligible_mask = ImageChops.invert(ignore_mask)
    effective_changed_mask = ImageChops.multiply(changed_mask, eligible_mask)
    pixels_changed = _mask_count(effective_changed_mask)
    ignored_changed_pixels = raw_pixels_changed - pixels_changed
    changed_ratio = pixels_changed / total_pixels if total_pixels else 0.0
    raw_percentage = (
        changed_ratio * 100 if total_pixels else 0.0
    )
    changed_bounds = effective_changed_mask.getbbox()
    changed_bounds_area = (
        (changed_bounds[2] - changed_bounds[0])
        * (changed_bounds[3] - changed_bounds[1])
        if changed_bounds is not None
        else 0
    )
    if _mask_count(eligible_mask):
        statistics = ImageStat.Stat(diff, mask=eligible_mask)
        mean_delta = tuple(round(float(value), 4) for value in statistics.mean)
        rms_delta = tuple(round(float(value), 4) for value in statistics.rms)
        stddev_delta = tuple(
            round(float(value), 4) for value in statistics.stddev
        )
    else:
        mean_delta = rms_delta = stddev_delta = (0.0, 0.0, 0.0)
    extrema = tuple(
        (int(bounds[0]), int(bounds[1])) for bounds in diff.getextrema()
    )

    visible_diff = diff.point(
        lambda value: min(255, value * request.amplification)
    )
    safe_case_id = _safe_case_id(case.case_id)
    artifact_path = request.output_dir.resolve() / f"diff_{safe_case_id}.png"
    artifact = _saved_artifact(
        kind="amplified_diff",
        image=visible_diff,
        path=artifact_path,
        request=request,
    )
    regions: list[RegionEvidence] = []
    for region in case.semantic_regions:
        bounds = _clip_region(region, *image_size)
        region_mask = _rectangle_mask(Image, ImageDraw, image_size, bounds)
        region_eligible_mask = ImageChops.multiply(region_mask, eligible_mask)
        regions.append(
            _region_evidence(
                region,
                bounds=bounds,
                changed_mask=effective_changed_mask,
                eligible_mask=region_eligible_mask,
                image_chops=ImageChops,
            )
        )
    ignored_regions = tuple(
        _region_evidence(
            region,
            bounds=bounds,
            changed_mask=changed_mask,
            eligible_mask=mask,
            image_chops=ImageChops,
        )
        for region, bounds, mask in clipped_ignore_regions
    )
    artifacts = [artifact]
    if request.reviewer_artifacts:
        artifacts.extend(
            _reviewer_case_artifacts(
                case=case,
                before=before.image,
                after=after.image,
                changed_mask=effective_changed_mask,
                changed_bounds=changed_bounds,
                request=request,
            )
        )
    return VisualComparison(
        case_id=case.case_id,
        viewport=case.viewport,
        before=before.evidence,
        after=after.evidence,
        metrics=VisualMetrics(
            threshold=request.threshold,
            raw_pixels_changed=raw_pixels_changed,
            ignored_changed_pixels=ignored_changed_pixels,
            ignored_ratio=round(
                ignored_changed_pixels / raw_pixels_changed
                if raw_pixels_changed
                else 0.0,
                8,
            ),
            pixels_changed=pixels_changed,
            total_pixels=total_pixels,
            change_percentage=round(raw_percentage, 2),
            changed_ratio=round(changed_ratio, 8),
            coverage_band=_coverage_band(raw_percentage),
            changed_bounds=changed_bounds,
            changed_bounds_ratio=round(
                changed_bounds_area / total_pixels if total_pixels else 0.0,
                8,
            ),
            exact_match=diff.getbbox() is None,
            mean_channel_delta=mean_delta,  # type: ignore[arg-type]
            rms_channel_delta=rms_delta,  # type: ignore[arg-type]
            stddev_channel_delta=stddev_delta,  # type: ignore[arg-type]
            extrema=extrema,  # type: ignore[arg-type]
        ),
        regions=tuple(regions),
        ignored_regions=ignored_regions,
        artifacts=tuple(artifacts),
    )


def build_visual_evidence(
    request: VisualEvidenceRequest,
) -> VisualEvidenceManifest:
    """Build exact visual evidence and optionally persist its atomic manifest."""

    _validate_request(request)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    pillow_version = _pillow_version()

    loaded: list[tuple[VisualEvidenceCase, _LoadedImage, _LoadedImage]] = []
    for case in request.comparisons:
        before = _load_png(
            case.before_path,
            max_pixels=request.max_pixels,
            alpha_background=request.alpha_background,
            color_policy=request.color_policy,
        )
        after = _load_png(
            case.after_path,
            max_pixels=request.max_pixels,
            alpha_background=request.alpha_background,
            color_policy=request.color_policy,
        )
        loaded.append((case, before, after))

    comparisons = tuple(
        _compare_images(case, before, after, request)
        for case, before, after in loaded
    )
    source_sha256s = tuple(
        image.sha256
        for comparison in comparisons
        for image in (comparison.before, comparison.after)
    )
    manifest_artifacts = (
        (_build_contact_sheet(loaded, request),)
        if request.reviewer_artifacts
        else ()
    )
    completed_viewports = {case.case_id for case in request.comparisons}
    incomplete_viewports = tuple(
        viewport
        for viewport in request.expected_viewports
        if viewport not in completed_viewports
    )
    manifest_warnings = tuple(
        dict.fromkeys(
            warning
            for _, before, after in loaded
            for warning in (*before.warnings, *after.warnings)
        )
    )
    parameters: dict[str, Any] = {
        "algorithm": "rgb-sum-v1",
        "pillow_version": pillow_version,
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
    freshness_payload = {
        "schema_version": VISUAL_EVIDENCE_SCHEMA_VERSION,
        "parameters": parameters,
        "context_sha256s": dict(sorted(request.context_sha256s.items())),
        "comparisons": [
            {
                "case_id": comparison.case_id,
                "viewport": comparison.viewport,
                "before_sha256": comparison.before.sha256,
                "after_sha256": comparison.after.sha256,
                "regions": [
                    _region_request_payload(region.to_dict())
                    for region in comparison.regions
                ],
                "ignored_regions": [
                    _region_request_payload(region.to_dict())
                    for region in comparison.ignored_regions
                ],
            }
            for comparison in comparisons
        ],
    }
    manifest = VisualEvidenceManifest(
        schema_version=VISUAL_EVIDENCE_SCHEMA_VERSION,
        generated_at=now_iso(),
        status="complete",
        parameters=parameters,
        comparisons=comparisons,
        freshness=FreshnessEvidence(
            request_sha256=_canonical_sha256(freshness_payload),
            source_sha256s=source_sha256s,
            context_sha256s=dict(sorted(request.context_sha256s.items())),
        ),
        context=request.context,
        artifacts=manifest_artifacts,
        incomplete_viewports=incomplete_viewports,
        warnings=manifest_warnings,
    )
    if request.manifest_path is not None:
        _atomic_write_json(request.manifest_path, manifest.to_dict())
    return manifest


def write_visual_evidence_manifest(
    path: Path,
    manifest: VisualEvidenceManifest,
) -> None:
    """Persist an existing manifest atomically."""

    _atomic_write_json(path, manifest.to_dict())


def _request_hash_from_payload(payload: dict[str, Any]) -> str:
    comparisons = payload.get("comparisons")
    freshness = payload.get("freshness")
    if not isinstance(comparisons, list) or not isinstance(freshness, dict):
        raise ValueError("missing comparisons or freshness object")
    request_payload = {
        "schema_version": payload.get("schema_version"),
        "parameters": payload.get("parameters"),
        "context_sha256s": freshness.get("context_sha256s", {}),
        "comparisons": [
            {
                "case_id": comparison.get("case_id"),
                "viewport": comparison.get("viewport"),
                "before_sha256": dict(comparison.get("before", {})).get("sha256"),
                "after_sha256": dict(comparison.get("after", {})).get("sha256"),
                "regions": [
                    _region_request_payload(region)
                    for region in comparison.get("regions", [])
                    if isinstance(region, dict)
                ],
                "ignored_regions": [
                    _region_request_payload(region)
                    for region in comparison.get("ignored_regions", [])
                    if isinstance(region, dict)
                ],
            }
            for comparison in comparisons
            if isinstance(comparison, dict)
        ],
    }
    return _canonical_sha256(request_payload)


def visual_evidence_request_hash_from_payload(
    payload: dict[str, Any],
) -> str:
    """Reconstruct the canonical input hash at a process trust boundary."""

    return _request_hash_from_payload(payload)


def _region_request_payload(region: dict[str, Any]) -> dict[str, Any]:
    """Select immutable region inputs while excluding measured output fields."""

    return {
        "region_id": region.get("region_id"),
        "kind": region.get("kind"),
        "requested_bounds": region.get(
            "requested_bounds",
            region.get("bounds"),
        ),
        "reason": region.get("reason"),
        "provenance": region.get("provenance"),
        "source_targets": region.get("source_targets", []),
        "intent_fields": region.get("intent_fields", []),
        "preserve_contracts": region.get("preserve_contracts", []),
    }


def inspect_visual_evidence(
    manifest_path: Path,
    *,
    required: bool = False,
    expected_parameters: dict[str, Any] | None = None,
    expected_context_sha256s: dict[str, str] | None = None,
) -> VisualEvidenceStatus:
    """Validate manifest integrity and freshness without importing Pillow."""

    resolved = manifest_path.expanduser().resolve()
    if not resolved.is_file():
        return VisualEvidenceStatus(
            state="missing",
            ready=not required,
            required=required,
            manifest_path=resolved,
            reasons=("visual evidence manifest is missing",),
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return VisualEvidenceStatus(
            state="blocked",
            ready=False,
            required=required,
            manifest_path=resolved,
            reasons=(f"visual evidence manifest is unreadable: {error}",),
        )
    if not isinstance(payload, dict):
        return VisualEvidenceStatus(
            state="blocked",
            ready=False,
            required=required,
            manifest_path=resolved,
            reasons=("visual evidence manifest root must be an object",),
        )

    blocking: list[str] = []
    stale: list[str] = []
    if payload.get("schema_version") != VISUAL_EVIDENCE_SCHEMA_VERSION:
        blocking.append(
            (
                f"unsupported visual evidence schema "
                f"{payload.get('schema_version')!r}"
            )
        )
    if payload.get("status") != "complete":
        blocking.append("visual evidence manifest is not complete")
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        blocking.append("visual evidence manifest has no comparisons")
        comparisons = []
    freshness = payload.get("freshness")
    if not isinstance(freshness, dict):
        blocking.append("visual evidence freshness object is missing")
        freshness = {}
    try:
        actual_request_hash = _request_hash_from_payload(payload)
    except (TypeError, ValueError) as error:
        blocking.append(f"visual evidence request hash cannot be validated: {error}")
    else:
        if freshness.get("request_sha256") != actual_request_hash:
            blocking.append("visual evidence request hash does not match manifest")

    parameters = payload.get("parameters")
    if expected_parameters:
        if not isinstance(parameters, dict):
            blocking.append("visual evidence parameters object is missing")
        else:
            for key, expected in expected_parameters.items():
                if parameters.get(key) != expected:
                    stale.append(
                        f"visual evidence parameter {key!r} changed"
                    )
    stored_context = freshness.get("context_sha256s", {})
    if not isinstance(stored_context, dict):
        blocking.append("visual evidence context hashes are malformed")
        stored_context = {}
    expected_context = expected_context_sha256s or {}
    if expected_context_sha256s is not None:
        missing_current_keys = sorted(set(stored_context) - set(expected_context))
        for key in missing_current_keys:
            stale.append(
                f"visual evidence context {key!r} is no longer available"
            )
    for key, expected in expected_context.items():
        if stored_context.get(key) != expected:
            stale.append(f"visual evidence context {key!r} changed")

    reviewer_artifacts: list[dict[str, Any]] = []
    changed_regions: list[dict[str, Any]] = []

    def inspect_artifact_record(
        artifact: object,
        *,
        case_id: str | None,
    ) -> None:
        if not isinstance(artifact, dict):
            blocking.append("visual evidence artifact is malformed")
            return
        kind = str(artifact.get("kind", ""))
        status = str(artifact.get("status", "generated"))
        summary = {
            "case_id": case_id,
            "kind": kind,
            "status": status,
            "path": artifact.get("path"),
            "reason": str(artifact.get("reason", "")),
        }
        reviewer_artifacts.append(summary)
        if status == "omitted":
            if not summary["reason"]:
                blocking.append(
                    f"omitted visual evidence artifact {kind!r} lacks a reason"
                )
            return
        if status != "generated":
            blocking.append(
                f"visual evidence artifact {kind!r} has invalid status {status!r}"
            )
            return
        path_value = artifact.get("path")
        if not isinstance(path_value, str) or not path_value:
            blocking.append(
                f"visual evidence artifact {kind!r} has no path"
            )
            return
        path = Path(path_value).expanduser()
        if not path.is_file():
            stale.append(f"visual evidence artifact is missing: {path}")
        elif _sha256_file(path) != artifact.get("sha256"):
            stale.append(f"visual evidence artifact hash changed: {path}")

    for comparison in comparisons:
        if not isinstance(comparison, dict):
            blocking.append("visual evidence comparison is malformed")
            continue
        case_id = str(comparison.get("case_id", ""))
        for role in ("before", "after"):
            image = comparison.get(role)
            if not isinstance(image, dict):
                blocking.append(f"visual evidence {role} image record is missing")
                continue
            path = Path(str(image.get("path", ""))).expanduser()
            if not path.is_file():
                stale.append(f"visual evidence {role} source is missing: {path}")
            else:
                try:
                    actual_hash = _sha256_file(path)
                except OSError as error:
                    stale.append(
                        f"visual evidence {role} source cannot be read: {error}"
                    )
                else:
                    if actual_hash != image.get("sha256"):
                        stale.append(
                            f"visual evidence {role} source hash changed: {path}"
                        )
        artifacts = comparison.get("artifacts", [])
        if not isinstance(artifacts, list):
            blocking.append("visual evidence artifacts record is malformed")
            continue
        for artifact in artifacts:
            inspect_artifact_record(artifact, case_id=case_id)
        regions = comparison.get("regions", [])
        if isinstance(regions, list):
            for region in regions:
                if not isinstance(region, dict):
                    continue
                pixels_changed = region.get("pixels_changed", 0)
                changed_ratio = region.get("changed_ratio", 0.0)
                if not isinstance(pixels_changed, (int, float)):
                    pixels_changed = 0
                if not isinstance(changed_ratio, (int, float)):
                    changed_ratio = 0.0
                changed_regions.append(
                    {
                        "case_id": case_id,
                        "region_id": str(region.get("region_id", "")),
                        "pixels_changed": int(pixels_changed),
                        "changed_ratio": float(changed_ratio),
                        "source_targets": list(
                            region.get("source_targets", [])
                        ),
                        "intent_fields": list(
                            region.get("intent_fields", [])
                        ),
                        "preserve_contracts": list(
                            region.get("preserve_contracts", [])
                        ),
                    }
                )

    manifest_artifacts = payload.get("artifacts", [])
    if not isinstance(manifest_artifacts, list):
        blocking.append("visual evidence manifest artifacts are malformed")
    else:
        for artifact in manifest_artifacts:
            inspect_artifact_record(artifact, case_id=None)
    incomplete_viewports = payload.get("incomplete_viewports", [])
    if (
        not isinstance(incomplete_viewports, list)
        or any(not isinstance(item, str) for item in incomplete_viewports)
    ):
        blocking.append("visual evidence incomplete viewport list is malformed")
        incomplete_viewports = []
    manifest_warnings = payload.get("warnings", [])
    if (
        not isinstance(manifest_warnings, list)
        or any(not isinstance(item, str) for item in manifest_warnings)
    ):
        blocking.append("visual evidence warning list is malformed")
        manifest_warnings = []
    top_changed_regions = tuple(
        sorted(
            changed_regions,
            key=lambda region: (
                -region["pixels_changed"],
                -region["changed_ratio"],
                region["case_id"],
                region["region_id"],
            ),
        )[:5]
    )

    if blocking:
        state = "blocked"
        reasons = tuple(dict.fromkeys((*blocking, *stale)))
    elif stale:
        state = "stale"
        reasons = tuple(dict.fromkeys(stale))
    else:
        state = "fresh"
        reasons = ()
    return VisualEvidenceStatus(
        state=state,
        ready=state == "fresh" or (state == "missing" and not required),
        required=required,
        manifest_path=resolved,
        reasons=reasons,
        comparisons=len(comparisons),
        generated_at=str(payload.get("generated_at", "")),
        reviewer_artifacts=tuple(reviewer_artifacts),
        top_changed_regions=top_changed_regions,
        incomplete_viewports=tuple(incomplete_viewports),
        warnings=tuple(manifest_warnings),
    )
