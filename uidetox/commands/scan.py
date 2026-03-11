"""Scan command — enhanced with tooling auto-detection and mechanical checks."""

import argparse
import uuid
from uidetox.analyzer import analyze_directory, RULES
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import add_issue, ensure_uidetox_dir, load_config, save_config, increment_scans
from uidetox.tooling import detect_all
from uidetox.history import save_run_snapshot
from uidetox.memory import save_scan_summary, save_session, log_progress


# Categories auto-covered by static analyzer, mapped to rule IDs
_AUTO_CATEGORIES = {
    "typography": {"TYPOGRAPHY_SLOP"},
    "color": {"COLOR_GRADIENT_SLOP", "COLOR_BLACK_SLOP", "CSS_GRADIENT_SLOP", "CSS_PURE_BLACK_SLOP"},
    "layout": {"LAYOUT_MATH_SLOP", "CENTER_BIAS_SLOP", "CARD_NESTING_SLOP", "OVERPADDED_LAYOUT_SLOP", "VIEWPORT_HEIGHT_SLOP"},
    "motion": {"BOUNCE_ANIMATION_SLOP"},
    "materiality": {"GLASSMORPHISM_SLOP", "SHADOW_SLOP", "MATERIALITY_RADIUS_SLOP", "NEON_GLOW_SLOP", "OPACITY_ABUSE_SLOP", "GRADIENT_TEXT_SLOP"},
    "states": {"MISSING_HOVER_STATES", "MISSING_FOCUS_SLOP", "MISSING_DARK_MODE"},
    "content": {"GENERIC_COPY_SLOP", "AI_COPY_CLICHE_SLOP", "LOREM_IPSUM_SLOP", "GENERIC_NAME_SLOP", "EMOJI_HEAVY_SLOP"},
    "code quality": {"DIV_SOUP_SLOP", "HARDCODED_ZINDEX_SLOP"},
    "components": {"HERO_DASHBOARD_SLOP", "ICONOGRAPHY_SLOP", "PILL_BADGE_SLOP"},
}

# Categories that ALWAYS need manual agent audit (not automatable via regex)
_MANUAL_CATEGORIES = {
    "accessibility": "ARIA labels, contrast ratios, skip-to-content, keyboard nav",
    "responsive": "Mobile collapse, container queries, fluid typography",
    "forms & inputs": "Label placement, validation, error messaging, input states",
    "strategic omissions": "404 page, legal links, back navigation, favicon",
}


