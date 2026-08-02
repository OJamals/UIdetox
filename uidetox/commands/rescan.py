"""Rescan command: clears the queue and runs a unified re-scan (static + subjective).
This is the 'outer loop' in the desloppify flow -- after the fix loop drains the
queue, rescan re-evaluates from scratch to discover deeper issues and check if
the target score has been reached.
"""

import argparse
import os
import sys

from uidetox.analyzer import analyze_directory
from uidetox.commands.add_issue import _is_suppressed
from uidetox.commands.scan import current_map_findings
from uidetox.findings import (
    coerce_finding,
    current_evidence_hashes,
    requires_resolution,
    score_current_snapshot,
)
from uidetox.history import save_run_snapshot
from uidetox.memory import log_progress
from uidetox.state import (
    add_issues,
    clear_issues,
    get_project_root,
    increment_scans,
    load_config,
    load_state,
)


def run(args: argparse.Namespace):
    state = load_state()
    config = load_config()
    project_root = get_project_root()
    old_issues = state.get("issues", [])
    old_count = len(old_issues)
    resolved = state.get("resolved", [])
    target = config.get("target_score", 95)
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)
    path_arg = getattr(args, "path", ".")
    path = str(project_root) if path_arg in (None, "", ".") else path_arg
    # Validate path before doing anything
    if not os.path.isdir(path):
        print(
            f"Error: scan path '{path}' does not exist or is not a directory.",
            file=sys.stderr,
        )
        sys.exit(1)
    clear_issues()
    increment_scans()
    print("=" * 58)
    print(" UIdetox Rescan (fresh analysis + smart dedup)")
    print("=" * 58)
    print(f"  Cleared {old_count} previous issue(s).")
    print(f"  Resolved history: {len(resolved)} issue(s)")
    print(f"  Path: {path}  |  Dials: V={variance} M={intensity} D={density}")
    print()
    # ---- STATIC ANALYSIS ----
    print("  Running static slop analyzer...")
    ignore_patterns = config.get("ignore_patterns", [])
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    slop_issues = analyze_directory(
        path,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
        design_variance=variance,
    )
    pending_issues = [
        coerce_finding(issue)
        for issue in slop_issues
        if not _is_suppressed(issue["file"], issue["issue"], ignore_patterns)
    ]
    mapped_findings, map_qualified = current_map_findings(project_root)
    pending_issues = list(
        {
            finding.fingerprint: finding
            for finding in [*pending_issues, *mapped_findings]
        }.values()
    )
    queued_count = add_issues(pending_issues, qualified_complete=map_qualified)
    actionable_detected = sum(requires_resolution(issue) for issue in pending_issues)
    investigative_detected = len(pending_issues) - actionable_detected
    if actionable_detected:
        print(f"  -> Queued {actionable_detected} actionable anti-pattern issue(s).")
    else:
        print("  -> No actionable anti-patterns detected.")
    if investigative_detected:
        print(f"  -> Recorded {investigative_detected} investigative finding(s).")
    # ---- SUBJECTIVE REVIEW PROMPT ----
    print()
    print("  SUBJECTIVE REVIEW (complete during this rescan):")
    print("  Read all frontend files with fresh eyes. Score these dimensions:")
    print("    A. VISUAL DESIGN (0-40): styling/elegance, typography, layout/spatial")
    print("    B. DESIGN SYSTEM (0-30): consistency, identity")
    print("    C. INTERACTION  (0-20): states/micro-interactions, edge cases/polish")
    print("    D. ARCHITECTURE (0-10): component structure, data flow, code quality")
    print("  Queue any new issues found:")
    print(
        '    uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"'
    )
    print("  Run `uidetox review` and record structured A/B/C/D evidence.")
    print()
    # ---- SUPPRESSIONS ----
    if ignore_patterns:
        print(
            f"  Active suppressions: {len(ignore_patterns)} (do NOT flag matching issues)"
        )
    # ---- TARGET CHECK ----
    save_run_snapshot(trigger="rescan")
    log_progress(
        "rescan",
        f"Rescanned {path}: {queued_count} current findings queued",
    )
    state = load_state()
    scores = score_current_snapshot(state, evidence_hashes=current_evidence_hashes())
    score = scores["blended_score"]
    current_issues = state.get("issues", [])
    queue_size = sum(requires_resolution(issue) for issue in current_issues)
    investigative_count = len(current_issues) - queue_size
    print()
    print("-" * 58)
    filled = score // 5
    bar = "#" * filled + "." * (20 - filled)
    print(f"  Design Score: [{bar}] {score}/100  (target: {target})")
    print(f"  Queue: {queue_size} actionable | {investigative_count} investigative")
    if score >= target and queue_size == 0:
        print("  TARGET REACHED -> Run `uidetox finish`")
    elif queue_size > 0:
        print("  -> Run `uidetox next` to enter fix loop.")
    else:
        print("  -> Complete subjective review above, then `uidetox status`.")
    print()
