"""Route-level UX-state validation.

Every data surface (page, route, component that fetches data) must prove
coverage of the four canonical UI states:

    loading  → skeleton / spinner / shimmer while data is in-flight
    error    → error boundary, retry action, user-friendly message
    empty    → empty state illustration + call-to-action
    success  → the happy-path render with actual data

This module maps data surfaces to backend response taxonomy (status codes,
GraphQL error shapes, Prisma error codes) and validates that the frontend
handles each case.

Integration points:
    - ``scan.py``  — runs UX-state validation during Phase 1
    - ``review.py`` — subagent domain #3 (interaction states) checks coverage
    - ``loop.py``   — autopilot plan includes UX-state gate
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── State coverage types ─────────────────────────────────────────

REQUIRED_STATES = ("loading", "error", "empty", "success")

# Pattern families for detecting each UI state in code
_STATE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "loading": [
        re.compile(r'\bisLoading\b|\bis_loading\b|\bpending\b', re.IGNORECASE),
        re.compile(r'\b(?:Skeleton|Shimmer|Spinner|Loading)\b'),
        re.compile(r'\bsuspense\b|\bSuspense\b'),
        re.compile(r'\buseSWR\b.*\bisValidating\b', re.DOTALL),
        re.compile(r'\buseQuery\b.*\bisLoading\b', re.DOTALL),
        re.compile(r'\bfallback\s*=', re.IGNORECASE),
    ],
    "error": [
        re.compile(r'\bisError\b|\bis_error\b|\berror\s*[!=]', re.IGNORECASE),
        re.compile(r'\bErrorBoundary\b|\bErrorFallback\b'),
        re.compile(r'\bcatch\s*\(', re.IGNORECASE),
        re.compile(r'\bfailure\b|\bfailed\b', re.IGNORECASE),
        re.compile(r'\btry\s*\{', re.IGNORECASE),
        re.compile(r'\bonError\b|\berrorElement\b'),
        re.compile(r'\btoast\.error\b|\bnotify.*error\b', re.IGNORECASE),
    ],
    "empty": [
        re.compile(r'\bempty\b.*\bstate\b|\bno\s+(?:data|results|items)\b', re.IGNORECASE),
        re.compile(r'(?:\.length|\.size)\s*===?\s*0'),
        re.compile(r'\bEmptyState\b|\bNoData\b|\bNoResults\b'),
        re.compile(r'\bisEmpty\b|\bis_empty\b'),
        re.compile(r'\bnull\s*(?:\|\||&&|\?)', re.IGNORECASE),
    ],
    "success": [
        # Success is detected by the presence of data rendering patterns
        re.compile(r'\.map\s*\('),
        re.compile(r'\bdata\b\s*&&|\bdata\b\s*\?'),
        re.compile(r'\breturn\s*\(?\s*<'),
        re.compile(r'\bisSuccess\b|\bis_success\b'),
    ],
}

# Data-fetching patterns that identify a "data surface"
_DATA_SURFACE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'\buseSWR\b'),
    re.compile(r'\buseQuery\b'),
    re.compile(r'\buseMutation\b'),
    re.compile(r'\bfetch\s*\('),
    re.compile(r'\baxios\b'),
    re.compile(r'\bgetServerSideProps\b|\bgetStaticProps\b'),
    re.compile(r'\bloader\s*[:=]'),  # React Router / Remix loaders
    re.compile(r'\btrpc\.\w+\.(?:useQuery|useMutation)\b'),
    re.compile(r'\buseEffect\b.*\bfetch\b', re.DOTALL),
    re.compile(r'\bapi\.\w+\b'),
]

# Backend response taxonomy: status codes that must be handled
_STATUS_CODE_TAXONOMY = {
    200: "success",
    201: "success",
    204: "empty",
    400: "error",
    401: "error",
    403: "error",
    404: "empty",
    422: "error",
    429: "error",
    500: "error",
    502: "error",
    503: "error",
}


@dataclass
class DataSurface:
    """A component/route that fetches data."""
    file: str
    line: int = 0
    pattern: str = ""
    name: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "pattern": self.pattern,
            "name": self.name,
        }


@dataclass
class StateCoverage:
    """Coverage report for a single data surface."""
    surface: DataSurface
    has_loading: bool = False
    has_error: bool = False
    has_empty: bool = False
    has_success: bool = False

    @property
    def missing_states(self) -> list[str]:
        missing: list[str] = []
        if not self.has_loading:
            missing.append("loading")
        if not self.has_error:
            missing.append("error")
        if not self.has_empty:
            missing.append("empty")
        if not self.has_success:
            missing.append("success")
        return missing

    @property
    def is_complete(self) -> bool:
        return not self.missing_states

    @property
    def coverage_ratio(self) -> float:
        covered = sum([self.has_loading, self.has_error, self.has_empty, self.has_success])
        return covered / 4.0

    def to_dict(self) -> dict:
        return {
            "surface": self.surface.to_dict(),
            "has_loading": self.has_loading,
            "has_error": self.has_error,
            "has_empty": self.has_empty,
            "has_success": self.has_success,
            "missing": self.missing_states,
            "coverage": self.coverage_ratio,
        }

    def to_issue(self) -> dict | None:
        """Convert missing state coverage to an issue dict."""
        missing = self.missing_states
        if not missing:
            return None

        severity = "T1" if len(missing) >= 3 else ("T2" if len(missing) >= 2 else "T3")
        missing_str = ", ".join(missing)
        return {
            "file": self.surface.file,
            "tier": severity,
            "issue": f"Data surface missing UX states: {missing_str}. "
                     f"Pattern: {self.surface.pattern}. "
                     f"Every data-fetching component must handle loading/error/empty/success.",
            "command": f"Add {missing_str} state handling to the data-fetching component. "
                       f"Use Skeleton/Shimmer for loading, ErrorBoundary for errors, "
                       f"EmptyState component for empty, and data rendering for success.",
        }


# ── Detection and validation ────────────────────────────────────

_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "vendor",
              "__pycache__", ".tox", "coverage", ".turbo", "out"}


def find_data_surfaces(root: Path, files: list[Path] | None = None) -> list[DataSurface]:
    """Find all data-fetching surfaces in the project."""
    frontend_exts = {".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte"}

    if files is None:
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith('.')]
            for fname in filenames:
                if Path(fname).suffix in frontend_exts:
                    files.append(Path(dirpath) / fname)
            if len(files) >= 300:
                break

    surfaces: list[DataSurface] = []

    for fpath in files:
        try:
            content = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for pattern in _DATA_SURFACE_PATTERNS:
            match = pattern.search(content)
            if match:
                # Determine line number
                line_num = content[:match.start()].count("\n") + 1
                surfaces.append(DataSurface(
                    file=str(fpath),
                    line=line_num,
                    pattern=pattern.pattern[:50],
                    name=fpath.stem,
                ))
                break  # One surface per file (avoid duplicates)

    return surfaces


def validate_state_coverage(
    root: Path,
    surfaces: list[DataSurface] | None = None,
) -> list[StateCoverage]:
    """Validate that each data surface has loading/error/empty/success coverage."""
    if surfaces is None:
        surfaces = find_data_surfaces(root)

    results: list[StateCoverage] = []

    for surface in surfaces:
        fpath = Path(surface.file)
        try:
            content = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        coverage = StateCoverage(surface=surface)

        for state_name, patterns in _STATE_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(content):
                    if state_name == "loading":
                        coverage.has_loading = True
                    elif state_name == "error":
                        coverage.has_error = True
                    elif state_name == "empty":
                        coverage.has_empty = True
                    elif state_name == "success":
                        coverage.has_success = True
                    break

        results.append(coverage)

    return results


def generate_coverage_report(coverages: list[StateCoverage]) -> dict:
    """Generate a summary report of UX-state coverage across all surfaces."""
    total = len(coverages)
    if total == 0:
        return {
            "total_surfaces": 0,
            "complete": 0,
            "incomplete": 0,
            "coverage_percentage": 100,
            "missing_breakdown": {},
        }

    complete = sum(1 for c in coverages if c.is_complete)
    incomplete = total - complete

    missing_breakdown: dict[str, int] = {"loading": 0, "error": 0, "empty": 0, "success": 0}
    for c in coverages:
        for state in c.missing_states:
            missing_breakdown[state] = missing_breakdown.get(state, 0) + 1

    avg_coverage = sum(c.coverage_ratio for c in coverages) / total

    return {
        "total_surfaces": total,
        "complete": complete,
        "incomplete": incomplete,
        "coverage_percentage": round(avg_coverage * 100),
        "missing_breakdown": missing_breakdown,
    }


def validate_against_response_taxonomy(
    coverages: list[StateCoverage],
    endpoint_status_codes: dict[str, list[int]] | None = None,
) -> list[dict]:
    """Cross-reference UX states against backend response status codes.

    If the backend can return a 404, the frontend must handle 'empty'.
    If the backend can return a 500, the frontend must handle 'error'.
    """
    if not endpoint_status_codes:
        return []

    violations: list[dict] = []

    # Build a map of which states are required by the backend taxonomy
    backend_requires: dict[str, set[str]] = {}
    for endpoint, codes in endpoint_status_codes.items():
        required_states: set[str] = set()
        for code in codes:
            state = _STATUS_CODE_TAXONOMY.get(code)
            if state:
                required_states.add(state)
        backend_requires[endpoint] = required_states

    # Aggregate all required states
    all_required = set()
    for states in backend_requires.values():
        all_required |= states

    for coverage in coverages:
        for state in all_required:
            has_state = getattr(coverage, f"has_{state}", False)
            if not has_state:
                violations.append({
                    "file": coverage.surface.file,
                    "tier": "T2",
                    "issue": f"Backend response taxonomy requires '{state}' state handling "
                             f"but component lacks coverage.",
                    "command": f"Add {state} state handling to cover backend response codes.",
                })

    return violations
