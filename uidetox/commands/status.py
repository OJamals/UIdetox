"""Status command: project health dashboard with smart scoring and velocity tracking."""

import argparse
import json
from uidetox.state import load_state, load_config
from uidetox.utils import compute_design_score, get_score_freshness, categorize_issue, ISSUE_CATEGORY_KEYWORDS
from uidetox.memory import get_session


# Recommended fix order hints per category
_CATEGORY_HINTS = {
    "typography": "Start here — font swap is the biggest instant improvement, lowest risk.",
    "color": "Clean up palette — remove AI purple-blue gradients and pure black.",
    "motion": "Add hover/active states — makes the interface feel alive.",
    "layout": "Fix grids and spacing — proper max-width, asymmetric layouts.",
    "materiality": "Replace glassmorphism and oversized shadows with solid surfaces.",
    "states": "Add loading/error/empty states — makes it feel finished.",
    "a11y": "Add focus indicators and ARIA labels — accessibility requirement.",
    "duplication": "Extract repeated code into shared components or utility functions.",
    "dead code": "Remove commented-out code, unused imports, and no-op handlers.",
    "content": "Replace generic AI copy and placeholder names with real content.",
    "code quality": "Fix lint suppressions, type safety issues, and semantic HTML.",
    "components": "Replace generic icon/badge/dashboard patterns with intentional design.",
}


