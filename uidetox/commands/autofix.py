"""Autofix command: automatically apply safe T1 fixes."""

import argparse
from uidetox.state import load_state, save_state, load_config


# Category classification + specific replacement guidance
_CATEGORIES = {
    "typography": {
        "keywords": ["font", "typography", "inter", "roboto"],
        "guidance": "Replace with Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale.",
    },
    "color": {
        "keywords": ["color", "gradient", "black", "palette", "pure black"],
        "guidance": "Replace pure black with zinc-950/#0f0f0f. Replace purple-blue gradients with a single accent on neutral base. See reference/color-palettes.md for curated schemes.",
    },
    "layout": {
        "keywords": ["layout", "grid", "spacing", "viewport", "h-screen", "padding", "center"],
        "guidance": "Replace h-screen with min-h-[100dvh]. Use asymmetric grids. Vary spacing scale. Add max-width container.",
    },
    "motion": {
        "keywords": ["animation", "bounce", "pulse", "spin"],
        "guidance": "Replace with CSS transitions (150-300ms ease-out-quart). Use transform/opacity only.",
    },
    "materiality": {
        "keywords": ["shadow", "glassmorphism", "radius", "glow", "blur"],
        "guidance": "Use shadow-sm/shadow-md. Replace glassmorphism with solid surfaces + subtle borders. Reduce border-radius to rounded-lg/rounded-xl max.",
    },
    "content": {
        "keywords": ["lorem", "generic", "copy", "cliche", "placeholder", "john doe"],
        "guidance": "Write real draft copy. Use diverse, realistic names. Use organic numbers (47.2% not 99.99%).",
    },
    "code quality": {
        "keywords": ["z-index", "div", "semantic"],
        "guidance": "Create semantic z-index scale (10/20/30/40/50). Replace divs with semantic HTML elements.",
    },
}


def _categorize_issue(issue: dict) -> str:
    """Classify an issue into a category by keyword matching."""
    desc = issue.get("issue", "").lower() + " " + issue.get("command", "").lower()
    for cat_name, cat in _CATEGORIES.items():
        if any(kw in desc for kw in cat["keywords"]):
            return cat_name
    return "other"


def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])

    t1_issues = [i for i in issues if i.get("tier") == "T1"]

    if not t1_issues:
        print("No T1 (quick fix) issues found. Nothing to autofix.")
        return

    dry_run = getattr(args, "dry_run", False)

    # Group by category
    grouped: dict[str, list[dict]] = {}
    for issue in t1_issues:
        cat = _categorize_issue(issue)
        grouped.setdefault(cat, []).append(issue)

    print("==============================")
    print(" UIdetox Autofix")
    print("==============================")
    print(f"Found {len(t1_issues)} T1 issue(s) eligible for autofix:\n")

    for cat_name, cat_issues in grouped.items():
        cat_info = _CATEGORIES.get(cat_name, {})
        guidance = cat_info.get("guidance", "Apply fix as described.")
        print(f"  --- {cat_name.upper()} ({len(cat_issues)} issues) ---")
        print(f"  Guidance: {guidance}")
        for issue in cat_issues:
            print(f"    [{issue['id']}] {issue['file']}: {issue['issue']}")
            print(f"      -> Fix: {issue.get('command', 'manual')}")
        print()

    if dry_run:
        print(f"[DRY RUN] No changes applied. Remove --dry-run to apply.")
        return

    config = load_config()
    auto_commit = config.get("auto_commit", False)

    print(f"[AGENT INSTRUCTION]")
    print(f"Apply all {len(t1_issues)} T1 fixes listed above, working category by category.")
    print(f"For each fix:")
    print(f"  1. Open the file")
    print(f"  2. Apply the fix using the category guidance above")
    print(f"  3. Run `uidetox resolve <issue_id> --note \"what you changed\"` when done")
    if auto_commit:
        print(f"\n  AUTO-COMMIT is ON — each `resolve` will atomically commit the fix to git.")
    print(f"\nThese are safe, mechanical changes (font swaps, color replacements, spacing).")
    print(f"Apply them all before moving to T2+ issues.")
