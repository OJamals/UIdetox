"""Scan command -- unified static + subjective analysis in a single pass.

Implements the desloppify flow: Scan Codebase -> generate score -> both
Mechanical Issues (static analyzer) AND Subjective Analysis (LLM review)
happen together, with mechanical informing subjective.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from uidetox.analyzer import analyze_directory, RULES
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import (
    add_issue, ensure_uidetox_dir, get_project_root, load_config, load_state,
    save_config, increment_scans,
)
from uidetox.tooling import detect_all
from uidetox.history import save_run_snapshot
from uidetox.memory import save_scan_summary, save_session, log_progress
from uidetox.utils import compute_design_score


# Categories auto-covered by static analyzer, mapped to rule IDs
_AUTO_CATEGORIES = {
    "typography": {"TYPOGRAPHY_SLOP", "HARDCODED_PX_FONT_SLOP", "TIGHT_LINE_HEIGHT_SLOP", "ALL_CAPS_HEADER_SLOP", "FONT_WEIGHT_EXTREMES_SLOP", "TITLE_CASE_HEADER_SLOP", "GENERIC_FONT_FAMILY_SLOP", "TEXT_TRANSFORM_UPPERCASE_SLOP", "FONT_WEIGHT_TOO_LIGHT_SLOP", "FONT_SIZE_ZERO_SLOP"},
    "color": {"COLOR_GRADIENT_SLOP", "COLOR_BLACK_SLOP", "CSS_GRADIENT_SLOP", "CSS_PURE_BLACK_SLOP", "RAW_COLOR_SLOP", "DUPLICATE_COLOR_LITERAL", "TAILWIND_V4_GRADIENT_SLOP", "GRADIENT_BORDER_SLOP", "GRAY_ON_COLOR_SLOP", "HSL_COLOR_TOKEN_SLOP", "PURE_GRAY_NEUTRAL_SLOP", "ALPHA_COLOR_ABUSE_SLOP", "PURE_WHITE_BACKGROUND_SLOP", "PURE_BLACK_TEXT_SLOP"},
    "layout": {"LAYOUT_MATH_SLOP", "CENTER_BIAS_SLOP", "CARD_NESTING_SLOP", "OVERPADDED_LAYOUT_SLOP", "VIEWPORT_HEIGHT_SLOP", "LAZY_FLEX_CENTER_SLOP", "SPACING_REPETITION_SLOP", "HARDCODED_BREAKPOINT_SLOP", "CENTERED_PARAGRAPH_SLOP", "THREE_EQUAL_COLUMN_SLOP", "HEIGHT_100VH_SLOP", "ASPECT_RATIO_HACK_SLOP", "FLEXBOX_PERCENTAGE_MATH_SLOP", "CSS_OVERFLOW_HIDDEN_BODY_SLOP", "ABSOLUTE_FONT_SIZE_BODY_SLOP", "BACKGROUND_ATTACHMENT_FIXED_SLOP", "RESIZE_NONE_SLOP", "SVG_WITHOUT_VIEWBOX_SLOP", "STICKY_WITHOUT_TOP_SLOP"},
    "motion": {"BOUNCE_ANIMATION_SLOP", "MISSING_TRANSITION_SLOP", "REDUCED_MOTION_MISSING_SLOP", "SCROLL_SMOOTH_NO_MOTION_SLOP", "CSS_SCROLL_BEHAVIOR_SLOP", "WILL_CHANGE_ABUSE_SLOP", "HEIGHT_ANIMATION_SLOP", "TRANSITION_ALL_SLOP", "EASE_DEFAULT_SLOP", "SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP"},
    "materiality": {"GLASSMORPHISM_SLOP", "SHADOW_SLOP", "MATERIALITY_RADIUS_SLOP", "NEON_GLOW_SLOP", "OPACITY_ABUSE_SLOP", "GRADIENT_TEXT_SLOP", "GRADIENT_TEXT_CSS_SLOP", "SOLID_DIVIDER_SLOP", "OVERSIZED_BORDER_RADIUS_SLOP", "OUTER_GLOW_SLOP"},
    "states": {"MISSING_HOVER_STATES", "MISSING_FOCUS_SLOP", "MISSING_DARK_MODE", "DISABLED_NO_CURSOR_SLOP", "OUTLINE_NONE_SLOP", "FOCUS_OUTLINE_REMOVED_SLOP", "EMPTY_ARIA_LABEL_SLOP"},
    "content": {"GENERIC_COPY_SLOP", "AI_COPY_CLICHE_SLOP", "LOREM_IPSUM_SLOP", "GENERIC_NAME_SLOP", "EMOJI_HEAVY_SLOP", "EXCLAMATION_UX_SLOP", "OOPS_ERROR_SLOP", "STAR_RATING_SLOP", "FAKE_METRIC_SLOP", "EMOJI_BULLET_LIST_SLOP", "TESTIMONIAL_GRID_SLOP", "PRICING_TABLE_SLOP", "ROUND_NUMBER_SLOP", "UNSPLASH_URL_SLOP", "BROKEN_IMAGE_SLOP", "SAME_DATE_REPEAT_SLOP", "HARDCODED_COPYRIGHT_YEAR_SLOP", "VAGUE_BUTTON_LABEL_SLOP", "GENERIC_LOADING_TEXT_SLOP"},
    "code quality": {"DIV_SOUP_SLOP", "HARDCODED_ZINDEX_SLOP", "INLINE_STYLE_SLOP", "IMPORTANT_ABUSE_SLOP", "NESTED_TERNARY_SLOP", "MAGIC_NUMBER_SLOP", "ANY_TYPE_SLOP", "TS_IGNORE_SLOP", "DISABLED_LINT_RULE", "HARDCODED_COLOR_STYLE_SLOP", "TAILWIND_FONT_CONFLICT_SLOP", "TAILWIND_WEIGHT_CONFLICT_SLOP", "TAILWIND_DISPLAY_CONFLICT_SLOP", "NO_SELECT_CONTENT_SLOP", "UGLY_SCROLLBAR_SLOP", "ARBITRARY_PX_VALUE_SLOP", "VERBOSE_HANDLER_NAME_SLOP", "MISSING_TABULAR_NUMS_SLOP", "VALUE_NAMED_TOKEN_SLOP", "WINDOW_CONFIRM_SLOP", "DIALOG_ROLE_ON_DIV_SLOP", "SRCSET_MISSING_SLOP", "EMPTY_CATCH_SLOP", "TYPE_ASSERTION_ABUSE_SLOP", "ASYNC_USEEFFECT_SLOP", "HARDCODED_DEV_URL_SLOP", "REDUNDANT_BOOL_COMPARE_SLOP", "ALERT_USAGE_SLOP", "USE_INDEX_AS_KEY_SLOP", "STYLE_TAG_IN_JSX_SLOP", "FLOAT_LAYOUT_SLOP", "BUTTON_TYPE_MISSING_SLOP", "CATCH_CONSOLE_ONLY_SLOP", "HARDCODED_TIMEOUT_SLOP", "CSS_EMPTY_RULE_SLOP", "CSS_IMPORTANT_ANIMATION_SLOP", "PROP_SPREADING_SLOP", "CSS_UNIVERSAL_SELECTOR_SLOP", "TAILWIND_APPLY_OVERUSE_SLOP", "NON_NULL_ASSERTION_SLOP", "EVAL_USAGE_SLOP", "EMPTY_INTERFACE_SLOP", "FRAGMENT_SHORTHAND_SLOP", "CSS_OVERFLOW_SCROLL_SLOP", "CSS_VENDOR_PREFIX_SLOP", "BUTTON_TYPE_RESET_SLOP", "GRID_AUTO_FIT_MISSING_SLOP", "STAR_IMPORT_SLOP", "USER_AGENT_SNIFF_SLOP"},
    "components": {"HERO_DASHBOARD_SLOP", "ICONOGRAPHY_SLOP", "PILL_BADGE_SLOP", "MISSING_LOADING_STATE_SLOP", "MISSING_ERROR_STATE_SLOP", "ACCORDION_FAQ_SLOP", "DARK_MODE_TOGGLE_SLOP", "FORM_NO_SUBMIT_SLOP"},
    "accessibility": {"IMG_ALT_MISSING_SLOP", "ICON_ARIA_MISSING_SLOP", "ORPHANED_LABEL_SLOP", "LOW_CONTRAST_SLOP", "MODAL_NO_ARIA_SLOP", "TOUCH_TARGET_SLOP", "AUTOFOCUS_SLOP", "SVG_HARDCODED_FILL_SLOP", "MISSING_META_DESCRIPTION_SLOP", "SKIP_TO_CONTENT_MISSING_SLOP", "FONT_DISPLAY_MISSING_SLOP", "IMG_MISSING_DIMENSIONS_SLOP", "PLACEHOLDER_ONLY_INPUT_SLOP", "USER_SCALABLE_DISABLED_SLOP", "MISSING_FAVICON_SLOP", "INPUT_NO_TYPE_SLOP", "EMPTY_HREF_SLOP", "MISSING_LANG_SLOP", "INPUT_AUTOCOMPLETE_MISSING_SLOP", "ARIA_HIDDEN_INTERACTIVE_SLOP", "FOCUS_VISIBLE_MISSING_SLOP", "TABINDEX_POSITIVE_SLOP", "TABLE_HEADER_NO_SCOPE_SLOP", "MEDIA_AUTOPLAY_SLOP", "AUTOCOMPLETE_OFF_SLOP", "MISSING_ARIA_ROLE_SLOP", "VAGUE_ARIA_LABEL_SLOP", "SELECT_NO_LABEL_SLOP", "IFRAME_NO_TITLE_SLOP", "VIDEO_NO_CAPTIONS_SLOP", "TABINDEX_ZERO_DIV_SLOP", "ICON_ONLY_BUTTON_SLOP"},
    "security": {"ANCHOR_TARGET_BLANK_SLOP", "DANGEROUS_HTML_SLOP", "HARDCODED_SECRET_SLOP", "DOCUMENT_WRITE_SLOP", "INNER_HTML_ASSIGN_SLOP", "LOCALSTORAGE_SENSITIVE_SLOP", "OPEN_REDIRECT_SLOP", "POSTMESSAGE_ORIGIN_MISSING_SLOP"},
    "ssr": {"LOCALSTORAGE_SSR_SLOP", "WINDOW_OBJECT_SSR_SLOP", "USE_CLIENT_DIRECTIVE_SLOP", "NAVIGATOR_SSR_SLOP", "PROCESS_BROWSER_DEPRECATED_SLOP", "DOCUMENT_COOKIE_SSR_SLOP"},
    "react": {"MISSING_KEY_PROP_SLOP", "USEEFFECT_EMPTY_DEPS_SLOP", "FRAMER_NO_REDUCED_MOTION_SLOP", "NEXT_IMAGE_RAW_SLOP", "ASYNC_USEEFFECT_SLOP", "DEPRECATED_FINDDOMNODE_SLOP", "DEPRECATED_CLASS_COMPONENT_SLOP", "LAZY_WITHOUT_SUSPENSE_SLOP", "NO_PASSIVE_SCROLL_LISTENER_SLOP", "CONTEXT_VALUE_INLINE_SLOP", "USE_STATE_INIT_SLOP"},
    "duplication": {"DUPLICATE_TAILWIND_BLOCK", "DUPLICATE_COLOR_LITERAL", "COPY_PASTE_COMPONENT", "DUPLICATE_HANDLER", "REPEATED_MEDIA_QUERY", "DUPLICATE_IMPORT_SLOP"},
    "dead code": {"COMMENTED_OUT_CODE", "UNUSED_IMPORT", "UNREACHABLE_CODE", "EMPTY_HANDLER", "DEAD_CSS_CLASS", "UNUSED_STATE", "DEPRECATED_LIFECYCLE", "CONSOLE_LOG_SLOP", "TODO_FIXME_SLOP", "DEBUGGER_STATEMENT_SLOP", "PROP_TYPES_IN_TS_SLOP"},
}

# Categories that ALWAYS need manual agent audit (not automatable via regex)
_MANUAL_CATEGORIES = {
    "responsive": "Mobile collapse, container queries, fluid typography",
    "forms & inputs": "Label placement, validation, error messaging, input states",
    "strategic omissions": "404 page, legal links, back navigation, favicon",
    "architecture": "Component boundaries, separation of concerns, data flow patterns",
    "elegance": "Visual rhythm, spatial harmony, intentional asymmetry, craft details",
    "a11y (deep)": "Skip-to-content, live regions, complex ARIA patterns, focus traps",
}


def run(args: argparse.Namespace):
    ensure_uidetox_dir()
    project_root = get_project_root()

    # Validate that the path exists and is a directory before doing anything
    scan_path_arg = getattr(args, "path", ".")
    scan_path = str(project_root) if scan_path_arg in (None, "", ".") else scan_path_arg
    if not os.path.isdir(scan_path):
        print(f"Error: scan path '{scan_path}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)
    target = config.get("target_score", 95)

    # Auto-detect tooling if not already configured
    if not config.get("tooling"):
        profile = detect_all(scan_path)
        config["tooling"] = profile.to_dict()
        save_config(config)

    tooling = config.get("tooling", {})

    print("+" + "=" * 58 + "+")
    print("| SCAN CODEBASE -- Static Analysis + Subjective Review     |")
    print("+" + "=" * 58 + "+")
    print(f"  Path  : {scan_path}")
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
    output_format = getattr(args, "output", "table")
    since_sha = getattr(args, "since", None)

    # Incremental mode: only scan files changed since a git SHA
    since_files: list[str] | None = None
    since_root: str = os.path.abspath(scan_path)  # fallback; overridden with git root below
    if since_sha:
        try:
            # git diff --name-only outputs paths relative to the repo root, not scan_path
            root_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, cwd=scan_path, timeout=10,
            )
            if root_result.returncode == 0:
                since_root = root_result.stdout.strip()
            result = subprocess.run(
                ["git", "diff", "--name-only", since_sha],
                capture_output=True, text=True, cwd=scan_path, timeout=10,
            )
            if result.returncode == 0:
                since_files = [
                    line.strip() for line in result.stdout.splitlines()
                    if line.strip()
                ]
                if output_format == "table":
                    print(f"  Incremental: scanning {len(since_files)} file(s) changed since {since_sha}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            if output_format == "table":
                print(f"  Warning: could not run git diff for --since={since_sha}, scanning all files")

    print(f"  Running {len(RULES)}-rule deterministic anti-slop analyzer...")
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    slop_issues = analyze_directory(
        scan_path,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
        design_variance=variance,
    )

    # Filter to only changed files in incremental mode
    if since_files is not None:
        since_abs = {os.path.abspath(os.path.join(since_root, f)) for f in since_files}
        slop_issues = [i for i in slop_issues if os.path.abspath(i.get("file", "")) in since_abs]

    # JSON output: print all issues as JSON and exit early
    if output_format == "json":
        print(json.dumps(slop_issues, indent=2))
        return

    # GitHub Actions annotation output
    if output_format == "github":
        for issue in slop_issues:
            line = issue.get("line", 1)
            col = issue.get("column", 1)
            filepath = issue.get("file", "")
            msg = issue.get("issue", "").replace("\n", " ")
            tier = issue.get("tier", "T2")
            level = "error" if tier in ("T3", "T4") else "warning"
            print(f"::{level} file={filepath},line={line},col={col}::{msg}")
        return

    queued_count = 0
    triggered_rules: set[str] = set()
    for issue in slop_issues:
        if not _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            issue_id = f"SCAN-{str(uuid.uuid4()).split('-')[0][:6].upper()}"
            new_issue = {
                "id": issue_id,
                "file": issue['file'],
                "tier": issue["tier"],
                "issue": issue["issue"],
                "command": issue["command"]
            }
            for key in ("line", "column", "snippet"):
                if key in issue:
                    new_issue[key] = issue[key]
            if add_issue(new_issue):
                queued_count += 1
            if rule_id := issue.get("id"):
                triggered_rules.add(rule_id)

    if queued_count > 0:
        print(f"  -> Queued {queued_count} mechanical anti-pattern issues.")
    else:
        print(f"  -> No mechanical anti-patterns detected.")

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
    _save_scan_to_memory(slop_issues, queued_count, triggered_rules, scan_path)
    save_session(phase="scan_complete", last_command="scan",
                 context=f"Found {queued_count} issues in {scan_path}")
    log_progress("scan", f"Scanned {scan_path}: {queued_count} issues queued")

    # Compute current score and show target check
    state = load_state()
    scores = compute_design_score(state)
    score = scores["blended_score"]
    queue_size = len(state.get("issues", []))

    print("=" * 58)
    print(" TARGET SCORE CHECK")
    print("=" * 58)
    filled = score // 5
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
        cat = _infer_category(desc)
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


def _infer_category(desc: str) -> str:
    """Infer issue category from description text."""
    category_keywords = {
        "typography": ["font", "typography", "inter", "type scale", "line-height", "kerning", "letter-spacing", "px font"],
        "color": ["color", "gradient", "palette", "contrast", "dark mode", "purple", "black", "hex color"],
        "layout": ["layout", "grid", "spacing", "padding", "margin", "dashboard", "card", "center", "flex center", "viewport"],
        "motion": ["animation", "bounce", "pulse", "spin", "transition", "motion"],
        "materiality": ["shadow", "glassmorphism", "radius", "border", "backdrop", "blur", "glow", "opacity"],
        "states": ["loading", "error", "empty", "skeleton", "disabled", "hover", "focus"],
        "content": ["copy", "lorem", "generic", "placeholder", "cliche", "john doe", "acme", "emoji", "oops", "exclamation"],
        "code quality": ["div soup", "semantic", "z-index", "inline style", "!important", "ternary", "magic number", "any type", "ts-ignore", "eslint-disable"],
        "duplication": ["duplicate", "repeated", "copy-paste", "identical", "same hex"],
        "dead code": ["commented-out", "unused import", "unreachable", "empty handler", "empty css", "unused state", "deprecated", "console", "todo", "fixme"],
    }
    for cat, keywords in category_keywords.items():
        if any(kw in desc for kw in keywords):
            return cat
    return "other"