def run(args: argparse.Namespace):
    state = load_state()
    config = load_config()
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])
    stats = state.get("stats", {})
    scans_run = stats.get("scans_run", 0)

    # Tier breakdown
    tiers = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    for issue in issues:
        tier = issue.get("tier", "T4")
        if tier in tiers:
            tiers[tier] += 1

    # Category breakdown (using centralized category inference)
    cat_pending: dict[str, int] = {}
    cat_resolved: dict[str, int] = {}
    for issue in issues:
        desc = issue.get("issue", "")
        cat = categorize_issue(desc)
        cat_pending[cat] = cat_pending.get(cat, 0) + 1
    for issue in resolved:
        desc = issue.get("issue", "")
        cat = categorize_issue(desc)
        cat_resolved[cat] = cat_resolved.get(cat, 0) + 1

    # Build a unified categories view for display
    all_cats = sorted(set(cat_pending.keys()) | set(cat_resolved.keys()) | set(ISSUE_CATEGORY_KEYWORDS.keys()))
    categories: dict[str, dict] = {}
    for cat in all_cats:
        categories[cat] = {
            "pending": cat_pending.get(cat, 0),
            "resolved": cat_resolved.get(cat, 0),
        }

    # Centralized scoring
    scores = compute_design_score(state)
    freshness = get_score_freshness(state)
    score = scores["blended_score"]
    objective_score = scores["objective_score"]
    subjective_score = scores["subjective_score"]
    # Handle None (no scans run yet)
    display_score = score if score is not None else 0

    use_json = getattr(args, "json", False)
    total_resolved = len(resolved)
    total_found = stats.get("total_found", len(issues) + total_resolved)

    if use_json:
        payload = {
            "design_score": score,
            "objective_score": objective_score,
            "subjective_score": subjective_score,
            "total_issues": len(issues),
            "total_resolved": total_resolved,
            "total_found": total_found,
            "resolution_rate": f"{(total_resolved / total_found * 100) if total_found else 0:.0f}%",
            "tiers": tiers,
            "scans_run": scans_run,
            "last_scan": state.get("last_scan"),
        }
        print(json.dumps(payload, indent=2))
        return

    print("╔══════════════════════════════╗")
    print("║   UIdetox Health Dashboard   ║")
    print("╚══════════════════════════════╝")

    # Score bar
    filled = max(0, display_score // 5)
    bar = "█" * filled + "░" * (20 - filled)
    if score is None:
        print(f"\n  Design Score : [{bar}] —/100  (not scanned yet)")
    else:
        print(f"\n  Design Score : [{bar}] {score}/100")
    if subjective_score is not None:
        effective_sub = scores.get("effective_subjective")
        print(f"    Objective  : {objective_score}/100  (static analysis — 30% weight)")
        if effective_sub is not None and effective_sub != subjective_score:
            print(f"    Subjective : {effective_sub}/100 effective  (raw {subjective_score} → curve + penalties)")
        else:
            print(f"    Subjective : {subjective_score}/100  (LLM review — 70% weight)")
        if effective_sub is not None and subjective_score is not None and subjective_score > effective_sub:
            delta = subjective_score - effective_sub
            print(f"    Compression: -{delta} pts  (diminishing-returns curve + objective anchoring)")
        if len(issues) == 0 and not freshness["target_ready"]:
            print("    Score state: STALE — re-run loop before trusting target reached")
    elif scans_run == 0 and scores["total_slop"] == 0:
        print(f"  (Baseline — run 'uidetox scan' for an accurate score)")
    else:
        print(f"    Objective only — run 'uidetox review' for LLM subjective score")
    print()

    # Issue summary
    print(f"  Pending Issues  : {len(issues)}")
    print(f"  Resolved Issues : {total_resolved}")
    if total_found:
        rate = total_resolved / total_found * 100
        print(f"  Resolution Rate : {rate:.0f}%")
    print(f"  Scans Run       : {scans_run}")
    print()

    # Tier breakdown
    print(f"  T1 Quick Fix         : {tiers['T1']}")
    print(f"  T2 Targeted Refactor : {tiers['T2']}")
    print(f"  T3 Design Judgment   : {tiers['T3']}")
    print(f"  T4 Major Redesign    : {tiers['T4']}")
    print()

    # Design dials
    print(f"  DESIGN_VARIANCE  : {config.get('DESIGN_VARIANCE', 8)}")
    print(f"  MOTION_INTENSITY : {config.get('MOTION_INTENSITY', 6)}")
    print(f"  VISUAL_DENSITY   : {config.get('VISUAL_DENSITY', 4)}")
    auto_commit = config.get('auto_commit', False)
    print(f"  AUTO_COMMIT      : {'enabled' if auto_commit else 'disabled'}")

    # ---- Velocity & Progression ----
    subjective_history = state.get("subjective", {}).get("history", [])
    if scans_run > 1 or total_resolved > 0:
        print()
        print("  ─── Velocity & Progression ───")
        if total_found > 0:
            print(f"  Fix rate        : {total_resolved}/{total_found} ({(total_resolved / total_found * 100):.0f}%)")
        if scans_run > 0:
            avg_per_scan = total_found / scans_run if total_found > 0 else 0
            print(f"  Avg issues/scan : {avg_per_scan:.1f}")
        if total_resolved > 0 and scans_run > 0:
            velocity = total_resolved / scans_run
            print(f"  Fix velocity    : {velocity:.1f} resolved/scan")

        # Subjective score progression
        if len(subjective_history) > 1:
            scores_list = [h["score"] for h in subjective_history]
            trend = scores_list[-1] - scores_list[0]
            trend_arrow = "↑" if trend > 0 else ("↓" if trend < 0 else "→")
            print(f"  Subjective trend: {scores_list[0]} → {scores_list[-1]} ({trend_arrow}{abs(trend)}pts over {len(scores_list)} reviews)")

    # Session context
    session = get_session()
    if session:
        phase = session.get('phase', 'unknown')
        fixed = session.get('issues_fixed_this_session', 0)
        last_component = session.get('last_component', '')
        session_parts = []
        session_parts.append(f"phase={phase}")
        if fixed > 0:
            session_parts.append(f"fixed={fixed}")
        if last_component:
            session_parts.append(f"last={last_component}")
        print(f"  Session         : {', '.join(session_parts)}")

    # Category breakdown with actionable hints
    active_cats = {k: v for k, v in categories.items() if v["pending"] > 0 or v["resolved"] > 0}
    if active_cats:
        print()
        print("  ─── Category Breakdown ───")
        for cat_name, cat in active_cats.items():
            pending_val = cat["pending"]
            resolved_val = cat["resolved"]
            total_cat = pending_val + resolved_val
            if total_cat > 0:
                cat_score = int((resolved_val / total_cat) * 100)
                cat_bar = "█" * (cat_score // 10) + "░" * (10 - cat_score // 10)
                print(f"  {cat_name:<14} [{cat_bar}] {cat_score}%  ({pending_val} pending, {resolved_val} resolved)")
                # Show hint for worst-performing categories
                if cat_score == 0 and cat_name in _CATEGORY_HINTS:
                    print(f"                 ^ {_CATEGORY_HINTS[cat_name]}")

    # Verdict — use display_score for safe comparisons (never None)
    if display_score >= 95 and len(issues) == 0 and freshness["target_ready"]:
        print("\n  EXCELLENT — Interface is clean of AI slop. Queue is empty.")
    elif display_score >= 95 and len(issues) == 0:
        print("\n  Score is high, but it is stale — objective and/or subjective analysis must re-run.")
    elif display_score >= 95:
        print("\n  Score is high, but some issues remain in the queue.")
    elif display_score >= 80:
        print("\n  Good progress. A few issues remain — keep pushing.")
    elif display_score >= 50:
        print("\n  Moderate slop detected. Focus on T1 and T2 first.")
    elif score is None:
        print("\n  No score yet. Run 'uidetox scan' to begin analysis.")
    else:
        print("\n  Heavy slop detected. Run 'uidetox loop' and go.")

    # Agent loop control signal
    target = config.get("target_score", 95)
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    if display_score >= target and len(issues) == 0 and freshness["target_ready"]:
        print(f"TARGET REACHED (score {display_score} >= {target}, queue empty).")
        print("Run `uidetox loop` — it will finish the session.")
    elif display_score >= target and len(issues) == 0:
        print(f"Score: {display_score} (>= {target}), queue empty, but finish is blocked.")
        print("Run `uidetox loop` NOW — it will refresh objective + subjective analysis.")
        if freshness.get("reasons"):
            for reason in freshness["reasons"][:2]:
                print(f"  - {reason}")
    elif len(issues) == 0:
        print(f"Queue empty but score {display_score} < {target}.")
        print("Run `uidetox loop` NOW — it will run objective + subjective analysis.")
        if freshness.get("reasons"):
            for reason in freshness["reasons"][:2]:
                print(f"  - {reason}")
    else:
        print(f"Score: {display_score}, Queue: {len(issues)} issue(s).")
        print("Run `uidetox loop` NOW — it will fix them automatically.")
    print("DO NOT STOP. DO NOT run individual commands — the loop handles everything.")
