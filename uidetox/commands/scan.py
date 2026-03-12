"""Scan command -- unified static + subjective analysis in a single pass.

Implements the desloppify flow: Scan Codebase -> generate score -> both
Mechanical Issues (static analyzer) AND Subjective Analysis (LLM review)
happen together, with mechanical informing subjective.
"""

import argparse
import sys
import uuid
from pathlib import Path
from uidetox.analyzer import analyze_directory, RULES
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import (
    batch_add_issues, load_config, load_state,
    save_config, increment_scans,
)
from uidetox.tooling import detect_all
from uidetox.history import save_run_snapshot
from uidetox.memory import save_scan_summary, save_session, log_progress
from uidetox.utils import compute_design_score, categorize_issue


# Categories auto-covered by static analyzer, mapped to rule IDs
_AUTO_CATEGORIES = {
    "typography": {"TYPOGRAPHY_SLOP", "HARDCODED_PX_FONT_SLOP", "TIGHT_LINE_HEIGHT_SLOP"},
    "color": {"COLOR_GRADIENT_SLOP", "COLOR_BLACK_SLOP", "CSS_GRADIENT_SLOP", "CSS_PURE_BLACK_SLOP", "RAW_COLOR_SLOP", "DUPLICATE_COLOR_LITERAL"},
    "layout": {"LAYOUT_MATH_SLOP", "CENTER_BIAS_SLOP", "CARD_NESTING_SLOP", "OVERPADDED_LAYOUT_SLOP", "VIEWPORT_HEIGHT_SLOP", "LAZY_FLEX_CENTER_SLOP"},
    "motion": {"BOUNCE_ANIMATION_SLOP", "MISSING_TRANSITION_SLOP"},
    "materiality": {"GLASSMORPHISM_SLOP", "SHADOW_SLOP", "MATERIALITY_RADIUS_SLOP", "NEON_GLOW_SLOP", "OPACITY_ABUSE_SLOP", "GRADIENT_TEXT_SLOP"},
    "states": {"MISSING_HOVER_STATES", "MISSING_FOCUS_SLOP", "MISSING_DARK_MODE", "DISABLED_NO_CURSOR_SLOP"},
    "content": {"GENERIC_COPY_SLOP", "AI_COPY_CLICHE_SLOP", "LOREM_IPSUM_SLOP", "GENERIC_NAME_SLOP", "EMOJI_HEAVY_SLOP", "EXCLAMATION_UX_SLOP", "OOPS_ERROR_SLOP"},
    "code quality": {"DIV_SOUP_SLOP", "HARDCODED_ZINDEX_SLOP", "INLINE_STYLE_SLOP", "IMPORTANT_ABUSE_SLOP", "NESTED_TERNARY_SLOP", "MAGIC_NUMBER_SLOP", "ANY_TYPE_SLOP", "TS_IGNORE_SLOP", "DISABLED_LINT_RULE"},
    "components": {"HERO_DASHBOARD_SLOP", "ICONOGRAPHY_SLOP", "PILL_BADGE_SLOP"},
    "duplication": {"DUPLICATE_TAILWIND_BLOCK", "DUPLICATE_COLOR_LITERAL", "COPY_PASTE_COMPONENT", "DUPLICATE_HANDLER", "REPEATED_MEDIA_QUERY"},
    "dead code": {"COMMENTED_OUT_CODE", "UNUSED_IMPORT", "UNREACHABLE_CODE", "EMPTY_HANDLER", "DEAD_CSS_CLASS", "UNUSED_STATE", "DEPRECATED_LIFECYCLE", "CONSOLE_LOG_SLOP", "TODO_FIXME_SLOP"},
}

# Categories that ALWAYS need manual agent audit (not automatable via regex)
_MANUAL_CATEGORIES = {
    "accessibility": "ARIA labels, contrast ratios, skip-to-content, keyboard nav",
    "responsive": "Mobile collapse, container queries, fluid typography",
    "forms & inputs": "Label placement, validation, error messaging, input states",
    "strategic omissions": "404 page, legal links, back navigation, favicon",
    "architecture": "Component boundaries, separation of concerns, data flow patterns",
    "elegance": "Visual rhythm, spatial harmony, intentional asymmetry, craft details",
}


