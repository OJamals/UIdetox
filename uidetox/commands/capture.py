"""Capture command: use Playwright to take before/after screenshots for visual regression."""

import argparse
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

from uidetox.frontend_map import FRONTEND_MAP_FILE
from uidetox.runtime_observer import (
    RuntimeObservation,
    RuntimePage,
    RuntimeViewport,
    observe_frontend,
)
from uidetox.state import (
    ensure_uidetox_dir,
    get_project_root,
    get_uidetox_dir,
    load_config,
)
from uidetox.utils import now_iso
from uidetox.visual_evidence import (
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    build_visual_evidence,
)
from uidetox.visual_worker_client import build_visual_evidence_isolated
from uidetox.visual_worker_protocol import VisualWorkerPolicy
from uidetox.visual_semantics import (
    explicit_ignore_regions,
    load_project_visual_context,
    semantic_regions_from_runtime,
)


_CAPTURE_INSTALL_GUIDANCE = (
    "Install capture support with: pip install 'uidetox[capture]'\n"
    "Install Chromium with: python -m playwright install chromium"
)
_RESPONSIVE_VIEWPORTS = (
    ("mobile", 375, 812),
    ("tablet", 768, 1024),
    ("desktop", 1280, 800),
    ("wide", 1920, 1080),
)


