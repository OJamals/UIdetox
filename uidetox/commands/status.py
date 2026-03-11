"""Status command: project health dashboard with smart scoring."""

import argparse
import json
from uidetox.state import load_state, load_config


# Recommended fix order hints per category
_CATEGORY_HINTS = {
    "typography": "Start here — font swap is the biggest instant improvement, lowest risk.",
    "color": "Clean up palette — remove AI purple-blue gradients and pure black.",
    "motion": "Add hover/active states — makes the interface feel alive.",
    "layout": "Fix grids and spacing — proper max-width, asymmetric layouts.",
    "materiality": "Replace glassmorphism and oversized shadows with solid surfaces.",
    "states": "Add loading/error/empty states — makes it feel finished.",
    "a11y": "Add focus indicators and ARIA labels — accessibility requirement.",
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

    # Category breakdown (infer from issue descriptions)
    categories = {
        "typography": {"keywords": ["font", "typography", "inter", "roboto", "type scale"], "pending": 0, "resolved": 0},
        "color": {"keywords": ["color", "gradient", "palette", "contrast", "dark mode", "purple", "blue", "black"], "pending": 0, "resolved": 0},
        "layout": {"keywords": ["layout", "grid", "spacing", "padding", "margin", "dashboard", "card", "center", "viewport", "h-screen"], "pending": 0, "resolved": 0},
        "motion": {"keywords": ["animation", "bounce", "pulse", "spin", "transition", "motion", "hover"], "pending": 0, "resolved": 0},
        "states": {"keywords": ["loading", "error", "empty", "skeleton", "disabled", "hover state", "focus"], "pending": 0, "resolved": 0},
        "a11y": {"keywords": ["accessibility", "a11y", "aria", "alt text", "focus", "contrast ratio", "skip-to-content"], "pending": 0, "resolved": 0},
        "materiality": {"keywords": ["shadow", "glassmorphism", "radius", "border", "backdrop", "blur", "glow", "opacity"], "pending": 0, "resolved": 0},
        "content": {"keywords": ["copy", "lorem", "generic", "placeholder", "cliche", "john doe", "acme"], "pending": 0, "resolved": 0},
        "code quality": {"keywords": ["div soup", "semantic", "z-index", "inline style", "import"], "pending": 0, "resolved": 0},
    }
    for issue in issues:
        desc = issue.get("issue", "").lower()
        for cat_name, cat in categories.items():
            if any(kw in desc for kw in cat["keywords"]):
                cat["pending"] += 1
                break
    for issue in resolved:
        desc = issue.get("issue", "").lower()
        for cat_name, cat in categories.items():
            if any(kw in desc for kw in cat["keywords"]):
                cat["resolved"] += 1
                break

    # Smarter health score: Strict Slop Ratio with baseline penalty
    tier_weights = {"T1": 1, "T2": 3, "T3": 5, "T4": 10}

    current_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in issues)
    resolved_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in resolved)
    total_slop = current_slop + resolved_slop

    total_resolved = len(resolved)
    total_found = stats.get("total_found", len(issues) + total_resolved)

    # Baseline penalty: never-scanned projects start at 50, not 100
    if scans_run == 0 and total_slop == 0:
        score = 50  # Unknown quality — haven't scanned yet
    elif total_slop == 0:
        score = 100
    else:
        score = int(100 - ((current_slop / total_slop) * 100))
        score = max(0, min(100, score))

    use_json = getattr(args, "json", False)
    if use_json:
        payload = {
            "design_score": score,
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
    filled = score // 5
    bar = "█" * filled + "░" * (20 - filled)
    print(f"\n  Design Score : [{bar}] {score}/100")
    if scans_run == 0 and total_slop == 0:
        print(f"  (Baseline — run 'uidetox scan' for an accurate score)")
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

    # Category breakdown with actionable hints
    active_cats = {k: v for k, v in categories.items() if v["pending"] > 0 or v["resolved"] > 0}
    if active_cats:
        print()
        print("  ─── Category Breakdown ───")
        for cat_name, cat in active_cats.items():
            total_cat = cat["pending"] + cat["resolved"]
            if total_cat > 0:
                cat_score = int((cat["resolved"] / total_cat) * 100)
                cat_bar = "█" * (cat_score // 10) + "░" * (10 - cat_score // 10)
                print(f"  {cat_name:<14} [{cat_bar}] {cat_score}%  ({cat['pending']} pending, {cat['resolved']} resolved)")
                # Show hint for worst-performing categories
                if cat_score == 0 and cat_name in _CATEGORY_HINTS:
                    print(f"                 ^ {_CATEGORY_HINTS[cat_name]}")

    # Verdict
    if score >= 95 and len(issues) == 0:
        print("\n  EXCELLENT — Interface is clean of AI slop. Queue is empty.")
    elif score >= 95:
        print("\n  Score is high, but some issues remain in the queue.")
    elif score >= 80:
        print("\n  Good progress. A few issues remain — keep pushing.")
    elif score >= 50:
        print("\n  Moderate slop detected. Focus on T1 and T2 first.")
    else:
        print("\n  Heavy slop detected. Run 'uidetox loop' and go.")

    # Agent loop control signal
    print("\n[AGENT LOOP SIGNAL]")
    if score >= 95 and len(issues) == 0:
        print("TARGET REACHED. You may exit the loop.")
    elif len(issues) == 0:
        print(f"Queue is empty but score is {score}. Run 'uidetox rescan' to find more issues.")
    else:
        print(f"Score is {score}, {len(issues)} issue(s) remain. Run 'uidetox next' to continue.")
