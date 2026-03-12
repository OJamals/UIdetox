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
from uidetox.state import load_state, load_config, clear_issues, batch_add_issues, increment_scans
from uidetox.history import save_run_snapshot
from uidetox.utils import compute_design_score, get_score_freshness
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
    pending_issues: list[dict] = []

    for issue in slop_issues:
        if _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            continue

        key = _dedup_key(issue)

        # Smart dedup: If this pattern was resolved before, check recurrence.
        # If the fix didn't stick (the analyzer found it again), re-queue it.
        # Only skip on first re-appearance when the issue was NOT already in the
        # pre-rescan pending queue (benefit-of-the-doubt window).
        if key in resolved_keys:
            occurrences = recurrence.get(key, 0)
            if occurrences < 2 and key not in old_issue_keys:
                # First re-appearance after resolution — give benefit of doubt
                dedup_skipped += 1
                continue
            # Otherwise: pattern keeps recurring — re-queue it

        # Auto-escalate recurring issues
        tier = issue["tier"]
        if key in recurrence and recurrence[key] >= 2:
            new_tier = _auto_escalate_tier(tier)
            if new_tier != tier:
                tier = new_tier
                escalated_count += 1

        issue_id = f"SCAN-{uuid.uuid4().hex[:8].upper()}"
        new_issue = {
            "id": issue_id,
            "file": issue['file'],
            "tier": tier,
            "issue": issue["issue"],
            "command": issue["command"]
        }
        pending_issues.append(new_issue)
        queued_count += 1

    # Batch-add all issues in a single state write
    batch_result = {"added": 0, "updated": 0, "skipped": 0}
    if pending_issues:
        batch_result = batch_add_issues(pending_issues)
        queued_count = batch_result["added"]

    if queued_count > 0:
        print(f"  -> Queued {queued_count} mechanical anti-pattern issues.")
    else:
        print(f"  -> No mechanical anti-patterns detected.")
    if batch_result["updated"] > 0:
        print(f"  -> Refreshed {batch_result['updated']} duplicate issue(s) with stronger severity/guidance.")
    if batch_result["skipped"] > 0:
        print(f"  -> Skipped {batch_result['skipped']} duplicate issue(s) generated during the rescan.")

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
    freshness = get_score_freshness(state)
    score = scores["blended_score"]
    if score is None:
        score = 0
    queue_size = len(state.get("issues", []))

    print()
    print("-" * 58)
    filled = max(0, score // 5)
    bar = "#" * filled + "." * (20 - filled)
    print(f"  Design Score: [{bar}] {score}/100  (target: {target})")
    # Score breakdown
    obj = scores.get("objective_score")
    raw_sub = scores.get("subjective_score")
    eff_sub = scores.get("effective_subjective")
    if eff_sub is not None and raw_sub is not None and eff_sub != raw_sub:
        print(f"    Objective  : {obj}/100  |  Subjective: {eff_sub}/100 effective (raw {raw_sub}, Δ-{raw_sub - eff_sub})")
    elif raw_sub is not None and obj is not None:
        print(f"    Objective  : {obj}/100  |  Subjective: {raw_sub}/100")
    print(f"  Queue: {queue_size} issue(s)")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    if score >= target and queue_size == 0 and freshness["target_ready"]:
        print(f"TARGET REACHED (score {score} >= {target}, queue empty).")
        print("Run `uidetox loop` NOW — it will finish the session.")
    elif queue_size > 0:
        print(f"Queue refilled with {queue_size} issue(s).")
        print("Run `uidetox loop` NOW — it will fix them automatically.")
    else:
        print("Queue empty, but finish is blocked until objective + subjective analysis are fresh.")
        if freshness.get("reasons"):
            for reason in freshness["reasons"][:2]:
                print(f"  - {reason}")
        print("Run `uidetox loop` NOW — it will run the review cycle.")
    print("DO NOT STOP. DO NOT run individual commands — the loop handles everything.")
    print()