def _missing_browser_executable(error: Exception) -> bool:
    """Return whether a Playwright launch error indicates a missing browser."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "executable doesn't exist",
            "executable does not exist",
            "playwright install",
            "browser executable",
        )
    )


def _server_is_reachable(url: str) -> bool:
    """Return True if the URL responds within 3 seconds."""
    try:
        urllib.request.urlopen(url, timeout=3)  # noqa: S310
        return True
    except Exception:
        return False


def _snapshots_dir() -> Path:
    uidetox_dir = ensure_uidetox_dir()
    d = uidetox_dir / "snapshots"
    d.mkdir(exist_ok=True)
    return d


def _capture_screenshot(url: str, out_path: Path, full_page: bool = True,
                         viewport: dict | None = None) -> bool:
    """Capture one screenshot through the shared runtime observer.

    Returns True on success, False on failure.
    """
    vp = viewport or {"width": 1280, "height": 800}
    observation = _observe_capture(
        url,
        (
            (
                RuntimeViewport(
                    "desktop",
                    int(vp["width"]),
                    int(vp["height"]),
                ),
                out_path,
            ),
        ),
        full_page=full_page,
    )
    return bool(
        observation is not None
        and any(
            page.screenshot == str(out_path.resolve())
            for page in observation.pages
        )
    )


def _capture_multi_viewport(url: str, prefix: str) -> list[Path]:
    """Capture screenshots at multiple viewport widths for responsive validation."""
    snapshots = _snapshots_dir()
    destinations = tuple(
        (
            RuntimeViewport(name, width, height),
            snapshots / f"{prefix}_{name}.png",
        )
        for name, width, height in _RESPONSIVE_VIEWPORTS
    )
    observation = _observe_capture(url, destinations)
    if observation is None:
        return []
    captured = {
        Path(page.screenshot)
        for page in observation.pages
        if page.screenshot is not None
    }
    ordered: list[Path] = []
    for viewport, out_file in destinations:
        if out_file.resolve() in captured:
            ordered.append(out_file)
            print(
                f"  ✓ {viewport.name} ({viewport.width}x{viewport.height})"
            )
    return ordered


def _observe_capture(
    url: str,
    destinations: tuple[tuple[RuntimeViewport, Path], ...],
    *,
    full_page: bool = True,
) -> RuntimeObservation | None:
    if not destinations:
        return RuntimeObservation(now_iso(), (url,), ())
    roots = {path.parent.resolve() for _, path in destinations}
    if len(roots) != 1:
        raise ValueError("Capture destinations must share one output directory.")
    names = {
        viewport.name: path.name for viewport, path in destinations
    }
    try:
        observation = observe_frontend(
            url,
            viewports=tuple(viewport for viewport, _ in destinations),
            screenshots_dir=next(iter(roots)),
            screenshot_namer=lambda _url, viewport: names[viewport.name],
            timeout_ms=15_000,
            full_page=full_page,
            settle_ms=1_000,
        )
    except RuntimeError as error:
        print(f"❌ Failed to capture screenshot: {error}", file=sys.stderr)
        if _missing_browser_executable(error) or "Playwright unavailable" in str(
            error
        ):
            print(_CAPTURE_INSTALL_GUIDANCE, file=sys.stderr)
        return None
    for error in observation.errors:
        print(f"❌ Failed to capture screenshot: {error}", file=sys.stderr)
    return observation


def _capture_named_stage(
    url: str,
    prefix: str,
    *,
    responsive: bool,
) -> tuple[list[Path], RuntimeObservation | None]:
    snapshots = _snapshots_dir()
    if responsive:
        destinations = tuple(
            (
                RuntimeViewport(name, width, height),
                snapshots / f"{prefix}_{name}.png",
            )
            for name, width, height in _RESPONSIVE_VIEWPORTS
        )
    else:
        destinations = (
            (
                RuntimeViewport("desktop", 1280, 800),
                snapshots / f"{prefix}.png",
            ),
        )
    observation = _observe_capture(url, destinations)
    if observation is None:
        return [], None
    captured_set = {
        Path(page.screenshot)
        for page in observation.pages
        if page.screenshot is not None
    }
    captured = [
        path for _, path in destinations if path.resolve() in captured_set
    ]
    if responsive:
        for viewport, path in destinations:
            if path in captured:
                print(
                    f"  ✓ {viewport.name} ({viewport.width}x{viewport.height})"
                )
    if captured:
        _atomic_write_json(
            snapshots / f"runtime_{prefix}.json",
            observation.to_dict(),
        )
    return captured, observation


def _generate_visual_diff(before_path: Path, after_path: Path) -> dict:
    """Generate a visual diff summary between before and after screenshots.

    Compatibility adapter over the typed visual-evidence engine.
    """
    diff_info = {
        "before": str(before_path),
        "after": str(after_path),
        "timestamp": now_iso(),
    }

    try:
        manifest = build_visual_evidence(
            VisualEvidenceRequest(
                comparisons=(
                    VisualEvidenceCase(
                        case_id=f"{before_path.stem}_{after_path.stem}",
                        before_path=before_path,
                        after_path=after_path,
                    ),
                ),
                output_dir=before_path.parent,
            )
        )
        comparison = manifest.comparisons[0]
        diff_info.update(
            {
                "diff_image": str(comparison.artifacts[0].path),
                "change_percentage": comparison.metrics.change_percentage,
                "pixels_changed": comparison.metrics.pixels_changed,
                "total_pixels": comparison.metrics.total_pixels,
                "coverage_band": comparison.metrics.coverage_band,
            }
        )
    except VisualEvidenceError as error:
        if error.code == "missing_dependency":
            diff_info["note"] = (
                "Pillow not installed — pixel diff unavailable. Compare screenshots "
                f"manually.\n{_CAPTURE_INSTALL_GUIDANCE}"
            )
        else:
            diff_info["error_code"] = error.code
            diff_info["error"] = str(error)
    except Exception as e:
        diff_info["error"] = str(e)

    return diff_info


def _atomic_write_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _viewport_for_case(case_id: str) -> tuple[int, int] | None:
    for name, width, height in _RESPONSIVE_VIEWPORTS:
        if name == case_id:
            return (width, height)
    if case_id == "desktop":
        return (1280, 800)
    return None


def _build_capture_evidence(
    comparisons: list[tuple[str, Path, Path]],
    snapshots: Path,
    *,
    runtime_pages: dict[str, RuntimePage] | None = None,
    config: dict | None = None,
    manifest_path: Path | None = None,
    threshold: int = 30,
    max_pixels: int = 40_000_000,
    dimension_policy: str = "strict",
    color_policy: str = "native",
    reviewer_artifacts: bool = False,
    crop_padding: int = 16,
    expected_viewports: tuple[str, ...] = (),
    png_compress_level: int = 6,
    png_optimize: bool = False,
    worker_policy: VisualWorkerPolicy | None = None,
) -> list[dict]:
    """Build and persist typed evidence, returning legacy summaries for output."""

    active_config = config or {}
    frontend_map, intent, context_hashes, context = load_project_visual_context(
        active_config,
        get_uidetox_dir() / FRONTEND_MAP_FILE,
    )
    pages = runtime_pages or {}
    cases: list[VisualEvidenceCase] = []
    for case_id, before_path, after_path in comparisons:
        page = pages.get(case_id)
        try:
            ignore_regions = (
                explicit_ignore_regions(active_config, page)
                if page is not None
                else ()
            )
        except ValueError as error:
            raise VisualEvidenceError(
                "invalid_request",
                f"Invalid visual-evidence ignore configuration: {error}",
            ) from error
        cases.append(
            VisualEvidenceCase(
                case_id=case_id,
                before_path=before_path,
                after_path=after_path,
                viewport=_viewport_for_case(case_id),
                semantic_regions=(
                    semantic_regions_from_runtime(
                        page,
                        frontend_map=frontend_map,
                        intent=intent,
                    )
                    if page is not None
                    else ()
                ),
                ignore_regions=ignore_regions,
            )
        )
    request = VisualEvidenceRequest(
        comparisons=tuple(cases),
        output_dir=snapshots,
        manifest_path=manifest_path or snapshots / "visual-evidence.json",
        threshold=threshold,
        max_pixels=max_pixels,
        dimension_policy=dimension_policy,
        color_policy=color_policy,
        reviewer_artifacts=reviewer_artifacts,
        crop_padding=crop_padding,
        expected_viewports=expected_viewports,
        png_compress_level=png_compress_level,
        png_optimize=png_optimize,
        context_sha256s=context_hashes,
        context=context,
    )
    manifest = (
        build_visual_evidence_isolated(request, policy=worker_policy)
        if worker_policy is not None
        else build_visual_evidence(request)
    )
    summaries: list[dict] = []
    for comparison in manifest.comparisons:
        summaries.append(
            {
                "before": str(comparison.before.path),
                "after": str(comparison.after.path),
                "timestamp": manifest.generated_at,
                "diff_image": str(comparison.artifacts[0].path),
                "change_percentage": comparison.metrics.change_percentage,
                "pixels_changed": comparison.metrics.pixels_changed,
                "total_pixels": comparison.metrics.total_pixels,
                "coverage_band": comparison.metrics.coverage_band,
                "viewport": comparison.case_id,
            }
        )
    return summaries


def _visual_options(
    args: argparse.Namespace,
    config: dict,
    snapshots: Path,
) -> dict:
    configured = config.get("visual_evidence", {})
    if not isinstance(configured, dict):
        configured = {}
    evidence_file = getattr(args, "evidence_file", None) or configured.get(
        "manifest_path"
    )
    manifest_path = (
        Path(str(evidence_file)).expanduser().resolve()
        if evidence_file
        else snapshots / "visual-evidence.json"
    )
    worker_config = configured.get("worker", {})
    if not isinstance(worker_config, dict):
        worker_config = {}
    isolated = bool(getattr(args, "isolated", False)) or bool(
        configured.get("isolated", False)
    )
    worker_policy = None
    if isolated:
        configured_roots = worker_config.get("allowed_roots", ())
        if not isinstance(configured_roots, (list, tuple)):
            configured_roots = ()
        roots = getattr(args, "allowed_root", None) or configured_roots
        allowed_roots = tuple(
            Path(str(path)).expanduser().resolve()
            for path in (roots or (get_project_root(),))
        )
        worker_policy = VisualWorkerPolicy(
            allowed_roots=allowed_roots,
            timeout_seconds=(
                getattr(args, "worker_timeout", None)
                if getattr(args, "worker_timeout", None) is not None
                else float(worker_config.get("timeout_seconds", 30.0))
            ),
            max_request_bytes=(
                getattr(args, "worker_max_request_bytes", None)
                if getattr(args, "worker_max_request_bytes", None) is not None
                else int(worker_config.get("max_request_bytes", 256 * 1024))
            ),
            max_output_bytes=(
                getattr(args, "worker_max_output_bytes", None)
                if getattr(args, "worker_max_output_bytes", None) is not None
                else int(
                    worker_config.get(
                        "max_output_bytes",
                        4 * 1024 * 1024,
                    )
                )
            ),
            max_stderr_bytes=(
                getattr(args, "worker_max_stderr_bytes", None)
                if getattr(args, "worker_max_stderr_bytes", None) is not None
                else int(worker_config.get("max_stderr_bytes", 64 * 1024))
            ),
            max_memory_bytes=(
                (
                    getattr(args, "worker_max_memory_mb", None)
                    if getattr(args, "worker_max_memory_mb", None) is not None
                    else int(worker_config.get("max_memory_mb", 1024))
                )
                * 1024
                * 1024
            ),
            max_file_bytes=(
                getattr(args, "worker_max_file_bytes", None)
                if getattr(args, "worker_max_file_bytes", None) is not None
                else int(
                    worker_config.get(
                        "max_file_bytes",
                        128 * 1024 * 1024,
                    )
                )
            ),
            cpu_seconds=(
                getattr(args, "worker_cpu_seconds", None)
                if getattr(args, "worker_cpu_seconds", None) is not None
                else int(worker_config.get("cpu_seconds", 30))
            ),
        )
    return {
        "threshold": (
            getattr(args, "threshold", None)
            if getattr(args, "threshold", None) is not None
            else int(configured.get("threshold", 30))
        ),
        "max_pixels": (
            getattr(args, "max_pixels", None)
            if getattr(args, "max_pixels", None) is not None
            else int(configured.get("max_pixels", 40_000_000))
        ),
        "dimension_policy": (
            getattr(args, "dimension_policy", None)
            or str(configured.get("dimension_policy", "strict"))
        ),
        "color_policy": (
            getattr(args, "color_policy", None)
            or str(configured.get("color_policy", "native"))
        ),
        "reviewer_artifacts": (
            bool(getattr(args, "reviewer_artifacts", False))
            or bool(configured.get("reviewer_artifacts", False))
        ),
        "crop_padding": (
            getattr(args, "crop_padding", None)
            if getattr(args, "crop_padding", None) is not None
            else int(configured.get("crop_padding", 16))
        ),
        "png_compress_level": (
            getattr(args, "png_compress_level", None)
            if getattr(args, "png_compress_level", None) is not None
            else int(configured.get("png_compress_level", 6))
        ),
        "png_optimize": (
            bool(getattr(args, "png_optimize", False))
            or bool(configured.get("png_optimize", False))
        ),
        "manifest_path": manifest_path,
        "worker_policy": worker_policy,
    }


def run(args: argparse.Namespace):
    url = getattr(args, "url", None)
    config = load_config()
    if not url:
        url = config.get("dev_server", "http://localhost:3000")

    stage = getattr(args, "stage", None)
    responsive = getattr(args, "responsive", False)

    snapshots = _snapshots_dir()
    visual_options = _visual_options(args, config, snapshots)
    visual_options["expected_viewports"] = (
        tuple(name for name, _, _ in _RESPONSIVE_VIEWPORTS)
        if responsive
        else ("desktop",)
    )

    if not _server_is_reachable(url):
        print(f"❌ Cannot reach {url}", file=sys.stderr)
        print("   ⚠️  uidetox does NOT start your dev server — you must start it first.", file=sys.stderr)
        print(
            "   Start your dev server (e.g. npm run dev / pnpm dev), then re-run capture.",
            file=sys.stderr,
        )
        sys.exit(1)

    if stage == "before":
        # ── Capture BEFORE screenshot (pre-fix baseline) ──
        print(f"📸 Capturing BEFORE screenshot of {url}...")

        captured, _observation = _capture_named_stage(
            url,
            "before",
            responsive=responsive,
        )
        if not captured:
            sys.exit(1)
        if responsive:
            print(f"\n✅ {len(captured)} responsive BEFORE screenshots saved.")
        else:
            out_file = captured[0]
            print(f"✅ BEFORE screenshot saved to {out_file}")

    elif stage == "after":
        # ── Capture AFTER screenshot and generate diff ──
        print(f"📸 Capturing AFTER screenshot of {url}...")

        captured, observation = _capture_named_stage(
            url,
            "after",
            responsive=responsive,
        )
        runtime_pages = {
            page.viewport.name: page
            for page in observation.pages
        } if observation is not None else {}
        if responsive:
            if captured:
                print(f"\n✅ {len(captured)} responsive AFTER screenshots saved.")

                pairs: list[tuple[str, Path, Path]] = []
                for after_path in captured:
                    vp_name = after_path.stem.replace("after_", "")
                    before_path = snapshots / f"before_{vp_name}.png"
                    if before_path.exists():
                        pairs.append((vp_name, before_path, after_path))
                if pairs:
                    print("\n🔍 Generating visual diffs...")
                    try:
                        diffs = _build_capture_evidence(
                            pairs,
                            snapshots,
                            runtime_pages=runtime_pages,
                            config=config,
                            **visual_options,
                        )
                    except VisualEvidenceError as error:
                        if error.code == "missing_dependency":
                            print(f"  ⚠️  {error}")
                            diffs = []
                        else:
                            print(f"❌ Visual evidence failed: {error}", file=sys.stderr)
                            sys.exit(1)
                    for diff in diffs:
                        vp_name = str(diff["viewport"])
                        change_pct = diff.get("change_percentage", "?")
                        coverage_band = diff.get(
                            "coverage_band",
                            "unknown",
                        )
                        print(
                            f"  {vp_name}: {change_pct}% changed-pixel "
                            f"coverage ({coverage_band})"
                        )
                    _atomic_write_json(
                        snapshots / "diff_meta.json",
                        {
                            "schema_version": 1,
                            "comparisons": diffs,
                        },
                    )
            else:
                sys.exit(1)
        else:
            if not captured:
                sys.exit(1)
            out_file = captured[0]
            print(f"✅ AFTER screenshot saved to {out_file}")

            # Generate diff if before exists
            before_file = snapshots / "before.png"
            if before_file.exists():
                print("\n🔍 Generating visual diff...")
                try:
                    diffs = _build_capture_evidence(
                        [("desktop", before_file, out_file)],
                        snapshots,
                        runtime_pages=runtime_pages,
                        config=config,
                        **visual_options,
                    )
                except VisualEvidenceError as error:
                    if error.code == "missing_dependency":
                        print(f"   ⚠️  {error}")
                        diffs = []
                    else:
                        print(f"❌ Visual evidence failed: {error}", file=sys.stderr)
                        sys.exit(1)
                diff = diffs[0] if diffs else {}
                change_pct = diff.get("change_percentage", "?")
                coverage_band = diff.get("coverage_band", "unknown")
                print(
                    f"   Changed-pixel coverage: {change_pct}% "
                    f"({coverage_band})"
                )
                if diff.get("diff_image"):
                    print(f"   Diff image: {diff['diff_image']}")

                if diff:
                    _atomic_write_json(snapshots / "diff_meta.json", diff)
            else:
                print("   ⚠️  No BEFORE screenshot found. Run `uidetox capture --stage before` first.")

        # Copy to latest for review command
        latest = snapshots / "latest.png"
        if responsive:
            after_desktop = snapshots / "after_desktop.png"
            if after_desktop in captured:
                _atomic_copy(after_desktop, latest)
            else:
                latest.unlink(missing_ok=True)
        else:
            _atomic_copy(snapshots / "after.png", latest)

    else:
        # ── Default: single capture (legacy behavior) ──
        print(f"📸 Capturing screenshot of {url}...")
        out_file = snapshots / "latest.png"
        if not _capture_screenshot(url, out_file):
            sys.exit(1)
        print(f"✅ Screenshot saved to {out_file}")
        print()
        print("  TIP: Use `uidetox capture --stage before` and `--stage after`")
        print("  for visual regression validation during the fix loop.")
