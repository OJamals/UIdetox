"""Next command: pops the highest-priority issue with full context."""

import argparse
import sys
from pathlib import Path
from uidetox.state import load_state, load_config
from uidetox.skills import recommend_skills_for_issues, format_skill_recommendations


def _get_skill_path() -> Path | None:
    """Locate SKILL.md — check platform-specific directories, then bundled data."""
    cwd = Path.cwd()
    # 1. Project root (installed via update-skill for copilot)
    if (cwd / "SKILL.md").exists():
        return cwd / "SKILL.md"
    # 2. Platform-specific skill directories (update-skill installs here)
    for platform in (".claude", ".cursor", ".gemini", ".windsurf", ".github"):
        skill = cwd / platform / "skills" / "uidetox" / "SKILL.md"
        if skill.exists():
            return skill
    # 3. Legacy .agents directory
    agents_skill = cwd / ".agents" / "skills" / "uidetox" / "SKILL.md"
    if agents_skill.exists():
        return agents_skill
    # 4. Bundled inside pip package
    pkg_data = Path(__file__).resolve().parent.parent / "data" / "SKILL.md"
    if pkg_data.exists():
        return pkg_data
    return None


# SKILL.md context fragments keyed by issue pattern keywords.
# Each entry: (context_snippet, reference_file_path | None)
SKILL_CONTEXT: dict[str, tuple[str, str | None]] = {
    # Typography
    "typography": (
        "TYPOGRAPHY RULES: Never use Inter, Roboto, or system-ui as primary. Use Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale (display, body, caption). Use Medium (500) and SemiBold (600) — not just Regular and Bold. Negative tracking for large headers, positive for small caps.",
        "reference/typography.md",
    ),
    "font": (
        "TYPOGRAPHY RULES: Never use Inter, Roboto, or system-ui as primary. Use Geist, Satoshi, Outfit, or Space Grotesk. Establish a 3-level type scale (display, body, caption). Use Medium (500) and SemiBold (600) — not just Regular and Bold.",
        "reference/typography.md",
    ),
    # Color
    "gradient": (
        "COLOR RULES: Never use purple-blue gradients. Use a single high-contrast accent color on neutral base. Max 1 accent, saturation < 80%. Tint all neutrals toward brand hue. Colors should feel intentional, not generated.",
        "reference/color-and-contrast.md",
    ),
    "palette": (
        "COLOR RULES: Use existing project colors first, then get inspired from reference/color-palettes.md. Never invent random color combinations. Max 1 accent color.",
        "reference/color-palettes.md",
    ),
    "black": (
        "COLOR RULES: Never use pure black (#000000). Use tinted dark neutrals (zinc-950, slate-900, #0f0f0f, #0d1117). Pure black feels digital, not designed.",
        "reference/color-and-contrast.md",
    ),
    "contrast": (
        "CONTRAST RULES: Gray text on colored backgrounds is BANNED — use a shade of the background color instead. Check WCAG AA contrast ratios (4.5:1 for text, 3:1 for large text).",
        "reference/color-and-contrast.md",
    ),
    # Materiality
    "icon": (
        "COMPONENT RULES: Avoid default lucide-react icon set. Use Phosphor Icons, Heroicons, or custom SVGs. Icons should match brand personality, not generic defaults.",
        None,
    ),
    "lucide": (
        "COMPONENT RULES: Avoid default lucide-react. Use Phosphor Icons, Heroicons, or custom SVGs. Icons should match brand personality.",
        None,
    ),
    "radius": (
        "MATERIALITY RULES: Avoid oversized radii on everything (2xl/3xl on cards, buttons, panels simultaneously). Use rounded-lg or rounded-xl max for cards. 8-10px radius max for buttons. Consistent radius = professional.",
        None,
    ),
    "shadow": (
        "MATERIALITY RULES: Avoid oversized shadows (2xl/3xl/custom). Use shadow-sm or shadow-md. Prefer border-based elevation over drop shadows. Tint shadows to the background hue.",
        None,
    ),
    "glow": (
        "MATERIALITY RULES: Neon glows, outer glows, and auto-glows are BANNED. Use inner borders (border-white/10) or tinted subtle shadows instead.",
        None,
    ),
    "glassmorphism": (
        "MATERIALITY RULES: Avoid glassmorphism (backdrop-blur + transparency) as default visual language. Use solid surfaces with subtle borders or shadow hierarchy. Reserve transparency for overlays and modals only.",
        None,
    ),
    "opacity": (
        "MATERIALITY RULES: No excessive layered transparency (stacking opacity-50 or bg-white/10). Use solid surface colors; reserve transparency for overlays and modals only.",
        None,
    ),
    # Layout
    "grid": (
        "LAYOUT RULES: Avoid symmetric 3-column grids. Use asymmetric layouts, varied column widths, or masonry. Use CSS Grid for reliable structures — never complex flexbox percentage math. Always use max-width (1200-1440px) with auto margins.",
        "reference/spatial-design.md",
    ),
    "column": (
        "LAYOUT RULES: Avoid symmetric 3-column grids. Use asymmetric layouts, varied column widths, or masonry. Break the predictable card-grid pattern.",
        "reference/spatial-design.md",
    ),
    "center": (
        "LAYOUT RULES: When DESIGN_VARIANCE > 4, centered hero sections are BANNED. Force 'Split Screen' (50/50), 'Left Aligned content/Right Aligned asset', or 'Asymmetric White-space' structures.",
        "reference/spatial-design.md",
    ),
    "card": (
        "CARD RULES: Don't wrap everything in cards. Don't nest cards inside cards. Use cards ONLY when elevation communicates hierarchy. For dense data, use border-top, divide-y, or negative space instead.",
        "reference/spatial-design.md",
    ),
    "dashboard": (
        "LAYOUT RULES: Avoid hero metric dashboards (big number, small label, gradient accent). Weave data into narrative flow. Use contextual inline metrics over isolated stat cards.",
        "reference/spatial-design.md",
    ),
    "spacing": (
        "SPACING RULES: Avoid uniform spacing (all p-4). Vary spacing scale (p-3, p-5, p-6) to create visual rhythm and hierarchy. Use 4pt base system (4, 8, 12, 16, 24, 32, 48, 64, 96px). Name tokens semantically.",
        "reference/spatial-design.md",
    ),
    "padding": (
        "SPACING RULES: Avoid overpadding (excessive p-8, p-10 everywhere). Reduce and vary. Standard section padding is 20-30px. Create rhythm with tight groupings and generous separations.",
        "reference/spatial-design.md",
    ),
    "viewport": (
        "VIEWPORT RULES: Never use h-screen for full-height sections — broken on iOS Safari. Always use min-h-[100dvh].",
        None,
    ),
    "z-index": (
        "Z-INDEX RULES: Create semantic z-index scales (dropdown=10, sticky=20, modal-backdrop=30, modal=40, toast=50, tooltip=60). Never use arbitrary z-index: 9999.",
        None,
    ),
    # Motion
    "bounce": (
        "MOTION RULES: Never use bounce or elastic easing — they feel dated and tacky. Use exponential easing (ease-out-quart/quint/expo) for natural deceleration. Animate only transform and opacity.",
        "reference/motion-design.md",
    ),
    "animation": (
        "MOTION RULES: Never use animate-bounce/pulse/spin. Use CSS transitions (150-300ms ease) or spring physics. Respect prefers-reduced-motion. Timing: 100-150ms for button press, 200-300ms for hover/menu, 300-500ms for accordion/modal.",
        "reference/motion-design.md",
    ),
    "transition": (
        "MOTION TIMING: Button press 100-150ms, hover/menus 200-300ms, layout changes 300-500ms, page entrance 500-800ms. Use ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1).",
        "reference/motion-design.md",
    ),
    # States
    "dark": (
        "THEMING RULES: Every light surface (bg-white, bg-gray-100) MUST have a dark: variant. Use dark:bg-zinc-900 or dark:bg-slate-900. Never use dark mode with glowing accents as substitute for design.",
        "reference/color-and-contrast.md",
    ),
    "hover": (
        "INTERACTION RULES: Every interactive element needs hover, focus, and active states. Hover: subtle scale, color shift, or shadow change. Active: -translate-y-[1px] or scale-[0.98]. Focus: visible keyboard focus ring. Use transition-colors duration-150.",
        "reference/interaction-design.md",
    ),
    "htmlfor": (
        "ACCESSIBILITY RULES: All <label> elements must have an 'htmlFor' attribute linking to the target input ID. Unlinked labels break screen readers.",
        "reference/interaction-design.md",
    ),
    # Micro-polish
    "scrollbar": (
        "POLISH RULES: Native scrollbars are ugly. Hide them entirely using scrollbar-hide or use a minimal custom-styled track/thumb.",
        "reference/interaction-design.md",
    ),
    "border": (
        "MATERIALITY RULES: Never use solid opaque borders (border-gray-200) for dividers. Use opacity (border-gray-200/50, border-white/10) to blend subtly into the background.",
        "reference/color-and-contrast.md",
    ),
    "line-height": (
        "TYPOGRAPHY RULES: Body text (text-sm/text-base) must use open leading (leading-relaxed/leading-normal). Tight leading is for large display headers only.",
        "reference/typography.md",
    ),
    "px": (
        "TYPOGRAPHY RULES: Never hardcode px for font sizes. Always use responsive rem units or Tailwind scale (text-sm, text-lg) for user accessibility scaling.",
        "reference/typography.md",
    ),
    "flex center": (
        "LAYOUT RULES: 'flex justify-center items-center' is verbose. Use 'grid place-items-center' for simple centering blocks.",
        "reference/spatial-design.md",
    ),
    "focus": (
        "ACCESSIBILITY RULES: Every interactive element MUST have visible focus indicators. Missing focus states = accessibility failure. Use focus:ring-2 focus:ring-offset-2 or custom focus:outline patterns.",
        "reference/interaction-design.md",
    ),
    "loading": (
        "STATE RULES: Every data-dependent component needs loading, error, and empty states. Use skeleton loaders matching layout sizes — never generic circular spinners. Missing states = unfinished UI.",
        "reference/interaction-design.md",
    ),
    "error": (
        "STATE RULES: Show actionable error messages. Backend validation errors → inline field errors, not generic toasts. Network errors → retry-capable states. Auth errors → redirect to login. Never 'Oops!' or 'Something went wrong'.",
        "reference/interaction-design.md",
    ),
    "empty": (
        "STATE RULES: Empty states are design opportunities, not afterthoughts. Use composed states indicating how to populate data. Include illustration, heading, description, and CTA.",
        "reference/interaction-design.md",
    ),
    # Content
    "copy": (
        "UX WRITING RULES: Never use generic startup copy ('Revolutionize', 'Seamless', 'Unleash', 'Elevate'). Write specific, benefit-driven, human-sounding text. No exclamation marks in success messages.",
        "reference/ux-writing.md",
    ),
    "lorem": (
        "CONTENT RULES: No Lorem Ipsum — write real draft copy. No generic names (John Doe, Jane Smith). No round numbers (99.99%, 50%). Use organic data (47.2%, $1,287.34).",
        "reference/ux-writing.md",
    ),
    "placeholder": (
        "CONTENT RULES: No broken Unsplash links — use picsum.photos/seed/{name}/800/600. No SVG egg avatars. No identical blog post dates. Use diverse, creative, realistic placeholder content.",
        "reference/ux-writing.md",
    ),
    "generic": (
        "CONTENT RULES: No 'Acme Corp', 'SmartFlow', 'NexusAI'. Invent premium, contextual brand names. No 'John Doe', 'Jane Smith' — use diverse, realistic full names.",
        "reference/ux-writing.md",
    ),
    # Code quality
    "div": (
        "SEMANTIC HTML: Replace div soup with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>. No inline styles mixed with classes. No hardcoded pixel widths.",
        None,
    ),
    "semantic": (
        "SEMANTIC HTML: Use appropriate HTML5 semantic elements. A single <h1> per page with proper heading hierarchy. Include skip-to-content link for keyboard users.",
        None,
    ),
    "any": (
        "TYPE SAFETY: Replace `any` with proper TypeScript types, `unknown`, or generic parameters. The `any` type defeats the entire purpose of TypeScript. Use discriminated unions for variant types.",
        None,
    ),
    "ts-ignore": (
        "TYPE SAFETY: Fix the underlying type error instead of suppressing with @ts-ignore. Use @ts-expect-error only as last resort, always with an explanation comment.",
        None,
    ),
    "eslint": (
        "CODE QUALITY: Fix the underlying lint issue instead of suppressing with eslint-disable. If a rule is truly wrong for your project, disable it in config — not inline.",
        None,
    ),
    "ternary": (
        "READABILITY: Extract nested ternaries into named variables, early returns, or switch/if blocks. Nested ternaries in JSX are unreadable. One level of ternary max in render.",
        None,
    ),
    "inline style": (
        "CODE QUALITY: Extract inline style objects (40+ chars) to Tailwind classes, CSS modules, styled-components, or cva() variants. Inline styles bypass the design system.",
        None,
    ),
    "!important": (
        "CSS QUALITY: Fix CSS specificity instead of using !important. Use CSS layers (@layer), lower-specificity selectors, or BEM naming to avoid specificity wars.",
        None,
    ),
    # Duplication
    "duplicate": (
        "DRY PRINCIPLE: Extract repeated code into shared components, utility functions, or CSS custom properties. If the same className, handler, or markup appears twice, it should be a component.",
        None,
    ),
    "copy-paste": (
        "COMPONENT EXTRACTION: Copy-pasted markup blocks should become reusable components with props for variation. Use composition, not duplication.",
        None,
    ),
    "repeated": (
        "DRY PRINCIPLE: Merge duplicate media queries into one block. Extract repeated color literals to CSS variables. Deduplicate identical event handlers into named functions.",
        None,
    ),
    # Dead code
    "commented": (
        "DEAD CODE: Delete commented-out code immediately. Git preserves history. Commented code rots, confuses readers, and signals unfinished work.",
        None,
    ),
    "unused": (
        "DEAD CODE: Remove unused imports, variables, and state declarations. Use your linter's auto-fix (`uidetox check --fix`) to clean automatically.",
        None,
    ),
    "unreachable": (
        "DEAD CODE: Remove code after return/throw/break statements. Unreachable code is never executed and confuses maintainers.",
        None,
    ),
    "deprecated": (
        "MODERNIZATION: Migrate deprecated React lifecycle methods to hooks. Use useEffect for side effects, useMemo for computation, useCallback for handlers.",
        None,
    ),
    "console": (
        "PRODUCTION CODE: Remove all console.log/warn/error statements. Use a proper logging utility or conditional debug logging that's stripped in production.",
        None,
    ),
    # Responsive
    "responsive": (
        "RESPONSIVE RULES: Use container queries for components, viewport queries for page layouts. Use repeat(auto-fit, minmax(280px, 1fr)) for responsive grids without breakpoints. Ensure mobile layout collapse for high-variance designs.",
        "reference/responsive-design.md",
    ),
    "mobile": (
        "RESPONSIVE RULES: Build mobile-first. Ensure touch targets are 44px minimum. Use fluid typography and responsive spacing.",
        "reference/responsive-design.md",
    ),
    # Accessibility
    "accessibility": (
        "A11Y RULES: Every interactive element needs visible focus indicators. Add ARIA labels to icon-only buttons. Ensure WCAG AA contrast ratios. Include skip-to-content link. Respect prefers-reduced-motion.",
        None,
    ),
    "a11y": (
        "A11Y RULES: Visible focus indicators on all interactive elements. ARIA labels on icon-only buttons. WCAG AA contrast (4.5:1 text, 3:1 large text). Skip-to-content link.",
        None,
    ),
    # Forms
    "form": (
        "FORM RULES: Label MUST sit above input. Helper text optional. Error text below input. Standard gap between input blocks. Explicit button hierarchy (primary, secondary, ghost, text link).",
        "reference/interaction-design.md",
    ),
    "input": (
        "INPUT RULES: Solid borders, simple focus ring. No animated underlines or morphing shapes. Client-side validation must reflect database constraints. Error state must be inline, not toast.",
        "reference/interaction-design.md",
    ),
}


