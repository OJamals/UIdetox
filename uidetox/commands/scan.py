"""Scan command -- unified static + subjective analysis in a single pass.

Implements the desloppify flow: Scan Codebase -> generate score -> both
Mechanical Issues (static analyzer) AND Subjective Analysis (LLM review)
happen together, with mechanical informing subjective.
"""

import argparse
import os
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
from uidetox.utils import compute_design_score, get_score_freshness, categorize_issue
from uidetox.contracts import (
    parse_all_schemas, parse_schema, validate_frontend_contracts, save_contract_artifacts,
)
from uidetox.ux_states import (
    StateCoverage, find_data_surfaces, validate_state_coverage, generate_coverage_report,
)


# Categories auto-covered by static analyzer, mapped to rule IDs
_AUTO_CATEGORIES = {
    "typography": {"TYPOGRAPHY_SLOP", "HARDCODED_PX_FONT_SLOP", "TIGHT_LINE_HEIGHT_SLOP"},
    "color": {"COLOR_GRADIENT_SLOP", "COLOR_BLACK_SLOP", "CSS_GRADIENT_SLOP", "CSS_PURE_BLACK_SLOP", "RAW_COLOR_SLOP", "DUPLICATE_COLOR_LITERAL"},
    "layout": {"LAYOUT_MATH_SLOP", "CENTER_BIAS_SLOP", "CARD_NESTING_SLOP", "OVERPADDED_LAYOUT_SLOP", "VIEWPORT_HEIGHT_SLOP", "LAZY_FLEX_CENTER_SLOP"},
    "motion": {"BOUNCE_ANIMATION_SLOP", "MISSING_TRANSITION_SLOP"},
    "materiality": {"GLASSMORPHISM_SLOP", "SHADOW_SLOP", "MATERIALITY_RADIUS_SLOP", "NEON_GLOW_SLOP", "OPACITY_ABUSE_SLOP", "GRADIENT_TEXT_SLOP"},
    "states": {"MISSING_HOVER_STATES", "MISSING_FOCUS_SLOP", "MISSING_DARK_MODE", "DISABLED_NO_CURSOR_SLOP", "ROUTE_UI_STATE_COVERAGE"},
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


_ROUTE_UI_STATE_RULE_ID = "ROUTE_UI_STATE_COVERAGE"
_REQUIRED_ROUTE_STATES = ("loading", "error", "empty")
_FRONTEND_EXTS = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte"}
_ROUTE_SEGMENTS = {"app", "pages", "routes", "views"}
_ROUTE_FILENAMES = {
    "page.tsx", "page.jsx", "page.ts", "page.js",
    "route.tsx", "route.jsx", "route.ts", "route.js",
    "+page.svelte", "+page.ts", "index.tsx", "index.jsx",
}
_TEST_FILE_MARKERS = (".test.", ".spec.", ".stories.")
_MAX_ROUTE_SCAN_FILES = 250
_MAX_ROUTE_FILE_BYTES = 250_000


def _normalize_contract_artifacts(tooling: dict) -> dict[str, list[str]]:
    raw = tooling.get("contract_artifacts", {})
    if not isinstance(raw, dict):
        raw = {}
    return {
        "schema_files": [v for v in raw.get("schema_files", []) if isinstance(v, str) and v],
        "dto_files": [v for v in raw.get("dto_files", []) if isinstance(v, str) and v],
        "contract_files": [v for v in raw.get("contract_files", []) if isinstance(v, str) and v],
    }


def _collect_contract_validation_issues(
    scan_root: Path,
    tooling: dict,
    ignore_patterns: list[str],
) -> tuple[list[dict], dict]:
    artifacts_config = _normalize_contract_artifacts(tooling)
    schema_paths = artifacts_config.get("schema_files", [])
    parsed_artifacts = []
    parsed_schema_files: list[str] = []

    for rel_path in schema_paths:
        schema_path = Path(rel_path)
        if not schema_path.is_absolute():
            schema_path = scan_root / schema_path
        art = parse_schema(schema_path)
        if not art or not (art.endpoints or art.models):
            continue
        parsed_artifacts.append(art)
        try:
            parsed_schema_files.append(schema_path.resolve().relative_to(scan_root.resolve()).as_posix())
        except ValueError:
            parsed_schema_files.append(schema_path.as_posix())

    if not parsed_artifacts:
        parsed_artifacts = parse_all_schemas(scan_root)
        parsed_schema_files = []
        for art in parsed_artifacts:
            source = art.source_file
            if not source:
                continue
            source_path = Path(source)
            try:
                rel = source_path.resolve().relative_to(scan_root.resolve()).as_posix()
            except ValueError:
                rel = source_path.as_posix()
            parsed_schema_files.append(rel)

    meta = {
        "schema_files": sorted(set(parsed_schema_files)),
        "artifact_count": len(parsed_artifacts),
        "source_types": sorted({a.source for a in parsed_artifacts}),
        "models": sum(len(a.models) for a in parsed_artifacts),
        "endpoints": sum(len(a.endpoints) for a in parsed_artifacts),
        "cache_path": "",
    }
    if not parsed_artifacts:
        return [], meta

    violations = validate_frontend_contracts(scan_root, parsed_artifacts)
    issues: list[dict] = []
    for violation in violations:
        issue = violation.to_issue()
        if _is_suppressed(issue["file"], issue["issue"], ignore_patterns):
            continue
        issue["id"] = f"CONTRACT-{uuid.uuid4().hex[:8].upper()}"
        issues.append(issue)

    cache_path = save_contract_artifacts(scan_root, parsed_artifacts)
    meta["cache_path"] = str(cache_path)
    return issues, meta


def _is_route_like_file(path: Path) -> bool:
    lower = path.as_posix().lower()
    if any(marker in lower for marker in _TEST_FILE_MARKERS):
        return False
    if path.name.lower() in _ROUTE_FILENAMES:
        return True
    return bool({part.lower() for part in path.parts} & _ROUTE_SEGMENTS)


def _iter_route_frontend_files(
    root: Path,
    *,
    exclude_paths: list[str],
    zone_overrides: dict[str, str],
) -> list[Path]:
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "vendor", "__pycache__", ".tox", "coverage", ".turbo", "out"}
    for entry in exclude_paths:
        cleaned = (entry or "").strip().strip("/")
        if not cleaned:
            continue
        skip_dirs.add(Path(cleaned).name or cleaned)

    zone_skip: set[str] = set()
    for file_path, zone in zone_overrides.items():
        if zone not in {"vendor", "generated", "test", "script"}:
            continue
        raw = str(file_path)
        zone_skip.add(raw)
        zone_skip.add(raw.lstrip("./"))

    route_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs and not d.startswith("."))
        for filename in sorted(filenames):
            candidate = Path(dirpath) / filename
            if candidate.suffix.lower() not in _FRONTEND_EXTS:
                continue
            try:
                if candidate.stat().st_size > _MAX_ROUTE_FILE_BYTES:
                    continue
            except OSError:
                continue

            try:
                rel = candidate.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = candidate.as_posix()
            if rel in zone_skip or rel.lstrip("./") in zone_skip:
                continue
            if not _is_route_like_file(Path(rel)):
                continue
            route_files.append(candidate)
            if len(route_files) >= _MAX_ROUTE_SCAN_FILES:
                return route_files
    return route_files


