#!/usr/bin/env python3
"""Sync root-level asset files into uidetox/data/ for packaging.

Root files are the single source of truth:
  AGENTS.md, SKILL.md, commands/*.md, docs/*.md, reference/*.md

This script copies them into uidetox/data/ so they're bundled
in the pip wheel via pyproject.toml [tool.setuptools.package-data].

Usage:
    python scripts/sync_data.py          # sync
    python scripts/sync_data.py --check  # verify (CI-safe, exit 1 if stale)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "uidetox" / "data"

# Mapping: root source → data destination (relative to ROOT / DATA)
SYNC_PAIRS: list[tuple[str, str]] = [
    ("AGENTS.md", "AGENTS.md"),
    ("SKILL.md", "SKILL.md"),
]

# Directory mirrors: all *.md files in these root dirs → data subdirs
SYNC_DIRS: list[tuple[str, str]] = [
    ("commands", "commands"),
    ("docs", "docs"),
    ("reference", "reference"),
]


def _collect_pairs() -> list[tuple[Path, Path]]:
    """Build list of (source, dest) pairs."""
    pairs: list[tuple[Path, Path]] = []

    for src_rel, dst_rel in SYNC_PAIRS:
        src = ROOT / src_rel
        if src.exists():
            pairs.append((src, DATA / dst_rel))

    for src_dir_name, dst_dir_name in SYNC_DIRS:
        src_dir = ROOT / src_dir_name
        if not src_dir.is_dir():
            continue
        for src_file in sorted(src_dir.glob("*.md")):
            dst_file = DATA / dst_dir_name / src_file.name
            pairs.append((src_file, dst_file))

    return pairs


def sync() -> int:
    """Copy root files → uidetox/data/. Returns count of updated files."""
    pairs = _collect_pairs()
    updated = 0
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Only copy if content differs (avoid unnecessary git churn)
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            continue
        shutil.copy2(src, dst)
        print(f"  synced {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")
        updated += 1
    if updated == 0:
        print("  uidetox/data/ is up-to-date.")
    else:
        print(f"  {updated} file(s) synced.")
    return updated


def check() -> bool:
    """Verify data/ matches root files. Returns True if in sync."""
    pairs = _collect_pairs()
    stale: list[str] = []
    missing: list[str] = []

    for src, dst in pairs:
        if not dst.exists():
            missing.append(str(src.relative_to(ROOT)))
        elif dst.read_bytes() != src.read_bytes():
            stale.append(str(src.relative_to(ROOT)))

    if stale or missing:
        if stale:
            print("  STALE (root changed but data/ not updated):")
            for f in stale:
                print(f"    {f}")
        if missing:
            print("  MISSING from uidetox/data/:")
            for f in missing:
                print(f"    {f}")
        print("\n  Run: python scripts/sync_data.py")
        return False

    print("  ✓ uidetox/data/ is in sync with root files.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync root assets → uidetox/data/")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify sync without modifying files (exit 1 if stale)",
    )
    args = parser.parse_args()

    if args.check:
        ok = check()
        sys.exit(0 if ok else 1)
    else:
        sync()


if __name__ == "__main__":
    main()