def run(args: argparse.Namespace):
    ensure_uidetox_dir()
    config = load_config()
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)

    # Auto-detect tooling if not already configured
    if not config.get("tooling"):
        profile = detect_all(args.path)
        config["tooling"] = profile.to_dict()
        save_config(config)

    tooling = config.get("tooling", {})

    print("╔══════════════════════════════╗")
    print("║      UIdetox Full Scan       ║")
    print("╚══════════════════════════════╝")
    print(f"Path: {args.path}")
    print(f"Dials: VARIANCE={variance}, MOTION={intensity}, DENSITY={density}")

    # Dial-specific audit guidance
    print(f"\n  Design Dial Effects on This Audit:")
    if variance > 4:
        print(f"    VARIANCE={variance} → Centered hero sections are BANNED. Force asymmetric layouts.")
    if variance > 7:
        print(f"    VARIANCE={variance} → Push for masonry, overlapping elements, offset margins.")
    if intensity > 5:
        print(f"    MOTION={intensity}  → Require entrance animations, staggered lists, spring physics.")
    if intensity > 7:
        print(f"    MOTION={intensity}  → Require scroll-triggered reveals, magnetic buttons, parallax.")
    if density < 5:
        print(f"    DENSITY={density}  → Art gallery mode. Generous whitespace, spacious layouts.")
    if density > 7:
        print(f"    DENSITY={density}  → Cockpit mode. Dense data, monospace numbers, compact spacing.")

    # Report detected tooling
    pm = tooling.get("package_manager")
    ts = tooling.get("typescript")
    linter = tooling.get("linter")
    fmt = tooling.get("formatter")
    frontends = tooling.get("frontend", [])
    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])

    print(f"\nDetected Tooling:")
    print(f"  Package Manager : {pm or 'none'}")
    print(f"  TypeScript      : {ts['config_file'] if ts else 'no'}")
    print(f"  Linter          : {linter['name'] if linter else 'none'}")
    print(f"  Formatter       : {fmt['name'] if fmt else 'none'}")
    if frontends:
        print(f"  Frontend        : {', '.join(f['name'] for f in frontends)}")
    if backends:
        print(f"  Backend         : {', '.join(b['name'] for b in backends)}")
    if databases:
        print(f"  Database/ORM    : {', '.join(d['name'] for d in databases)}")
    if apis:
        print(f"  API Layer       : {', '.join(a['name'] for a in apis)}")

    # Mechanical checks instructions
    print(f"\n[STEP 1 — MECHANICAL CHECKS]")
    if ts or linter or fmt:
        print(f"Run 'uidetox check' to execute tsc → lint → format in sequence.")
        print(f"This queues all compiler/lint errors as T1 issues automatically.")
        print(f"Alternatively, run individually: 'uidetox tsc', 'uidetox lint', 'uidetox format'")
    else:
        print(f"No mechanical tools detected. Skipping to design audit.")

    # Design audit instructions
    print(f"\n[STEP 1.5 — STATIC SLOP ANALYSIS]")

    # Enforce Zones and Suppressions
    ignore_patterns = config.get("ignore_patterns", [])
    if ignore_patterns:
        print("\n  [!] ACTIVE SUPPRESSIONS (Do NOT flag issues matching these patterns):")
        for p in ignore_patterns:
            print(f"      - {p}")

    overrides = config.get("zone_overrides", {})
    if overrides:
        print(f"\n  [!] ACTIVE ZONE OVERRIDES ({len(overrides)}):")
        print("      Run 'uidetox zone show' for details.")

    print("\n  [!] ZONING RULES:")
    print("      SKIP all files in 'vendor' or 'generated' zones (e.g., node_modules, dist, .next).")
    print("      ONLY audit 'production' and 'config' zones.")

    print(f"\n[!] RUNNING STATIC SLOP ANALYZER ({len(RULES)} rules)...")
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    slop_issues = analyze_directory(
        args.path,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
        design_variance=variance,
    )
    queued_count = 0
    triggered_rules: set[str] = set()
    for issue in slop_issues:
        if not _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            issue_id = f"SCAN-{str(uuid.uuid4()).split('-')[0][:6].upper()}" # type: ignore
            new_issue = {
                "id": issue_id,
                "file": issue['file'],
                "tier": issue["tier"],
                "issue": issue["issue"],
                "command": issue["command"]
            }
            add_issue(new_issue)
            queued_count += 1
            # Track which rules fired for the coverage report
            for rule in RULES:
                if rule["description"] in issue["issue"]:
                    triggered_rules.add(rule["id"])

    if queued_count > 0:
        print(f"  Auto-queued {queued_count} deterministic AI slop anti-patterns.")
    else:
        print(f"  No deterministic AI slop detected by static analysis.")

    # Category coverage report
    print(f"\n  ─── Category Coverage Report ───")
    for cat, rule_ids in _AUTO_CATEGORIES.items():
        fired = rule_ids & triggered_rules
        status = f"({len(fired)} hit)" if fired else "(clean)"
        print(f"    {cat:<14} : auto-scanned {status}")
    for cat, desc in _MANUAL_CATEGORIES.items():
        print(f"    {cat:<14} : NEEDS MANUAL AUDIT — {desc}")

    print(f"\n[STEP 1.7 — CODE INTELLIGENCE (optional)]")
    print(f"Use GitNexus to build a knowledge graph before deep file reading:")
    print(f"  npx gitnexus analyze .")
    print(f"  npx gitnexus query <concept>   — find execution flows by concept")
    print(f"  npx gitnexus impact <symbol>   — check blast radius before refactoring")

    print(f"\n[STEP 2 — DESIGN AUDIT]")
    print(f"Read all frontend files in '{args.path}'.")
    print(f"Evaluate against SKILL.md. For each issue found by the agent, run:")
    print(f"  uidetox add-issue --file <path> --tier <T1-T4> --issue <description> --fix-command <cmd>")

    # Reference files for the agent to consult
    print(f"\n  Reference Files for Deep-Dive:")
    print(f"    reference/typography.md       — Type scales, font pairing, loading")
    print(f"    reference/color-and-contrast.md — OKLCH, tinted neutrals, dark mode")
    print(f"    reference/spatial-design.md    — Grids, spacing systems, hierarchy")
    print(f"    reference/motion-design.md     — Easing curves, timing, reduced motion")
    print(f"    reference/interaction-design.md — Forms, focus, loading patterns")
    print(f"    reference/anti-patterns.md     — Full banned pattern catalog")
    print(f"    reference/creative-arsenal.md  — Advanced layout and motion concepts")

    # Full-stack integration instructions
    if backends or databases or apis:
        print(f"\n[STEP 3 — FULL-STACK INTEGRATION]")
        print(f"Check for integration issues between layers:")
        print(f"  - DTO shapes match between frontend and backend")
        print(f"  - Frontend forms respect database constraints")
        print(f"  - Backend errors surfaced properly in UI (loading/error/empty states)")
        print(f"  - Type safety across API boundaries")
        if apis:
            print(f"  - API contract validation ({', '.join(a['name'] for a in apis)})")
        if databases:
            print(f"  - Schema alignment ({', '.join(d['name'] for d in databases)})")

    print(f"\nWhen finished, run 'uidetox plan' then 'uidetox next'.")
    increment_scans()
    save_run_snapshot(trigger="scan")

    # Auto-save scan summary and session progress
    _save_scan_to_memory(slop_issues, queued_count, triggered_rules, args.path)
    save_session(phase="scan_complete", last_command="scan",
                 context=f"Found {queued_count} issues in {args.path}")
    log_progress("scan", f"Scanned {args.path}: {queued_count} issues queued")


