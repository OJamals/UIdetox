"""Plan command: smart attack plan with component grouping and effort estimation.

Groups issues by component/directory, estimates effort per group, and emits an
optimized attack order (highest impact first = most issues × lowest tier).
"""

import argparse
from pathlib import Path
from collections import defaultdict
from uidetox.state import load_state, load_config
from uidetox.utils import compute_design_score

# Effort estimate per tier (minutes)
_TIER_EFFORT = {"T1": 2, "T2": 8, "T3": 20, "T4": 45}

# Impact weight per tier (higher = more impactful to fix)
_TIER_IMPACT = {"T1": 1, "T2": 3, "T3": 5, "T4": 10}


def _component_key(filepath: str) -> str:
    """Derive component/directory name from a file path."""
    p = Path(filepath)
    parts = p.parts
    # Skip system/absolute path prefixes, find the project-relevant directory
    for i, part in enumerate(parts):
        if part in ("src", "app", "pages", "components", "features", "lib", "modules", "views", "layouts"):
            # Return up to 2 levels deep from the meaningful directory
            remaining = parts[i:]
            if len(remaining) >= 3:
                return str(Path(*remaining[:3]))
            elif len(remaining) >= 2:
                return str(Path(*remaining[:2]))
            return str(Path(*remaining[:1]))
    # Fallback: parent directory
    parent = str(p.parent)
    if parent == "." or parent == "/":
        return "root"
    # Trim to last 2 segments
    parent_parts = Path(parent).parts
    if len(parent_parts) > 2:
        return str(Path(*parent_parts[-2:]))
    return parent


def _categorize_issue(desc: str) -> str:
    """Quick category inference from description."""
    desc_lower = desc.lower()
    category_keywords = {
        "typography": ["font", "typography", "inter", "roboto", "type scale", "line-height", "px font"],
        "color": ["color", "gradient", "palette", "contrast", "dark mode", "purple", "black"],
        "layout": ["layout", "grid", "spacing", "padding", "center", "viewport", "card", "dashboard"],
        "motion": ["animation", "bounce", "pulse", "spin", "transition"],
        "materiality": ["shadow", "glassmorphism", "radius", "glow", "opacity", "blur"],
        "states": ["hover", "focus", "disabled", "loading", "error", "empty"],
        "content": ["copy", "lorem", "generic", "placeholder", "emoji", "oops", "exclamation"],
        "code quality": ["div soup", "z-index", "inline style", "!important", "ternary", "any type", "ts-ignore"],
        "duplication": ["duplicate", "repeated", "copy-paste", "identical"],
        "dead code": ["commented", "unused", "unreachable", "empty handler", "dead", "deprecated", "console"],
    }
    for cat, kws in category_keywords.items():
        if any(kw in desc_lower for kw in kws):
            return cat
    return "other"


def run(args: argparse.Namespace):
    state = load_state()
    config = load_config()
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])

    if not issues:
        print("No issues in queue. Run 'uidetox scan' to find slop.")
        return

    print("╔══════════════════════════════════════════════════════╗")
    print("║              UIdetox Attack Plan                    ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ---- Tier overview ----
    tiers = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    total_effort = 0
    for i in issues:
        t = i.get("tier", "T4")
        tiers[t] = tiers.get(t, 0) + 1
        total_effort += _TIER_EFFORT.get(t, 45)

    print(f"  Total: {len(issues)} issues  |  Resolved: {len(resolved)}  |  Est. effort: ~{total_effort} min")
    print(f"  T1: {tiers['T1']}  T2: {tiers['T2']}  T3: {tiers['T3']}  T4: {tiers['T4']}")
    print()

    # ---- Category breakdown ----
    cat_counts: dict[str, int] = defaultdict(int)
    for i in issues:
        cat = _categorize_issue(i.get("issue", ""))
        cat_counts[cat] += 1

    if cat_counts:
        cats_sorted = sorted(cat_counts.items(), key=lambda x: -x[1])
        cat_line = ", ".join(f"{cat}({n})" for cat, n in cats_sorted)
        print(f"  Categories: {cat_line}")
        print()

    # ---- Group by component ----
    groups: dict[str, list[dict]] = defaultdict(list)
    for i in issues:
        key = _component_key(i.get("file", ""))
        groups[key].append(i)

    # Score each group by impact (sum of tier weights × count)
    group_scores: list[tuple[str, list[dict], int, int]] = []
    for comp, comp_issues in groups.items():
        impact = sum(_TIER_IMPACT.get(i.get("tier", "T4"), 10) for i in comp_issues)
        effort = sum(_TIER_EFFORT.get(i.get("tier", "T4"), 45) for i in comp_issues)
        group_scores.append((comp, comp_issues, impact, effort))

    # Sort: highest impact first, then lowest effort
    group_scores.sort(key=lambda x: (-x[2], x[3]))

    print("  ─── Attack Order (highest impact first) ───")
    print()

    for rank, (comp, comp_issues, impact, effort) in enumerate(group_scores, 1):
        tier_breakdown = defaultdict(int)
        cat_breakdown = defaultdict(int)
        files_in_group = set()
        for i in comp_issues:
            tier_breakdown[i.get("tier", "T4")] += 1
            cat_breakdown[_categorize_issue(i.get("issue", ""))] += 1
            files_in_group.add(i.get("file", ""))

        tier_str = " ".join(f"{t}:{c}" for t, c in sorted(tier_breakdown.items()))
        cat_str = ", ".join(f"{c}" for c, _ in sorted(cat_breakdown.items(), key=lambda x: -x[1])[:3])

        print(f"  {rank}. {comp}")
        print(f"     {len(comp_issues)} issues ({tier_str})  ~{effort}min  [{cat_str}]")
        print(f"     Files: {len(files_in_group)}")

        # Show up to 5 issues per group
        shown = 0
        for i in sorted(comp_issues, key=lambda x: {"T1": 0, "T2": 1, "T3": 2, "T4": 3}.get(x.get("tier", "T4"), 4)):
            if shown >= 5:
                remaining = len(comp_issues) - shown
                print(f"       ... +{remaining} more")
                break
            short_file = Path(i.get("file", "")).name
            print(f"       [{i.get('tier', '?')}] {i.get('id', '?')} {short_file}: {i.get('issue', '?')[:70]}")
            shown += 1
        print()

    # ---- Score context ----
    scores = compute_design_score(state)
    target = config.get("target_score", 95)
    print(f"  ─── Score Context ───")
    filled = scores["blended_score"] // 5
    bar = "█" * filled + "░" * (20 - filled)
    print(f"  Current: [{bar}] {scores['blended_score']}/100  (target: {target})")
    if scores["blended_score"] < target:
        gap = target - scores["blended_score"]
        print(f"  Gap: {gap} points to target")
    print()

    # ---- Agent instruction ----
    print("[AGENT INSTRUCTION]")
    if group_scores:
        top_comp = group_scores[0][0]
        top_count = len(group_scores[0][1])
        print(f"  Highest-impact component: {top_comp} ({top_count} issues)")
        print(f"  Run `uidetox next` to get the batch with full SKILL.md context.")
        print(f"  Fix all issues in the component, then:")
        print(f"    `uidetox batch-resolve ID1 ID2 ... --note 'what you changed'`")
    else:
        print(f"  Run `uidetox next` to get the next issue.")