def run(args: argparse.Namespace):

    # Validate scan path exists
    scan_path = Path(args.path)
    if not scan_path.exists():
        print(f"Error: Scan path '{args.path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)
    target = config.get("target_score", 95)

    # Auto-detect tooling if not already configured
    if not config.get("tooling"):
        profile = detect_all(args.path)
        config["tooling"] = profile.to_dict()
        save_config(config)

    tooling = config.get("tooling", {})

    print("+" + "=" * 58 + "+")
    print("| SCAN CODEBASE -- Static Analysis + Subjective Review     |")
    print("+" + "=" * 58 + "+")
    print(f"  Path  : {args.path}")
    print(f"  Dials : VARIANCE={variance}  MOTION={intensity}  DENSITY={density}")
    print()

    # --- Tooling Summary ---
    pm = tooling.get("package_manager")
    ts = tooling.get("typescript")
    linter = tooling.get("linter")
    fmt = tooling.get("formatter")
    frontends = tooling.get("frontend", [])
    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])

    print(f"  Tooling: pkg={pm or 'none'}, tsc={'yes' if ts else 'no'}, lint={linter['name'] if linter else 'none'}, fmt={fmt['name'] if fmt else 'none'}")
    if frontends:
        print(f"           frontend={', '.join(f['name'] for f in frontends)}")
    if backends or databases or apis:
        layers = []
        if backends:
            layers.append(f"backend={', '.join(b['name'] for b in backends)}")
        if databases:
            layers.append(f"db={', '.join(d['name'] for d in databases)}")
        if apis:
            layers.append(f"api={', '.join(a['name'] for a in apis)}")
        print(f"           {', '.join(layers)}")
    print()

    # --- Suppressions & Zones ---
    ignore_patterns = config.get("ignore_patterns", [])
    overrides = config.get("zone_overrides", {})
    if ignore_patterns:
        print(f"  Active suppressions: {len(ignore_patterns)} pattern(s)")
    if overrides:
        print(f"  Active zone overrides: {len(overrides)}")

    # ===========================================================
    # PART 1: MECHANICAL ISSUES (deterministic static analysis)
    # ===========================================================
    print()
    print("=" * 58)
    print(" PART 1: MECHANICAL ISSUES (static analyzer)")
    print("=" * 58)

    # Run tsc/lint/format pre-pass if tooling is available
    if ts or linter or fmt:
        print("  Pre-check: run `uidetox check --fix` to clear compiler/lint/format errors first.")
        print()

    # Run static slop analyzer
    print(f"  Running {len(RULES)}-rule deterministic anti-slop analyzer...")
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    slop_issues = analyze_directory(
        args.path,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
        design_variance=variance,
    )
    detected_count = 0
    triggered_rules: set[str] = set()
    new_issues: list[dict] = []
    for issue in slop_issues:
        if not _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            issue_id = f"SCAN-{uuid.uuid4().hex[:8].upper()}"
            new_issues.append({
                "id": issue_id,
                "file": issue['file'],
                "tier": issue["tier"],
                "issue": issue["issue"],
                "command": issue["command"]
            })
            detected_count += 1
            for rule in RULES:
                if rule["description"] in issue["issue"]:
                    triggered_rules.add(rule["id"])

    # Batch-add all issues in a single state write
    batch_result = {"added": 0, "updated": 0, "skipped": 0}
    if new_issues:
        batch_result = batch_add_issues(new_issues)

    queued_count = batch_result["added"]
    if queued_count > 0:
        print(f"  -> Queued {queued_count} mechanical anti-pattern issues.")
    else:
        print(f"  -> No mechanical anti-patterns detected.")
    if batch_result["updated"] > 0:
        print(f"  -> Refreshed {batch_result['updated']} matching pending issue(s) with sharper guidance/severity.")
    if batch_result["skipped"] > 0:
        print(f"  -> Skipped {batch_result['skipped']} duplicate pending issue(s) already in the queue.")

    # Category coverage (compact)
    print()
    auto_hits = []
    auto_clean = []
    for cat, rule_ids in _AUTO_CATEGORIES.items():
        fired = rule_ids & triggered_rules
        if fired:
            auto_hits.append(f"{cat}({len(fired)})")
        else:
            auto_clean.append(cat)
    if auto_hits:
        print(f"  Issues in : {', '.join(auto_hits)}")
    if auto_clean:
        print(f"  Clean     : {', '.join(auto_clean)}")
    manual_list = [f"{cat}" for cat in _MANUAL_CATEGORIES]
    print(f"  Need audit: {', '.join(manual_list)}")

    # Full-stack integration checks
    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])
    has_fullstack = bool(backends or databases or apis)
    if has_fullstack:
        print()
        print("  Full-stack: check DTO alignment, type safety, error surfacing across layers.")

    # ===========================================================
    # PART 2: SUBJECTIVE ANALYSIS (LLM-driven design review)
    # ===========================================================
    print()
    print("=" * 58)
    print(" PART 2: SUBJECTIVE ANALYSIS (LLM design review)")
    print("=" * 58)
    print()
    print("  The mechanical analysis above INFORMS this subjective review.")
    print("  Read every frontend file. Evaluate the holistic design quality.")
    print()

    # ---- VISUAL DESIGN & AESTHETICS (40 pts) ----
    print("  A. VISUAL DESIGN & AESTHETICS (0-40)")
    print("  " + "-" * 50)
    print("    STYLING & ELEGANCE (0-15)")
    print("      Surface textures, color relationships, shadow/border craft.")
    print("      Does it feel polished or rough? Premium or cheap?")
    print("      Is there visual rhythm — intentional contrast between dense and airy?")
    print()
    print("    TYPOGRAPHY (0-10)")
    print("      Font choice, weight spectrum, scale, kerning, line-height.")
    print("      Is there a clear type hierarchy (display, body, caption)?")
    print("      Are weights intentional (500/600, not just 400/700)?")
    print()
    print("    LAYOUT & SPATIAL DESIGN (0-15)")
    print("      Grid structure, whitespace, alignment, responsive behavior.")
    print("      Is the layout compositional or just stacked divs?")
    print("      Does spacing create grouping and hierarchy, not just padding?")
    print()

    # ---- DESIGN SYSTEM & COHERENCE (30 pts) ----
    print("  B. DESIGN SYSTEM & COHERENCE (0-30)")
    print("  " + "-" * 50)
    print("    CONSISTENCY (0-15)")
    print("      Unified tokens, spacing scale, color palette, component patterns.")
    print("      Does the same element look the same everywhere?")
    print("      Would a new developer know the design system from reading the code?")
    print()
    print("    IDENTITY (0-15)")
    print("      Does this feel designed, not generated?")
    print("      Is there an intentional aesthetic point-of-view?")
    print("      Would someone ask 'what tool made this?' (bad) or 'who designed this?' (good)")
    print()

    # ---- INTERACTION & CRAFT (20 pts) ----
    print("  C. INTERACTION & CRAFT (0-20)")
    print("  " + "-" * 50)
    print("    STATES & MICRO-INTERACTIONS (0-10)")
    print("      Hover, focus, active, disabled, loading, empty, error states.")
    print("      Transitions, animations, feedback on user actions.")
    print("      Does the interface feel alive and responsive to input?")
    print()
    print("    EDGE CASES & POLISH (0-10)")
    print("      Error boundaries, empty states, skeleton screens, truncation.")
    print("      Graceful degradation, mobile edge cases, keyboard navigation.")
    print("      Does the squint test pass — clear hierarchy at a glance?")
    print()

    # ---- ARCHITECTURE & COHERENCE (10 pts) ----
    print("  D. ARCHITECTURE & CODE QUALITY (0-10)")
    print("  " + "-" * 50)
    print("    Component structure, file organization, naming conventions.")
    print("    Separation of concerns (logic/presentation/data).")
    print("    Reusability, composability, prop/API surface area.")
    if has_fullstack:
        print("    DTO alignment: do frontend types match backend schemas?")
        print("    Error surfacing: do API errors appear as meaningful UI feedback?")
        print("    Data flow: is fetching/caching/mutation coherent across the stack?")
    print()

    # Dial-aware review guidance (compact)
    dial_notes = []
    if variance > 4:
        dial_notes.append(f"VARIANCE={variance}: centered heroes BANNED, push asymmetric layouts")
    if variance > 7:
        dial_notes.append(f"VARIANCE={variance}: masonry, overlapping elements, offset margins")
    if intensity > 5:
        dial_notes.append(f"MOTION={intensity}: entrance animations, staggered lists required")
    if intensity > 7:
        dial_notes.append(f"MOTION={intensity}: scroll-triggered reveals, spring physics")
    if density < 5:
        dial_notes.append(f"DENSITY={density}: art gallery mode, generous whitespace")
    if density > 7:
        dial_notes.append(f"DENSITY={density}: cockpit mode, dense data, compact spacing")
    if dial_notes:
        print("  Dial constraints for this review:")
        for note in dial_notes:
            print(f"    -> {note}")
        print()

    print("  For each new issue found, queue it:")
    print('    uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    print()
    print("  When review is complete, record your subjective score:")
    print("    uidetox review --score <N>   (0-100, sum of A+B+C+D above)")
    print()

    # ===========================================================
    # SCORE CHECK: Target reached?
    # ===========================================================
    increment_scans()
    save_run_snapshot(trigger="scan")
    _save_scan_to_memory(new_issues, queued_count, triggered_rules, args.path)
    save_session(phase="scan_complete", last_command="scan",
                 context=f"Detected {detected_count} issues in {args.path}; queued {queued_count}")
    log_progress("scan", f"Scanned {args.path}: detected={detected_count}, queued={queued_count}, updated={batch_result['updated']}, skipped={batch_result['skipped']}")

    # Compute current score and show target check
    state = load_state()
    scores = compute_design_score(state)
    score = scores["blended_score"]
    if score is None:
        score = 0  # No scan history yet
    queue_size = len(state.get("issues", []))

    print("=" * 58)
    print(" TARGET SCORE CHECK")
    print("=" * 58)
    filled = max(0, score // 5)
    bar = "#" * filled + "." * (20 - filled)
    print(f"  Design Score : [{bar}] {score}/100  (target: {target})")
    print(f"  Queue        : {queue_size} issue(s)")

    if score >= target and queue_size == 0:
        print()
        print(f"  TARGET REACHED -- Score >= {target} and queue is empty.")
        print("  -> Run `uidetox finish` to finalize.")
    else:
        print()
        if queue_size > 0:
            print(f"  Score < {target} or queue non-empty -> enter Fix Loop.")
            print("  -> Run `uidetox next` to start fixing.")
        else:
            print(f"  Queue empty but score < {target} -> subjective review needed.")
            print("  -> Complete Part 2 above, then `uidetox review --score <N>`")
            print("  -> Then `uidetox rescan` to discover deeper issues.")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    if score >= target and queue_size == 0:
        print("TARGET REACHED. Run `uidetox finish` NOW.")
    elif queue_size > 0:
        print(f"Scan complete: {queue_size} issues queued. Run `uidetox next` NOW.")
        print("DO NOT STOP. Begin the autonomous fix loop immediately.")
    else:
        print("Scan complete with empty queue. Complete subjective review above,")
        print("then `uidetox review --score <N>` followed by `uidetox status`.")
    print()


def _save_scan_to_memory(slop_issues: list, queued_count: int,
                         triggered_rules: set, scan_path: str):
    """Auto-save scan results to memory for review without re-scanning."""
    by_tier: dict[str, int] = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    by_category: dict[str, int] = {}
    file_counts: dict[str, int] = {}

    for issue in slop_issues:
        tier = issue.get("tier", "T4")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        desc = issue.get("issue", "").lower()
        cat = categorize_issue(desc)
        by_category[cat] = by_category.get(cat, 0) + 1
        f = issue.get("file", "")
        file_counts[f] = file_counts.get(f, 0) + 1

    top_files = sorted(file_counts.keys(), key=lambda f: file_counts[f], reverse=True)

    save_scan_summary(
        total_found=queued_count,
        by_tier=by_tier,
        by_category=by_category,
        files_scanned=len(file_counts),
        top_files=top_files,
    )
