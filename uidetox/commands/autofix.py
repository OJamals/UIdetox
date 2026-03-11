"""Autofix command: automatically apply safe T1 fixes."""

import argparse
from uidetox.state import load_state, save_state, load_config


# Category classification + specific replacement guidance
_CATEGORIES = {
    "typography": {
        "keywords": ["font", "typography", "inter", "roboto", "type scale", "line-height", "px font", "letter-spacing", "kerning"],
        "guidance": "Replace with Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale. Use rem/Tailwind scale instead of px. Use Medium (500) and SemiBold (600).",
    },
    "color": {
        "keywords": ["color", "gradient", "black", "palette", "pure black", "hex color", "named css color"],
        "guidance": "Replace pure black with zinc-950/#0f0f0f. Replace purple-blue gradients with a single accent on neutral base. Extract repeated hex literals to CSS variables. See reference/color-palettes.md.",
    },
    "layout": {
        "keywords": ["layout", "grid", "spacing", "viewport", "h-screen", "padding", "center", "flex center", "overpadded"],
        "guidance": "Replace h-screen with min-h-[100dvh]. Use asymmetric grids. Vary spacing scale. Use 'grid place-items-center' instead of verbose flex centering.",
    },
    "motion": {
        "keywords": ["animation", "bounce", "pulse", "spin", "transition"],
        "guidance": "Replace animate-bounce/pulse/spin with CSS transitions (150-300ms ease-out-quart). Add transition-colors/transition-all to hover elements.",
    },
    "materiality": {
        "keywords": ["shadow", "glassmorphism", "radius", "glow", "blur", "opacity", "neon", "gradient text"],
        "guidance": "Use shadow-sm/shadow-md. Replace glassmorphism with solid surfaces + subtle borders. Reduce border-radius to rounded-lg/rounded-xl max. Remove neon glows and gradient text.",
    },
    "states": {
        "keywords": ["hover", "focus", "disabled", "cursor-not-allowed", "missing hover", "missing focus"],
        "guidance": "Add hover:, focus:ring, active: states to all interactive elements. Add disabled:cursor-not-allowed disabled:opacity-50 to disabled elements.",
    },
    "content": {
        "keywords": ["lorem", "generic", "copy", "cliche", "placeholder", "john doe", "acme", "emoji", "oops", "exclamation", "unsplash"],
        "guidance": "Write real draft copy. Use diverse, realistic names. Use organic numbers. Replace Unsplash URLs with picsum.photos. Remove exclamation marks from status messages.",
    },
    "code quality": {
        "keywords": ["z-index", "div", "semantic", "inline style", "!important", "any type", "ts-ignore", "eslint-disable", "ternary", "magic number"],
        "guidance": "Create semantic z-index scale (10/20/30/40/50). Replace divs with semantic HTML5. Extract inline styles. Fix lint/type suppressions instead of disabling.",
    },
    "components": {
        "keywords": ["lucide", "icon", "pill", "badge", "dashboard", "stat-card", "hero"],
        "guidance": "Replace lucide-react with Phosphor/Heroicons. Replace pill badges with squared (rounded-md). Replace hero dashboards with inline metrics.",
    },
    "duplication": {
        "keywords": ["duplicate", "repeated", "copy-paste", "identical", "same className", "same hex"],
        "guidance": "Extract repeated className strings to cn()/cva() utilities. Extract copy-pasted markup into shared components. Merge duplicate media queries. Deduplicate event handlers.",
    },
    "dead code": {
        "keywords": ["commented-out", "unused import", "unreachable", "empty handler", "dead css", "unused state", "deprecated", "console", "no-op", "todo", "fixme"],
        "guidance": "Delete commented-out code (git has history). Remove unused imports via linter. Remove empty handlers. Delete dead CSS classes. Resolve TODOs or convert to tracked issues.",
    },
    "accessibility": {
        "keywords": ["htmlfor", "label", "aria", "alt text", "scrollbar", "border", "divider"],
        "guidance": "Add htmlFor to labels. Use opacity on borders for softer blending. Style or hide scrollbars. Add ARIA labels to icon-only buttons.",
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

    import subprocess
    from pathlib import Path
    
    transforms_dir = Path(__file__).parent.parent / "data" / "transforms"
    
    applied_files = set()
    for cat_name, cat_issues in grouped.items():
        transform_file = transforms_dir / f"{cat_name}.js"
        if transform_file.exists():
            files_to_fix = list(set([i["file"] for i in cat_issues]))
            print(f"\n⚙️  Applying {cat_name} transforms via jscodeshift on {len(files_to_fix)} file(s)...")
            
            for file_path in files_to_fix:
                try:
                    subprocess.run(
                        ["npx", "jscodeshift", "-t", str(transform_file), file_path],
                        capture_output=True, text=True, check=True
                    )
                    applied_files.add(file_path)
                except FileNotFoundError:
                    print("    ⚠️  npx not found. Please install Node.js/npm.")
                    break
                except subprocess.CalledProcessError as e:
                    print(f"    ⚠️  Failed to transform {file_path}: {e.stderr[:100]}...")

    if applied_files:
        print(f"\n✅ Automatically transformed {len(applied_files)} files using jscodeshift.")
        print(f"Run `uidetox rescan` to update the issue queue.")
        return

    config = load_config()
    auto_commit = config.get("auto_commit", False)

    print(f"\n[AGENT INSTRUCTION]")
    print(f"Apply all {len(t1_issues)} T1 fixes listed above, working category by category.")
    print(f"For each fix:")
    print(f"  1. Open the file")
    print(f"  2. Apply the fix using the category guidance above")
    print(f"  3. Run `uidetox resolve <issue_id> --note \"what you changed\"` when done")
    if auto_commit:
        print(f"\n  AUTO-COMMIT is ON — each `resolve` will atomically commit the fix to git.")
    print(f"\nThese are safe, mechanical changes (font swaps, color replacements, spacing).")
    print(f"Apply them all before moving to T2+ issues.")