def _get_relevant_context(batch: list) -> list[tuple[str, str | None]]:
    """Extract relevant SKILL.md fragments based on issue descriptions.

    Returns list of (context_snippet, reference_file_path) tuples.
    """
    seen_snippets: set[str] = set()
    contexts: list[tuple[str, str | None]] = []
    for issue in batch:
        desc = (issue.get("issue", "") + " " + issue.get("command", "")).lower()
        for keyword, (context, ref_file) in SKILL_CONTEXT.items():
            if keyword in desc and context not in seen_snippets:
                seen_snippets.add(context)
                contexts.append((context, ref_file))
    return contexts


def run(args: argparse.Namespace):
    state = load_state()
    config = load_config()
    issues = state.get("issues", [])
    resolved_count = len(state.get("resolved", []))

    if not issues:
        print("Queue is empty. No pending issues.")
        print()
        print("[AUTONOMOUS LOOP SIGNAL]")
        print("Queue drained — the loop will now run objective + subjective analysis.")
        print("Run `uidetox loop` NOW.")
        print("DO NOT STOP. DO NOT run individual commands — the loop handles everything.")
        sys.exit(0)  # exit 0 so autopilot chain continues

    # Design dials
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)

    # Sort by tier priority: T1 > T2 > T3 > T4
    tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
    sorted_issues = sorted(issues, key=lambda x: tiers_order.get(x.get("tier", "T4"), 5))

    # Get the file of the highest priority issue
    target_file = sorted_issues[0].get("file")

    # Group issues by directory (component) for coherent batches
    target_dir = str(Path(target_file).parent)
    batch = [i for i in sorted_issues if str(Path(i.get("file", "")).parent) == target_dir][:15]

    # Derive component name
    batch_files = list(set(i.get("file", "") for i in batch))
    component = target_dir.replace("\\", "/").split("/")[-1] if target_dir != "." else "root"

    print("╔═════════════════════════════════════════════╗")
    print(f"║ Next Component: {component} ({len(batch_files)} file(s))")
    print("╚═════════════════════════════════════════════╝")
    print(f"  Directory: {target_dir}")
    print(f"  Batching {len(batch)} issue(s) across {len(batch_files)} file(s):")
    print()

    for idx, iss in enumerate(batch):
        print(f"  [{idx+1}] ID: {iss['id']} | Tier: {iss['tier']}")
        print(f"      Issue  : {iss['issue']}")
        print(f"      Action : {iss.get('command', 'manual fix')}")
        print()

    # Inject design dials — critical for calibrating fixes
    print(f"  ━━━ DESIGN DIALS (calibrate your fixes to these values) ━━━")
    print(f"  DESIGN_VARIANCE  = {variance}  ", end="")
    if variance <= 3:
        print("(clean, centered, standard grids)")
    elif variance <= 7:
        print("(varied sizes, offset margins, overlapping elements)")
    else:
        print("(asymmetric, masonry, massive whitespace zones)")
    print(f"  MOTION_INTENSITY = {intensity}  ", end="")
    if intensity <= 3:
        print("(CSS hover/active only)")
    elif intensity <= 7:
        print("(fade-ins, transitions, staggered entry)")
    else:
        print("(scroll-triggered, spring physics, magnetic effects)")
    print(f"  VISUAL_DENSITY   = {density}  ", end="")
    if density <= 3:
        print("(art gallery, spacious, luxury)")
    elif density <= 7:
        print("(standard web app spacing)")
    else:
        print("(cockpit mode, dense data, monospace numbers)")
    print()

    # Inject relevant SKILL.md context with reference file pointers
    contexts = _get_relevant_context(batch)
    if contexts:
        print("  ━━━ SKILL.md DESIGN RULES (relevant to this batch) ━━━")
        seen_refs: set[str] = set()
        for ctx, ref_file in contexts:
            print(f"  > {ctx}")
        print()

        # Collect unique reference file pointers
        ref_files: list[str] = []
        for _, ref in contexts:
            if ref and ref not in seen_refs:
                seen_refs.add(ref)
                ref_files.append(ref)
        if ref_files:
            print("  Deep-dive references:")
            for ref in ref_files:
                print(f"    {ref}")
            print()

    # Inject semantic memory context based on current issues
    try:
        from uidetox.subagent import _build_memory_block # type: ignore
        query_text = " ".join([i.get("issue", "") + " " + i.get("command", "") for i in batch])
        memory_block = _build_memory_block(query=query_text)
        if memory_block:
            print("  ━━━ PERSISTENT AGENT MEMORY (semantically matched) ━━━")
            for line in memory_block.split("\n"):
                if line.strip():
                    print(f"  {line}")
            print()
    except Exception:
        pass

    # Point the agent to the full SKILL.md for deeper reference
    skill_path = _get_skill_path()
    if skill_path:
        print(f"  Full design rules: {skill_path}")
        print()

    # ---- Skill recommendations for this batch ----
    skill_recs = recommend_skills_for_issues(batch, config=config, phase="fix", limit=5)
    if skill_recs:
        print("  ━━━ RECOMMENDED SKILLS (invoke before fixing) ━━━")
        print("  These skills match the issues in this batch. Run them on")
        print(f"  the target directory to inject domain-specific rules:")
        print()
        formatted = format_skill_recommendations(
            skill_recs,
            indent="    ",
            show_commands=True,
            target=target_dir,
        )
        if formatted:
            print(formatted)

    remaining = len(issues) - len(batch)
    tiers = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
    for i in issues:
        t = i.get("tier", "T4")
        if t in tiers:
            tiers[t] += 1

    print(f"  Queue : {remaining} remaining after this batch")
    print(f"  Stats : {tiers['T1']}xT1, {tiers['T2']}xT2, {tiers['T3']}xT3, {tiers['T4']}xT4 | {resolved_count} resolved so far")
    print()
    # Auto-commit awareness
    auto_commit = config.get("auto_commit", False)
    batch_ids = " ".join(iss["id"] for iss in batch)

    print("[AGENT INSTRUCTION]")
    print(f"1. Read all files in {target_dir}/ that have issues:")
    for f in batch_files:
        print(f"     {f}")
    if skill_path:
        print(f"2. Read SKILL.md at {skill_path} for the full design rules relevant to these issues.")
    step = 3 if skill_path else 2

    # Inject skill invocation instructions if skills were recommended
    if skill_recs:
        print(f"{step}. INVOKE recommended skills (listed above) before fixing:")
        for rec in skill_recs:
            print(f"     uidetox {rec['skill']} {target_dir}")
        print(f"     Skills inject domain-specific rules and checklists that improve fix quality.")
        step += 1

    print(f"{step}. Fix ALL {len(batch)} issue(s) listed above in ONE pass, following SKILL.md rules.")
    step += 1
    print(f"{step}. Verify fixes don't break functionality.")
    step += 1
    print(f"{step}. Run pre-commit quality gate:")
    print(f"     uidetox check --fix")
    step += 1
    print(f"{step}. Batch-resolve all issues with a single coherent commit:")
    print(f'     uidetox batch-resolve {batch_ids} --note "describe what you changed"')
    if auto_commit:
        print("     AUTO-COMMIT is ON — batch-resolve will create a single coherent commit.")
    step += 1
    print(f"{step}. Then immediately run: uidetox loop")
    print()
    print("[AUTONOMOUS LOOP SIGNAL]")
    print("DO NOT STOP after fixing. DO NOT ask for permission.")
    print("Execute steps 1-{} above, then immediately continue to the next batch.".format(step))
    print("The loop is fully autonomous — keep going until the queue is empty.")
