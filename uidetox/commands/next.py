"""Next command: pops the highest-priority issue with full context."""

import argparse
import sys
from pathlib import Path
from uidetox.state import load_state, load_config


def _get_skill_path() -> Path | None:
    """Locate SKILL.md — check project root first, then bundled data."""
    cwd = Path.cwd()
    # 1. Project root (installed via update-skill)
    if (cwd / "SKILL.md").exists():
        return cwd / "SKILL.md"
    # 2. Claude skills directory
    claude_skill = cwd / ".claude" / "skills" / "uidetox" / "SKILL.md"
    if claude_skill.exists():
        return claude_skill
    # 3. Bundled inside pip package
    pkg_data = Path(__file__).resolve().parent.parent / "data" / "SKILL.md"
    if pkg_data.exists():
        return pkg_data
    return None


# SKILL.md context fragments keyed by issue pattern keywords
SKILL_CONTEXT = {
    "typography": "TYPOGRAPHY RULES: Never use Inter, Roboto, or system-ui as primary. Use Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale (display, body, caption).",
    "font": "TYPOGRAPHY RULES: Never use Inter, Roboto, or system-ui as primary. Use Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale (display, body, caption).",
    "gradient": "COLOR RULES: Never use purple-blue gradients. Use a single high-contrast accent color on neutral base. Colors should feel intentional, not generated.",
    "palette": "COLOR RULES: Never use purple-blue gradients. Use a single high-contrast accent color on neutral base. Colors should feel intentional, not generated.",
    "black": "COLOR RULES: Never use pure black (#000000). Use tinted dark neutrals (zinc-950, slate-900). Pure black feels digital, not designed.",
    "icon": "COMPONENT RULES: Avoid default lucide-react. Use Phosphor Icons, Heroicons, or custom SVGs. Icons should match brand personality.",
    "lucide": "COMPONENT RULES: Avoid default lucide-react. Use Phosphor Icons, Heroicons, or custom SVGs. Icons should match brand personality.",
    "radius": "MATERIALITY RULES: Avoid oversized radii (2xl/3xl) except for avatars/modals. Use rounded-lg or rounded-xl for cards. Consistent radius = professional.",
    "shadow": "MATERIALITY RULES: Avoid oversized shadows (2xl/3xl). Use shadow-sm or shadow-md. Prefer border-based elevation over drop shadows.",
    "glassmorphism": "MATERIALITY RULES: Avoid glassmorphism (backdrop-blur + transparency). Use solid surfaces with subtle borders or shadow hierarchy.",
    "grid": "LAYOUT RULES: Avoid symmetric 3-column grids. Use asymmetric layouts, varied column widths, or masonry. Break the predictable card-grid pattern.",
    "column": "LAYOUT RULES: Avoid symmetric 3-column grids. Use asymmetric layouts, varied column widths, or masonry. Break the predictable card-grid pattern.",
    "bounce": "MOTION RULES: Never use animate-bounce/pulse/spin. Use CSS transitions (150-300ms ease) or spring physics. Motion should be purposeful, not decorative.",
    "animation": "MOTION RULES: Never use animate-bounce/pulse/spin. Use CSS transitions (150-300ms ease) or spring physics. Motion should be purposeful, not decorative.",
    "dark": "THEMING RULES: Every light surface (bg-white, bg-gray-100) MUST have a dark: variant. Use dark:bg-zinc-900 or dark:bg-slate-900.",
    "hover": "INTERACTION RULES: Every interactive element needs hover, focus, and active states. Use transition-colors duration-150. Missing states = unfinished UI.",
    "dashboard": "LAYOUT RULES: Avoid hero metric dashboards. Weave data into narrative flow. Use contextual inline metrics over isolated stat cards.",
    "spacing": "SPACING RULES: Avoid uniform spacing (all p-4). Vary spacing scale (p-3, p-5, p-6) to create visual rhythm and hierarchy.",
    "opacity": "MATERIALITY RULES: No excessive layered transparency. Use solid surface colors; reserve transparency for overlays and modals only.",
    "copy": "UX WRITING RULES: Never use generic startup copy ('Revolutionize your workflow'). Write specific, benefit-driven, human-sounding UI text.",
    "loading": "STATE RULES: Every data-dependent component needs loading, error, and empty states. Use skeleton loaders, not spinners. Missing states = unfinished UI.",
    "error": "STATE RULES: Every data-dependent component needs loading, error, and empty states. Show actionable error messages, not generic 'Something went wrong'.",
    "empty": "STATE RULES: Every data-dependent component needs loading, error, and empty states. Empty states are design opportunities, not afterthoughts.",
}


