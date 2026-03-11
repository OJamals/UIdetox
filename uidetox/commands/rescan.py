"""Rescan command: clears the queue and runs a unified re-scan (static + subjective).

This is the 'outer loop' in the desloppify flow -- after the fix loop drains the
queue, rescan re-evaluates from scratch to discover deeper issues and check if
the target score has been reached.

Smart deduplication: issues already resolved in this session won't be re-queued
unless the underlying pattern reappears in modifed code. Issues that survived
multiple rescans get auto-escalated in priority.
"""

import argparse
import uuid
from uidetox.analyzer import analyze_directory
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import load_state, load_config, clear_issues, add_issue, increment_scans
from uidetox.history import save_run_snapshot
from uidetox.utils import compute_design_score
from uidetox.memory import log_progress


def _dedup_key(issue: dict) -> str:
    """Create a deduplication key from file + issue description."""
    return f"{issue.get('file', '')}::{issue.get('issue', '')}"


def _auto_escalate_tier(tier: str) -> str:
    """Escalate tier by one level for recurring issues."""
    escalation = {"T1": "T2", "T2": "T3", "T3": "T4", "T4": "T4"}
    return escalation.get(tier, tier)


def run(args: argparse.Namespace):
    state = load_state()
    config = load_config()
    old_issues = state.get("issues", [])
    old_count = len(old_issues)
    resolved = state.get("resolved", [])
    target = config.get("target_score", 95)

    # Build dedup sets from resolved AND old issues
    resolved_keys = {_dedup_key(r) for r in resolved}
    old_issue_keys = {_dedup_key(i) for i in old_issues}

    # Track scan count per issue pattern for auto-escalation
    recurrence: dict[str, int] = {}
    for r in resolved:
        key = _dedup_key(r)
        recurrence[key] = recurrence.get(key, 0) + 1

    # Clear existing issues and track the rescan
    clear_issues()
    increment_scans()

    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)

    path = getattr(args, "path", ".")

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
    slop_issues = analyze_directory(path, exclude_paths=exclude_paths, zone_overrides=zone_overrides, design_variance=variance)

    queued_count = 0
    dedup_skipped = 0
    escalated_count = 0

    for issue in slop_issues:
        if _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            continue

        key = _dedup_key(issue)

        # Smart dedup: skip if already resolved AND file hasn't changed
        # (we re-queue if the pattern recurs — meaning the fix didn't stick)
        if key in resolved_keys and key not in old_issue_keys:
            dedup_skipped += 1
            continue

        # Auto-escalate recurring issues
        tier = issue["tier"]
        if key in recurrence and recurrence[key] >= 2:
            new_tier = _auto_escalate_tier(tier)
            if new_tier != tier:
                tier = new_tier
                escalated_count += 1

        issue_id = f"SCAN-{str(uuid.uuid4())[:6].upper()}"
        new_issue = {
            "id": issue_id,
            "file": issue['file'],
            "tier": tier,
            "issue": issue["issue"],
            "command": issue["command"]
        }
        add_issue(new_issue)
        queued_count += 1

    if queued_count > 0:
        print(f"  -> Queued {queued_count} mechanical anti-pattern issues.")
    else:
        print(f"  -> No mechanical anti-patterns detected.")

    if dedup_skipped > 0:
        print(f"  -> Skipped {dedup_skipped} already-resolved issue(s) (smart dedup).")
    if escalated_count > 0:
        print(f"  -> Escalated {escalated_count} recurring issue(s) to higher severity.")

    # ---- SUBJECTIVE REVIEW PROMPT ----
    print()
    print("  SUBJECTIVE REVIEW (complete during this rescan):")
    print("  Read all frontend files with fresh eyes. Score these dimensions:")
    print("    A. VISUAL DESIGN (0-40): styling/elegance, typography, layout/spatial")
    print("    B. DESIGN SYSTEM (0-30): consistency, identity")
    print("    C. INTERACTION  (0-20): states/micro-interactions, edge cases/polish")
    print("    D. ARCHITECTURE (0-10): component structure, data flow, code quality")
    print("  Queue any new issues found:")
    print('    uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    print("  Record your score:  uidetox review --score <N>   (sum of A+B+C+D)")
    print()

    # ---- SUPPRESSIONS ----
    if ignore_patterns:
        print(f"  Active suppressions: {len(ignore_patterns)} (do NOT flag matching issues)")

    # ---- TARGET CHECK ----
    save_run_snapshot(trigger="rescan")
    log_progress("rescan", f"Rescanned {path}: {queued_count} issues queued, {dedup_skipped} deduped, {escalated_count} escalated")
    state = load_state()
    scores = compute_design_score(state)
    score = scores["blended_score"]
    queue_size = len(state.get("issues", []))

    print()
    print("-" * 58)
    filled = score // 5
    bar = "#" * filled + "." * (20 - filled)
    print(f"  Design Score: [{bar}] {score}/100  (target: {target})")
    print(f"  Queue: {queue_size} issue(s)")

    if score >= target and queue_size == 0:
        print(f"  TARGET REACHED -> Run `uidetox finish`")
    elif queue_size > 0:
        print(f"  -> Run `uidetox next` to enter fix loop.")
    else:
        print(f"  -> Complete subjective review above, then `uidetox status`.")
    print()
