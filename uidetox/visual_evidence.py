"""Safe, deterministic pixel evidence built on optional Pillow support.

The public boundary is deliberately Pillow-free: callers submit paths and receive
immutable metadata. Image objects never escape this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from dataclasses import dataclass, field
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
class VisualEvidenceCase:
    """One before/after comparison within a visual-evidence request."""

    case_id: str
    before_path: Path
    after_path: Path
    viewport: tuple[int, int] | None = None


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
        }


@dataclass(frozen=True)
class ArtifactEvidence:
    """One persisted image artifact."""

    kind: str
    path: Path
    sha256: str
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class VisualMetrics:
    """Exact comparison measurements; these are not aesthetic quality scores."""

    threshold: int
    pixels_changed: int
    total_pixels: int
    change_percentage: float
    changed_ratio: float
    severity: str
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
            "pixels_changed": self.pixels_changed,
            "total_pixels": self.total_pixels,
            "change_percentage": self.change_percentage,
            "changed_ratio": self.changed_ratio,
            "severity": self.severity,
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
    artifacts: tuple[ArtifactEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "viewport": list(self.viewport) if self.viewport is not None else None,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "metrics": self.metrics.to_dict(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True)
class FreshnessEvidence:
    """Content-addressed inputs used to detect stale visual evidence."""

    request_sha256: str
    source_sha256s: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_sha256": self.request_sha256,
            "source_sha256s": list(self.source_sha256s),
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
            "warnings": list(self.warnings),
        }


@dataclass
class _LoadedImage:
    """Private decoded image plus its serializable source facts."""

    image: Any
    evidence: ImageEvidence


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


def _atomic_save_png(image: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        image.save(temporary, format=_PNG_FORMAT)
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


def _load_png(
    path: Path,
    *,
    max_pixels: int,
    alpha_background: tuple[int, int, int],
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
                normalized = _normalize_image(
                    decoded,
                    Image,
                    alpha_background,
                ).copy()
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
    )
    return _LoadedImage(image=normalized, evidence=evidence)


def _severity(change_percentage: float) -> str:
    if change_percentage < 0.1:
        return "none"
    if change_percentage < 5:
        return "minor"
    if change_percentage < 20:
        return "moderate"
    if change_percentage < 50:
        return "major"
    return "complete_redesign"


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


def _compare_images(
    case: VisualEvidenceCase,
    before: _LoadedImage,
    after: _LoadedImage,
    request: VisualEvidenceRequest,
) -> VisualComparison:
    try:
        from PIL import ImageChops, ImageStat
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
    histogram = changed_mask.histogram()
    pixels_changed = int(histogram[255])
    total_pixels = before.evidence.width * before.evidence.height
    changed_ratio = pixels_changed / total_pixels if total_pixels else 0.0
    raw_percentage = (
        changed_ratio * 100 if total_pixels else 0.0
    )
    changed_bounds = changed_mask.getbbox()
    changed_bounds_area = (
        (changed_bounds[2] - changed_bounds[0])
        * (changed_bounds[3] - changed_bounds[1])
        if changed_bounds is not None
        else 0
    )
    statistics = ImageStat.Stat(diff)
    mean_delta = tuple(round(float(value), 4) for value in statistics.mean)
    rms_delta = tuple(round(float(value), 4) for value in statistics.rms)
    stddev_delta = tuple(round(float(value), 4) for value in statistics.stddev)
    extrema = tuple(
        (int(bounds[0]), int(bounds[1])) for bounds in diff.getextrema()
    )

    visible_diff = diff.point(
        lambda value: min(255, value * request.amplification)
    )
    safe_case_id = _safe_case_id(case.case_id)
    artifact_path = request.output_dir.resolve() / f"diff_{safe_case_id}.png"
    _atomic_save_png(visible_diff, artifact_path)
    artifact = ArtifactEvidence(
        kind="amplified_diff",
        path=artifact_path,
        sha256=_sha256_file(artifact_path),
        width=visible_diff.width,
        height=visible_diff.height,
    )
    return VisualComparison(
        case_id=case.case_id,
        viewport=case.viewport,
        before=before.evidence,
        after=after.evidence,
        metrics=VisualMetrics(
            threshold=request.threshold,
            pixels_changed=pixels_changed,
            total_pixels=total_pixels,
            change_percentage=round(raw_percentage, 2),
            changed_ratio=round(changed_ratio, 8),
            severity=_severity(raw_percentage),
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
        artifacts=(artifact,),
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
        )
        after = _load_png(
            case.after_path,
            max_pixels=request.max_pixels,
            alpha_background=request.alpha_background,
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
    parameters: dict[str, Any] = {
        "algorithm": "rgb-sum-v1",
        "pillow_version": pillow_version,
        "threshold": request.threshold,
        "max_pixels": request.max_pixels,
        "amplification": request.amplification,
        "alpha_background": list(request.alpha_background),
    }
    freshness_payload = {
        "schema_version": VISUAL_EVIDENCE_SCHEMA_VERSION,
        "parameters": parameters,
        "comparisons": [
            {
                "case_id": comparison.case_id,
                "viewport": comparison.viewport,
                "before_sha256": comparison.before.sha256,
                "after_sha256": comparison.after.sha256,
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
        ),
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
