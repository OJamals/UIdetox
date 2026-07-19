"""Build deterministic visual evidence from local PNG files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from uidetox.state import get_project_root, get_uidetox_dir
from uidetox.visual_evidence import (
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    build_visual_evidence,
)
from uidetox.visual_worker_client import build_visual_evidence_isolated
from uidetox.visual_worker_protocol import VisualWorkerPolicy


def _viewport(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    try:
        width_text, height_text = value.lower().split("x", maxsplit=1)
        width = int(width_text)
        height = int(height_text)
    except (TypeError, ValueError) as error:
        raise VisualEvidenceError(
            "invalid_request",
            "Viewport must use WIDTHxHEIGHT, for example 1280x800.",
        ) from error
    if width <= 0 or height <= 0:
        raise VisualEvidenceError(
            "invalid_request",
            "Viewport width and height must be positive.",
        )
    return (width, height)


def _value_or_default(value: object | None, default: object) -> object:
    return default if value is None else value


def _local_image_path(value: str) -> Path:
    normalized = value.strip().lower()
    if normalized.startswith(("http:", "https:", "ftp:", "data:")):
        raise VisualEvidenceError(
            "invalid_request",
            f"URL fetching is unsupported; provide a local file: {value}",
        )
    return Path(value).expanduser().resolve()


def _worker_policy(args: argparse.Namespace) -> VisualWorkerPolicy:
    roots = tuple(
        Path(value).expanduser().resolve()
        for value in (args.allowed_root or (get_project_root(),))
    )
    return VisualWorkerPolicy(
        allowed_roots=roots,
        timeout_seconds=float(_value_or_default(args.worker_timeout, 30.0)),
        max_request_bytes=int(
            _value_or_default(args.worker_max_request_bytes, 256 * 1024)
        ),
        max_output_bytes=int(
            _value_or_default(
                args.worker_max_output_bytes,
                4 * 1024 * 1024,
            )
        ),
        max_stderr_bytes=int(
            _value_or_default(args.worker_max_stderr_bytes, 64 * 1024)
        ),
        max_memory_bytes=int(_value_or_default(args.worker_max_memory_mb, 1024))
        * 1024
        * 1024,
        max_file_bytes=int(
            _value_or_default(
                args.worker_max_file_bytes,
                128 * 1024 * 1024,
            )
        ),
        cpu_seconds=int(_value_or_default(args.worker_cpu_seconds, 30)),
    )


def run(args: argparse.Namespace) -> None:
    """Compare two local PNGs in-process or in a bounded worker."""

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else get_uidetox_dir() / "visual-evidence"
    )
    manifest_path = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest
        else output_dir / "manifest.json"
    )
    try:
        request = VisualEvidenceRequest(
            comparisons=(
                VisualEvidenceCase(
                    case_id=args.case_id,
                    before_path=_local_image_path(args.before),
                    after_path=_local_image_path(args.after),
                    viewport=_viewport(args.viewport),
                ),
            ),
            output_dir=output_dir,
            manifest_path=manifest_path,
            threshold=args.threshold,
            max_pixels=args.max_pixels,
            color_policy=args.color_policy,
            reviewer_artifacts=args.reviewer_artifacts,
            crop_padding=args.crop_padding,
            png_compress_level=args.png_compress_level,
            png_optimize=args.png_optimize,
        )
        manifest = (
            build_visual_evidence_isolated(
                request,
                policy=_worker_policy(args),
            )
            if args.isolated
            else build_visual_evidence(request)
        )
    except VisualEvidenceError as error:
        print(f"Visual evidence failed [{error.code}]: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    if args.json:
        print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
        return
    comparison = manifest.comparisons[0]
    print(f"Visual evidence: {manifest.status}")
    print(f"Manifest: {manifest_path}")
    print(
        "Changed-pixel coverage: "
        f"{comparison.metrics.change_percentage}% "
        f"({comparison.metrics.coverage_band})"
    )
    print(
        "Process isolation: "
        + ("enabled (not an OS sandbox)" if args.isolated else "disabled")
    )