def _save_scan_to_memory(slop_issues: list, queued_count: int,
                         triggered_rules: set, scan_path: str):
    """Auto-save scan results to memory for review without re-scanning."""
    # Count by tier
    by_tier: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    by_category: dict[str, int] = {}
    file_counts: dict[str, int] = {}

    for issue in slop_issues:
        tier = issue.get("tier", "T4")
        by_tier[tier] = by_tier.get(tier, 0) + 1

        # Infer category from issue text
        desc = issue.get("issue", "").lower()
        cat = _infer_category(desc)
        by_category[cat] = by_category.get(cat, 0) + 1

        f = issue.get("file", "")
        file_counts[f] = file_counts.get(f, 0) + 1

    # Sort files by issue count
    top_files = sorted(file_counts.keys(), key=lambda f: file_counts[f], reverse=True)

    save_scan_summary(
        total_found=queued_count,
        by_tier=by_tier,
        by_category=by_category,
        files_scanned=len(file_counts),
        top_files=top_files,
    )


def _infer_category(desc: str) -> str:
    """Infer issue category from description text."""
    category_keywords = {
        "typography": ["font", "typography", "inter", "type scale"],
        "color": ["color", "gradient", "palette", "contrast", "dark mode", "purple", "black"],
        "layout": ["layout", "grid", "spacing", "padding", "margin", "dashboard", "card", "center"],
        "motion": ["animation", "bounce", "pulse", "spin", "transition", "motion"],
        "materiality": ["shadow", "glassmorphism", "radius", "border", "backdrop", "blur", "glow"],
        "states": ["loading", "error", "empty", "skeleton", "disabled", "hover", "focus"],
        "content": ["copy", "lorem", "generic", "placeholder", "cliche", "emoji"],
        "code quality": ["div soup", "semantic", "z-index", "inline style"],
    }
    for cat, keywords in category_keywords.items():
        if any(kw in desc for kw in keywords):
            return cat
    return "other"
