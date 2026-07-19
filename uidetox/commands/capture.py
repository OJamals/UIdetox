"""Capture command: use Playwright to take before/after screenshots for visual regression."""

import argparse
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path
from uuid import uuid4

from uidetox.state import ensure_uidetox_dir, load_config
from uidetox.utils import now_iso
from uidetox.visual_evidence import (
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    build_visual_evidence,
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
    """Capture a screenshot using Playwright headless browser.

    Returns True on success, False on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright Python package is not installed.", file=sys.stderr)
        print(_CAPTURE_INSTALL_GUIDANCE, file=sys.stderr)
        return False

    vp = viewport or {"width": 1280, "height": 800}
    temporary = out_path.with_name(f".{out_path.name}.{uuid4().hex}.tmp")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport=vp)
                page.goto(url, wait_until="networkidle", timeout=15000)
                # Wait for animations to settle
                page.wait_for_timeout(1000)
                page.screenshot(
                    path=str(temporary),
                    full_page=full_page,
                    type="png",
                )
                os.replace(temporary, out_path)
            finally:
                browser.close()
        return True
    except Exception as e:
        print(f"❌ Failed to capture screenshot: {e}", file=sys.stderr)
        if _missing_browser_executable(e):
            print(_CAPTURE_INSTALL_GUIDANCE, file=sys.stderr)
        return False
    finally:
        temporary.unlink(missing_ok=True)


def _capture_multi_viewport(url: str, prefix: str) -> list[Path]:
    """Capture screenshots at multiple viewport widths for responsive validation."""
    snapshots = _snapshots_dir()
    captured = []

    for name, width, height in _RESPONSIVE_VIEWPORTS:
        out_file = snapshots / f"{prefix}_{name}.png"
        vp_config = {"width": width, "height": height}
        if _capture_screenshot(url, out_file, viewport=vp_config):
            captured.append(out_file)
            print(f"  ✓ {name} ({width}x{height})")

    return captured


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
                "severity": comparison.metrics.severity,
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
) -> list[dict]:
    """Build and persist typed evidence, returning legacy summaries for output."""

    manifest = build_visual_evidence(
        VisualEvidenceRequest(
            comparisons=tuple(
                VisualEvidenceCase(
                    case_id=case_id,
                    before_path=before_path,
                    after_path=after_path,
                    viewport=_viewport_for_case(case_id),
                )
                for case_id, before_path, after_path in comparisons
            ),
            output_dir=snapshots,
            manifest_path=snapshots / "visual-evidence.json",
        )
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
                "severity": comparison.metrics.severity,
                "viewport": comparison.case_id,
            }
        )
    return summaries


def run(args: argparse.Namespace):
    url = getattr(args, "url", None)
    config = load_config()
    if not url:
        url = config.get("dev_server", "http://localhost:3000")

    stage = getattr(args, "stage", None)
    responsive = getattr(args, "responsive", False)

    snapshots = _snapshots_dir()

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

        if responsive:
            captured = _capture_multi_viewport(url, "before")
            if captured:
                print(f"\n✅ {len(captured)} responsive BEFORE screenshots saved.")
            else:
                sys.exit(1)
        else:
            out_file = snapshots / "before.png"
            if not _capture_screenshot(url, out_file):
                sys.exit(1)
            print(f"✅ BEFORE screenshot saved to {out_file}")

    elif stage == "after":
        # ── Capture AFTER screenshot and generate diff ──
        print(f"📸 Capturing AFTER screenshot of {url}...")

        if responsive:
            captured = _capture_multi_viewport(url, "after")
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
                        diffs = _build_capture_evidence(pairs, snapshots)
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
                        severity = diff.get("severity", "unknown")
                        print(f"  {vp_name}: {change_pct}% change ({severity})")
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
            out_file = snapshots / "after.png"
            if not _capture_screenshot(url, out_file):
                sys.exit(1)
            print(f"✅ AFTER screenshot saved to {out_file}")

            # Generate diff if before exists
            before_file = snapshots / "before.png"
            if before_file.exists():
                print("\n🔍 Generating visual diff...")
                try:
                    diffs = _build_capture_evidence(
                        [("desktop", before_file, out_file)],
                        snapshots,
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
                severity = diff.get("severity", "unknown")
                print(f"   Change: {change_pct}% ({severity})")
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