def _get_relevant_context(batch: list) -> list[str]:
    """Extract relevant SKILL.md fragments based on issue descriptions."""
    seen = set()
    contexts = []
    for issue in batch:
        desc = (issue.get("issue", "") + " " + issue.get("command", "")).lower()
        for keyword, context in SKILL_CONTEXT.items():
            if keyword in desc and context not in seen:
                seen.add(context)
                contexts.append(context)
    return contexts


def run(args: argparse.Namespace):
    state = load_state()
    issues = state.get("issues", [])
    resolved_count = len(state.get("resolved", []))

    if not issues:
        print("🎉 Queue is empty! No pending issues.")
        print("\n[AGENT LOOP SIGNAL]")
        print("Run 'uidetox status' to check if target score is reached.")
        print("If score < target, run 'uidetox rescan' to find more issues.")
        sys.exit(1)

    # Sort by tier priority: T1 > T2 > T3 > T4
    tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
    sorted_issues = sorted(issues, key=lambda x: tiers_order.get(x.get("tier", "T4"), 5))
    
    # Get the file of the highest priority issue
    target_file = sorted_issues[0].get("file")
    
    # Gather all issues for this file (limit batch to 5 to avoid overwhelming the agent)
    batch = [i for i in sorted_issues if i.get("file") == target_file][:5]
    
    remaining = len(issues) - len(batch)
    tiers = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    for i in issues:
        t = i.get("tier", "T4")
        if t in tiers:
            tiers[t] += 1

    print("╔═════════════════════════════════════════════╗")
    print(f"║ Next Target: {target_file}")
    print("╚═════════════════════════════════════════════╝")
    print(f"  Batching {len(batch)} issue(s) for this file:")
    print()
    
    for idx, iss in enumerate(batch):
        print(f"  [{idx+1}] ID: {iss['id']} | Tier: {iss['tier']}")
        print(f"      Issue  : {iss['issue']}")
        print(f"      Action : {iss.get('command', 'manual fix')}")
        print()

    # Inject relevant SKILL.md context
    contexts = _get_relevant_context(batch)
    if contexts:
        print("  ━━━ SKILL.md DESIGN RULES (relevant to this batch) ━━━")
        for ctx in contexts:
            print(f"  ▸ {ctx}")
        print()

    # Point the agent to the full SKILL.md for deeper reference
    skill_path = _get_skill_path()
    if skill_path:
        print(f"  📖 Full design rules: {skill_path}")
        print(f"     Read this file for complete anti-pattern catalog and design engineering rules.")
        print()

    print(f"  Queue : {remaining} remaining after this batch")
    print(f"  Stats : {tiers['T1']}×T1, {tiers['T2']}×T2, {tiers['T3']}×T3, {tiers['T4']}×T4 | {resolved_count} resolved so far")
    print()
    # Auto-commit awareness
    config = load_config()
    auto_commit = config.get("auto_commit", False)

    print("[AGENT INSTRUCTION]")
    print(f"1. Read the file: {target_file}")
    if skill_path:
        print(f"2. Read SKILL.md at {skill_path} for the full design rules relevant to these issues.")
    print(f"{'3' if skill_path else '2'}. Fix ALL {len(batch)} issue(s) listed above following the SKILL.md rules shown.")
    print(f"{'4' if skill_path else '3'}. Verify the fixes don't break functionality.")
    print(f"{'5' if skill_path else '4'}. Run the resolve command for each issue, adding a mandatory --note:")
    for iss in batch:
        print(f"   uidetox resolve {iss['id']} --note \"what you changed\"")
    if auto_commit:
        print("   📦 AUTO-COMMIT is ON — each resolve atomically commits the fix to git.")
    print(f"{'6' if skill_path else '5'}. Then immediately run: uidetox next")
