"""Capture command: use Playwright to take before/after screenshots for visual regression."""

import argparse
from pathlib import Path
from uidetox.state import ensure_uidetox_dir, load_config
from uidetox.utils import now_iso
import sys


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
        print("❌ Playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
        return False

    vp = viewport or {"width": 1280, "height": 800}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport=vp)
                page.goto(url, wait_until="networkidle", timeout=15000)
                # Wait for animations to settle
                page.wait_for_timeout(1000)
                page.screenshot(path=str(out_path), full_page=full_page)
            finally:
                browser.close()
        return True
    except Exception as e:
        print(f"❌ Failed to capture screenshot: {e}", file=sys.stderr)
        return False


def _capture_multi_viewport(url: str, prefix: str) -> list[Path]:
    """Capture screenshots at multiple viewport widths for responsive validation."""
    viewports = [
        {"name": "mobile", "width": 375, "height": 812},
        {"name": "tablet", "width": 768, "height": 1024},
        {"name": "desktop", "width": 1280, "height": 800},
        {"name": "wide", "width": 1920, "height": 1080},
    ]

    snapshots = _snapshots_dir()
    captured = []

    for vp in viewports:
        out_file = snapshots / f"{prefix}_{vp['name']}.png"
        vp_config = {"width": vp["width"], "height": vp["height"]}
        if _capture_screenshot(url, out_file, viewport=vp_config):
            captured.append(out_file)
            print(f"  ✓ {vp['name']} ({vp['width']}x{vp['height']})")

    return captured


def _generate_visual_diff(before_path: Path, after_path: Path) -> dict:
    """Generate a visual diff summary between before and after screenshots.

    Returns metadata about the visual changes detected.
    """
    diff_info = {
        "before": str(before_path),
        "after": str(after_path),
        "timestamp": now_iso(),
    }

    try:
        # Use Pillow for basic pixel-level diff if available
        from PIL import Image, ImageChops

        before_img = Image.open(before_path)
        after_img = Image.open(after_path)

        # Resize to common size if needed
        if before_img.size != after_img.size:
            target_size = (max(before_img.width, after_img.width),
                          max(before_img.height, after_img.height))
            before_img = before_img.resize(target_size, Image.Resampling.LANCZOS)
            after_img = after_img.resize(target_size, Image.Resampling.LANCZOS)

        diff_img = ImageChops.difference(before_img.convert("RGB"), after_img.convert("RGB"))

        # Calculate change percentage — use NumPy for speed if available,
        # otherwise fall back to Pillow's ImageStat (fast C code).
        try:
            import numpy as np
            diff_array = np.array(diff_img)
            diff_pixels = int(np.sum(np.sum(diff_array, axis=-1) > 30))
            total_pixels = diff_array.shape[0] * diff_array.shape[1]
        except ImportError:
            from PIL import ImageStat
            stat = ImageStat.Stat(diff_img)
            total_pixels = diff_img.width * diff_img.height
            # Approximate: use mean channel diff to estimate changed fraction
            mean_diff = sum(stat.mean) / 3
            diff_pixels = int((mean_diff / 255) * total_pixels) if total_pixels > 0 else 0

        change_pct = (diff_pixels / total_pixels) * 100 if total_pixels > 0 else 0

        # Save the diff image
        diff_path = before_path.parent / f"diff_{before_path.stem}_{after_path.stem}.png"
        diff_img.save(str(diff_path))

        diff_info["diff_image"] = str(diff_path)
        diff_info["change_percentage"] = round(change_pct, 2)
        diff_info["pixels_changed"] = diff_pixels
        diff_info["total_pixels"] = total_pixels
        diff_info["severity"] = (
            "none" if change_pct < 0.1 else
            "minor" if change_pct < 5 else
            "moderate" if change_pct < 20 else
            "major" if change_pct < 50 else
            "complete_redesign"
        )

    except ImportError:
        diff_info["note"] = "Pillow not installed — pixel diff unavailable. Compare screenshots manually."
    except Exception as e:
        diff_info["error"] = str(e)

    return diff_info


def run(args: argparse.Namespace):
    url = getattr(args, "url", None)
    config = load_config()
    if not url:
        url = config.get("dev_server", "http://localhost:3000")

    stage = getattr(args, "stage", None)
    responsive = getattr(args, "responsive", False)

    snapshots = _snapshots_dir()

    if stage == "before":
        # ── Capture BEFORE screenshot (pre-fix baseline) ──
        print(f"📸 Capturing BEFORE screenshot of {url}...")

        if responsive:
            captured = _capture_multi_viewport(url, "before")
            if captured:
                print(f"\n✅ {len(captured)} responsive BEFORE screenshots saved.")
        else:
            out_file = snapshots / "before.png"
            if _capture_screenshot(url, out_file):
                print(f"✅ BEFORE screenshot saved to {out_file}")

    elif stage == "after":
        # ── Capture AFTER screenshot and generate diff ──
        print(f"📸 Capturing AFTER screenshot of {url}...")

        if responsive:
            captured = _capture_multi_viewport(url, "after")
            if captured:
                print(f"\n✅ {len(captured)} responsive AFTER screenshots saved.")

                # Generate diffs for each viewport
                print("\n🔍 Generating visual diffs...")
                responsive_diffs = []
                for after_path in captured:
                    vp_name = after_path.stem.replace("after_", "")
                    before_path = snapshots / f"before_{vp_name}.png"
                    if before_path.exists():
                        diff = _generate_visual_diff(before_path, after_path)
                        change_pct = diff.get("change_percentage", "?")
                        severity = diff.get("severity", "unknown")
                        print(f"  {vp_name}: {change_pct}% change ({severity})")
                        responsive_diffs.append({"viewport": vp_name, **diff})

                # Save responsive diff metadata (mirrors the non-responsive path)
                if responsive_diffs:
                    import json
                    diff_meta = snapshots / "diff_meta.json"
                    with open(diff_meta, "w", encoding="utf-8") as f:
                        json.dump({"responsive": True, "viewports": responsive_diffs}, f, indent=2)
        else:
            out_file = snapshots / "after.png"
            if _capture_screenshot(url, out_file):
                print(f"✅ AFTER screenshot saved to {out_file}")

                # Generate diff if before exists
                before_file = snapshots / "before.png"
                if before_file.exists():
                    print("\n🔍 Generating visual diff...")
                    diff = _generate_visual_diff(before_file, out_file)
                    change_pct = diff.get("change_percentage", "?")
                    severity = diff.get("severity", "unknown")
                    print(f"   Change: {change_pct}% ({severity})")
                    if diff.get("diff_image"):
                        print(f"   Diff image: {diff['diff_image']}")

                    # Save diff metadata
                    import json
                    diff_meta = snapshots / "diff_meta.json"
                    with open(diff_meta, "w", encoding="utf-8") as f:
                        json.dump(diff, f, indent=2)
                else:
                    print("   ⚠️  No BEFORE screenshot found. Run `uidetox capture --stage before` first.")

        # Copy to latest for review command
        latest = snapshots / "latest.png"
        after_desktop = snapshots / "after.png"
        if after_desktop.exists():
            shutil.copy2(after_desktop, latest)

    else:
        # ── Default: single capture (legacy behavior) ──
        print(f"📸 Capturing screenshot of {url}...")
        out_file = snapshots / "latest.png"
        if _capture_screenshot(url, out_file):
            print(f"✅ Screenshot saved to {out_file}")
            print()
            print("  TIP: Use `uidetox capture --stage before` and `--stage after`")
            print("  for visual regression validation during the fix loop.")