def _missing_required_route_states(coverage: StateCoverage) -> list[str]:
    return [state for state in _REQUIRED_ROUTE_STATES if state in coverage.missing_states]


def _build_route_state_issue(file_path: str, missing: list[str]) -> dict:
    return {
        "file": file_path,
        "tier": "T2",
        "issue": f"Route data-fetch UI state coverage missing: {', '.join(missing)}.",
        "command": (
            "Add route-level state branches before success render: "
            "loading -> skeleton/spinner, error -> retryable error state, empty -> actionable empty state."
        ),
    }


def _collect_route_ui_state_issues(
    path: str,
    *,
    exclude_paths: list[str],
    zone_overrides: dict[str, str],
    ignore_patterns: list[str],
) -> list[dict]:
    scan_root = Path(path).resolve()
    route_files = _iter_route_frontend_files(
        scan_root,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
    )
    if not route_files:
        return []
    surfaces = find_data_surfaces(scan_root, files=route_files)
    if not surfaces:
        return []
    coverages = validate_state_coverage(scan_root, surfaces)
    issues: list[dict] = []
    for coverage in sorted(coverages, key=lambda c: c.surface.file):
        missing = _missing_required_route_states(coverage)
        if not missing:
            continue
        issue = _build_route_state_issue(coverage.surface.file, missing)
        if _is_suppressed(issue["file"], issue["issue"], ignore_patterns):
            continue
        issue["id"] = f"ROUTESTATE-{uuid.uuid4().hex[:8].upper()}"
        issues.append(issue)
    return issues


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

    # Auto-detect tooling if not already configured (or needs contract artifact upgrade)
    tooling_missing = not config.get("tooling")
    tooling_needs_upgrade = bool(config.get("tooling")) and "contract_artifacts" not in config.get("tooling", {})
    if tooling_missing or tooling_needs_upgrade:
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
    contract_artifacts = _normalize_contract_artifacts(tooling)

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
    schema_count = len(contract_artifacts["schema_files"])
    dto_count = len(contract_artifacts["dto_files"])
    contract_count = len(contract_artifacts["contract_files"])
    if schema_count or dto_count or contract_count:
        print(
            "           contract-artifacts="
            f"schemas:{schema_count}, dto:{dto_count}, contracts:{contract_count}"
        )
        for label, files in (
            ("schemas", contract_artifacts["schema_files"]),
            ("dtos", contract_artifacts["dto_files"]),
            ("contracts", contract_artifacts["contract_files"]),
        ):
            if not files:
                continue
            preview = ", ".join(files[:3])
            extra = ""
            if len(files) > 3:
                extra = f", ... (+{len(files) - 3})"
            print(f"             - {label}: {preview}{extra}")
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

    route_state_issues = _collect_route_ui_state_issues(
        args.path,
        exclude_paths=exclude_paths,
        zone_overrides=zone_overrides,
        ignore_patterns=ignore_patterns,
    )
    if route_state_issues:
        triggered_rules.add(_ROUTE_UI_STATE_RULE_ID)

    # Batch-add in two phases to keep reporting clear.
    batch_result = {"added": 0, "updated": 0, "skipped": 0}
    if new_issues:
        batch_result = batch_add_issues(new_issues)

    route_result = {"added": 0, "updated": 0, "skipped": 0}
    if route_state_issues:
        route_result = batch_add_issues(route_state_issues, phase="route_state_validation")

    queued_count = batch_result["added"] + route_result["added"]
    if queued_count > 0:
        print(f"  -> Queued {queued_count} mechanical issue(s).")
    else:
        print("  -> No mechanical anti-patterns detected.")
    if batch_result["updated"] > 0:
        print(f"  -> Refreshed {batch_result['updated']} matching pending issue(s) with sharper guidance/severity.")
    if batch_result["skipped"] > 0:
        print(f"  -> Skipped {batch_result['skipped']} duplicate pending issue(s) already in the queue.")
    if route_state_issues:
        print(f"  -> Route-level state findings: {len(route_state_issues)}")
        if route_result["updated"] > 0:
            print(f"  -> Updated {route_result['updated']} matching route-state issue(s).")
        if route_result["skipped"] > 0:
            print(f"  -> Skipped {route_result['skipped']} duplicate route-state issue(s).")

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
        print("  Run the following GitNexus queries for cross-layer analysis:")
        print("    npx gitnexus query \"API endpoint route handler DTO\"")
        print("    npx gitnexus query \"fetch request mutation query\"")
        print("    npx gitnexus query \"validation constraint required schema\"")
        print("    npx gitnexus query \"error status code exception boundary\"")

    # ===========================================================
    # PART 1b: CONTRACT VALIDATION (OpenAPI/GraphQL/Prisma)
    # ===========================================================
    scan_root = Path(args.path)
    contract_issues, contract_meta = _collect_contract_validation_issues(
        scan_root,
        tooling,
        ignore_patterns,
    )
    if contract_meta["artifact_count"] > 0:
        print()
        print("=" * 58)
        print(" PART 1b: CONTRACT VALIDATION (backend schema → frontend DTO)")
        print("=" * 58)
        source_types = contract_meta["source_types"] or ["unknown"]
        print(f"  Parsed {contract_meta['artifact_count']} schema(s): {', '.join(source_types)}")
        print(f"  Models: {contract_meta['models']}  |  Endpoints: {contract_meta['endpoints']}")
        if contract_meta["schema_files"]:
            preview = ", ".join(contract_meta["schema_files"][:4])
            extra = ""
            if len(contract_meta["schema_files"]) > 4:
                extra = f", ... (+{len(contract_meta['schema_files']) - 4})"
            print(f"  Schema files: {preview}{extra}")

        if contract_issues:
            contract_result = batch_add_issues(contract_issues, phase="contract_validation")
            print(f"  -> Queued {contract_result['added']} contract violation(s).")
            if contract_result["skipped"] > 0:
                print(f"  -> Skipped {contract_result['skipped']} duplicate(s).")
        else:
            print("  -> Frontend DTOs match backend contracts. ✓")

        if contract_meta["cache_path"]:
            print(f"  Contract cache: {contract_meta['cache_path']}")
        print()
    else:
        print()
        print("  No OpenAPI/GraphQL/Prisma schemas found — contract validation skipped.")

    # ===========================================================
    # PART 1c: UX-STATE VALIDATION (loading/error/empty/success)
    # ===========================================================
    ux_issues: list[dict] = []
    surfaces = find_data_surfaces(scan_root)
    if surfaces:
        print()
        print("=" * 58)
        print(" PART 1c: UX-STATE VALIDATION (data surface coverage)")
        print("=" * 58)
        coverages = validate_state_coverage(scan_root, surfaces)
        report = generate_coverage_report(coverages)

        print(f"  Data surfaces found : {report['total_surfaces']}")
        print(f"  Complete coverage   : {report['complete']}")
        print(f"  Incomplete coverage : {report['incomplete']}")
        print(f"  Overall coverage    : {report['coverage_percentage']}%")

        missing = report.get("missing_breakdown", {})
        if any(v > 0 for v in missing.values()):
            print(f"  Missing breakdown   : " + ", ".join(
                f"{k}={v}" for k, v in missing.items() if v > 0
            ))

        for cov in coverages:
            # Route-level surfaces are handled by the dedicated route checker above.
            surface_path = Path(cov.surface.file)
            try:
                rel_surface = surface_path.resolve().relative_to(scan_root.resolve())
            except ValueError:
                rel_surface = surface_path
            if _is_route_like_file(rel_surface):
                continue
            issue_dict = cov.to_issue()
            if issue_dict and not _is_suppressed(issue_dict["file"], issue_dict["issue"], ignore_patterns):
                issue_dict["id"] = f"UXSTATE-{uuid.uuid4().hex[:8].upper()}"
                ux_issues.append(issue_dict)

        if ux_issues:
            ux_result = batch_add_issues(ux_issues, phase="ux_state_validation")
            print(f"  -> Queued {ux_result['added']} UX-state coverage issue(s).")
            if ux_result["skipped"] > 0:
                print(f"  -> Skipped {ux_result['skipped']} duplicate(s).")
        else:
            print("  -> All data surfaces have complete state coverage. ✓")
        print()

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
    print("  ⚠️  SCORE INTEGRITY (enforced automatically):")
    print("    • Your raw score passes through a diminishing-returns curve.")
    print("      Raw 90 → effective ~85.  Raw 95 → effective ~92.  Only 100 → 100.")
    print("    • Pending issues in the queue AUTO-DEDUCT from your effective score.")
    print("    • If ANY issues remain, effective subjective is CAPPED at 85.")
    print("    • If objective < 90, effective subjective is CAPPED at 80.")
    print("    • You CANNOT reach 95+ blended without: empty queue, 100% objective,")
    print("      AND a raw subjective of ~98+.")
    print("    • A Perfection Gate enforces: zero TODO/FIXME, zero console.log,")
    print("      zero AI slop fingerprints, all states present, skip-to-content,")
    print("      favicon, meta tags, custom 404 — run `uidetox review` for full list.")
    print("    • Do NOT inflate — the curve, penalties, and gate WILL expose it.")
    print()

    # ===========================================================
    # SCORE CHECK: Target reached?
    # ===========================================================
    increment_scans()
    save_run_snapshot(trigger="scan")
    _save_scan_to_memory(new_issues, queued_count, triggered_rules, args.path)
    total_new = queued_count + len(contract_issues) + len(ux_issues)
    save_session(phase="scan_complete", last_command="scan",
                 context=f"Detected {detected_count} anti-slop + {len(route_state_issues)} route-state + {len(contract_issues)} contract + {len(ux_issues)} UX-state issues in {args.path}; queued {total_new}")
    log_progress("scan", f"Scanned {args.path}: anti_slop={detected_count}, route_state={len(route_state_issues)}, contract={len(contract_issues)}, ux_state={len(ux_issues)}, queued={total_new}")

    # Compute current score and show target check
    state = load_state()
    scores = compute_design_score(state)
    freshness = get_score_freshness(state)
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

    if score >= target and queue_size == 0 and freshness["target_ready"]:
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
    if score >= target and queue_size == 0 and freshness["target_ready"]:
        print("TARGET REACHED. Run `uidetox finish` NOW.")
    elif queue_size > 0:
        print(f"Scan complete: {queue_size} issues queued. Run `uidetox next` NOW.")
        print("DO NOT STOP. Begin the autonomous fix loop immediately.")
    else:
        print("Scan complete with empty queue, but the score is not fresh enough to finish.")
        print("Complete subjective review above, then `uidetox review --score <N>` followed by `uidetox status`.")
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
