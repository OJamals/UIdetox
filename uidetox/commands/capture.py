"""Capture command: use Playwright to take a screenshot of the dev server."""

import argparse
from pathlib import Path
from uidetox.state import ensure_uidetox_dir, load_config
import sys


def run(args: argparse.Namespace):
    url = getattr(args, "url", None)
    config = load_config()
    if not url:
        url = config.get("dev_server", "http://localhost:3000")

    print(f"📸 Capturing screenshot of {url}...")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright not installed. Run: pip install playwright && playwright install", file=sys.stderr)
        return

    uidetox_dir = ensure_uidetox_dir()
    snapshots_dir = uidetox_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    
    out_file = snapshots_dir / "latest.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, wait_until="networkidle", timeout=15000)
            page.screenshot(path=str(out_file), full_page=True)
            browser.close()
            
        print(f"✅ Screenshot saved to {out_file}")
    except Exception as e:
        print(f"❌ Failed to capture screenshot: {e}", file=sys.stderr)
