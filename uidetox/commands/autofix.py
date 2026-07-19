"""Autofix command: automatically apply safe T1 fixes."""

import argparse
import subprocess
from pathlib import Path

from uidetox.state import get_project_root, load_state, load_config
from uidetox.utils import tracked_changed_files


# Category classification + specific replacement guidance
# NOTE: order matters — earlier entries win on keyword collision.
# accessibility must precede states (both match "focus").
# code quality must precede typography (both match "font").
_CATEGORIES = {
    "accessibility": {
        "keywords": [
            "htmlfor",
            "aria",
            "alt text",
            "invisible keyboard focus",
            "outline-none",
            "touch target",
            "tabindex",
            "aria-modal",
            "wcag",
            "24×24",
            "role='dialog'",
            "autofocus",
            "screen reader",
            "keyboard accessibility",
            "svg fill",
            "currentcolor",
            "hardcoded fill",
            "skip",
            "skip to content",
            "skip link",
            "meta description",
            "font-display",
            "foit",
            "flash of invisible",
            "img missing",
            "layout shift",
            "cls",
            "placeholder only",
            "label-less",
            "placeholder is not",
            "user-scalable",
            "zoom",
            "pinch zoom",
            "wcag 1.4.4",
            "favicon",
            "missing favicon",
            "link rel icon",
            "no favicon",
            "input type",
            "input without type",
            "mobile keyboard",
            "type attribute",
            "href=#",
            "href=javascript",
            "empty href",
            "anchor as button",
            "lang attribute",
            "html lang",
            "missing lang",
            "wcag 3.1.1",
            "missing autocomplete",
            "autocomplete attribute",
            "autocomplete='off'",
            "disables browser autofill",
            "muted attribute",
            "unmuted autoplay",
            "autoplay",
            "select without aria",
            "select without label",
        ],
        "guidance": "Add htmlFor to labels. Replace outline-none with focus-visible:ring-2. Add aria-label to icon buttons. Ensure 24×24px minimum touch targets. Never use tabIndex > 0. Use fill='currentColor' in SVGs. Add skip-to-content link before nav. Add font-display:swap to @font-face. Add width/height to <img>. Remove user-scalable=no. Add favicon links (icon + apple-touch-icon). Specify type on all <input>. Replace href='#' with <button type='button'>. Add lang='en' to <html>. Add autocomplete tokens to form inputs. Remove autocomplete='off'. Add muted to all autoplay media. Wrap <select> with <label> or add aria-label.",
    },
    "code quality": {
        "keywords": [
            "z-index",
            "div soup",
            "semantic",
            "inline style",
            "!important",
            "any type",
            "ts-ignore",
            "eslint-disable",
            "ternary",
            "magic number",
            "conflicting tailwind",
            "font-size classes",
            "font-weight classes",
            "display classes",
            "select-none",
            "hardcoded breakpoint",
            "arbitrary px",
            "magic pixel",
            "verbose handler",
            "compound handler",
            "handlebutton",
            "handleform",
            "tabular",
            "tabular-nums",
            "numeric columns",
            "value-named token",
            "--font-size-",
            "--spacing-",
            "semantic token",
            "window.confirm",
            "confirm dialog",
            "blocking dialog",
            "role=dialog",
            "native dialog",
            "<dialog>",
            "inert",
            "srcset",
            "missing key prop",
            "key prop",
            ".map() without key",
            "useeffect with empty",
            "empty dependency array",
            "exhaustive-deps",
            "@apply overuse",
            "tailwind apply",
            "@apply",
            "form without submit",
            "form without onsubmit",
            "hardcoded breakpoints",
            "standard breakpoints",
            "conflicts with tailwind",
            "universal selector",
            "matches every element",
            "css universal",
            "prop spreading",
            "unrestricted spread",
            "non-null assertion",
            "empty interface",
            "vendor prefix",
            "overflow: scroll",
            "always shows scrollbars",
            "wildcard import",
            "tree-shaking",
            "star import",
            "import *",
            "eslint disable",
            "user agent",
            "useragent",
            "browser sniffing",
            "feature detection",
        ],
        "guidance": "Create semantic z-index scale. Replace divs with semantic HTML5. Remove conflicting Tailwind class pairs. Fix lint/type suppressions. Use concise handler names. Name CSS tokens semantically (--text-body not --font-size-16). Use native <dialog> with showModal(). Add srcset to all <img>. Replace window.confirm() with undo toast. Always add key prop in .map() callbacks. Add missing dependencies to useEffect. Replace @apply with component utilities (cva/cn). Add onSubmit handler to all forms. Use Tailwind responsive prefixes instead of custom breakpoints. Scope CSS resets instead of using *. Destructure props instead of spreading. Replace ! assertions with optional chaining. Remove manual vendor prefixes. Replace overflow:scroll with overflow:auto.",
    },
    "typography": {
        "keywords": [
            "font",
            "typography",
            "inter",
            "roboto",
            "open sans",
            "lato",
            "montserrat",
            "generic font",
            "invisible default",
            "type scale",
            "line-height",
            "px font",
            "letter-spacing",
            "kerning",
            "all-caps",
            "uppercase",
            "font-weight",
            "mid-range",
            "title case",
            "sentence case",
            "distinctive",
        ],
        "guidance": "Replace generic defaults (Inter/Roboto/Lato) with Instrument Sans, Plus Jakarta Sans, Outfit, Figtree, or Fraunces. Establish a 3-level type scale. Use rem/Tailwind scale instead of px.",
    },
    "color": {
        "keywords": [
            "color",
            "gradient",
            "black",
            "palette",
            "pure black",
            "hex color",
            "named css color",
            "hsl",
            "oklch",
            "perceptual",
            "color token",
            "design token",
            "zero chroma",
            "dead gray",
            "pure gray",
            "rgba",
            "hsla",
            "alpha",
            "transparency",
            "pure white",
            "#ffffff",
            "white background",
            "harsh white",
            "pure black text",
            "#000000",
        ],
        "guidance": "Replace pure black with zinc-950/#0f0f0f. Replace pure white with tinted near-white (oklch(99% 0.01 250)). Replace purple-blue gradients with a single accent on neutral base. Extract repeated hex literals to CSS variables. Replace hsl() tokens with oklch(). Add subtle chroma to neutral tokens. Replace rgba/hsla with explicit surface tokens.",
    },
    "layout": {
        "keywords": [
            "layout",
            "grid",
            "spacing",
            "viewport",
            "h-screen",
            "padding",
            "center",
            "flex center",
            "overpadded",
            "100vh",
            "dvh",
            "ios safari",
            "mobile viewport",
            "aspect ratio",
            "padding-bottom",
            "56.25",
            "aspect-ratio hack",
            "padding hack",
            "33.33%",
            "25%",
            "percentage-based",
            "flex child",
            "percentage math",
            "flex width",
            "scrollbar visible",
            "scrollbar-hide",
            "native scrollbars",
            "hides the scrollbar",
            "body or html element",
            "fixed repeat count",
            "auto-fit",
            "auto-fill",
            "background-attachment",
            "ios repaint",
            "resize: none",
            "resize:none",
            "textarea size",
            "overflow:hidden on body",
            "svg without viewbox",
            "won't scale",
            "viewbox",
            "position: sticky",
            "won't stick",
            "sticky without",
        ],
        "guidance": "Replace h-screen/height:100vh with min-h-[100dvh]. Use asymmetric grids. Vary spacing scale. Use 'grid place-items-center' instead of verbose flex centering. Replace padding-bottom aspect-ratio hacks with aspect-ratio: 16/9. Replace flex+percentage widths with CSS Grid. Add scrollbar-hide to overflow-auto. Replace overflow:hidden on body with modal-open class. Replace repeat(3,1fr) with repeat(auto-fit,minmax(min(300px,100%),1fr)). Remove background-attachment:fixed. Allow textarea resize:vertical.",
    },
    "motion": {
        "keywords": [
            "animation",
            "bounce",
            "pulse",
            "spin",
            "transition",
            "motion-reduce",
            "reduced-motion",
            "prefers-reduced-motion",
            "scroll-smooth",
            "scroll-behavior",
            "will-change",
            "height animation",
            "transition: all",
            "transition-all",
            "ease",
            "ease-in-out",
            "ease default",
            "expo",
            "cubic-bezier",
            "scroll-snap",
            "snap without smooth",
            "framer motion",
            "framer-motion",
            "usereducedmotion",
            "reduced motion check",
        ],
        "guidance": "Replace animate-bounce/pulse/spin with CSS transitions. Always add motion-reduce:transition-none alongside transitions. Wrap scroll-behavior:smooth in prefers-reduced-motion media query. Use cubic-bezier(0.16,1,0.3,1) instead of bare ease. Avoid transition:all — list specific properties. Add scroll-behavior:smooth alongside scroll-snap-type. Import useReducedMotion from framer-motion and gate all animations. Add {passive: true} to scroll/touch/wheel event listeners.",
    },
    "materiality": {
        "keywords": [
            "shadow",
            "glassmorphism",
            "radius",
            "glow",
            "blur",
            "opacity",
            "neon",
            "gradient text",
            "border-radius",
            "rounded",
            "big rounded",
            "oversized radius",
            "outer glow",
            "box-shadow 0 0",
            "background-clip",
            "bg-clip-text",
        ],
        "guidance": "Cap border-radius at 8-12px (rounded-lg). Remove outer glows (box-shadow: 0 0). Remove gradient text headings. Use solid surfaces with directional shadows. Remove glassmorphism.",
    },
    "states": {
        "keywords": [
            "hover",
            "focus",
            "disabled",
            "cursor-not-allowed",
            "missing hover",
            "missing focus",
        ],
        "guidance": "Add hover:, focus:ring, active: states to all interactive elements. Add disabled:cursor-not-allowed disabled:opacity-50 to disabled elements.",
    },
    "security": {
        "keywords": [
            'target="_blank"',
            "target='_blank'",
            "noopener",
            "noreferrer",
            "window.opener",
            "dangerouslysetinnerhtml",
            "inner html",
            "innerhtml",
            "dompurify",
            "sanitize",
            "xss",
            "cross-site scripting",
            "unsafe html",
            "document.write",
            "open redirect",
            "location.href",
            "allowlist",
            "sensitive data",
            "localstorage exposes",
            "postmessage",
            "cross-origin data injection",
            "event.origin",
        ],
        "guidance": "Add rel='noopener noreferrer' to all target='_blank' links. Wrap dangerouslySetInnerHTML with DOMPurify.sanitize(). Never inject unsanitized user content into the DOM. Remove document.write() — replace with DOM manipulation. Validate location.href destinations against an allowlist. Use httpOnly cookies instead of localStorage for auth tokens.",
    },
    "ssr": {
        "keywords": [
            "localstorage",
            "sessionstorage",
            "window object",
            "window.",
            "typeof window",
            "ssr",
            "server-side",
            "server render",
            "nextjs",
            "next.js",
            "use client",
            "client boundary",
            "use client directive",
            "navigator object",
            "ssr environments",
            "process.browser",
            "webpack 4 shim",
            "document.cookie",
            "typeof document",
            "app router",
        ],
        "guidance": "Guard localStorage/sessionStorage with typeof window !== 'undefined'. Move browser API reads inside useEffect or 'use client' components. Add typeof window guard before window.* module-scope access. Use 'use client' directive only in leaf components that require client state. Replace process.browser with typeof window !== 'undefined'.",
    },
    "content": {
        "keywords": [
            "lorem",
            "generic",
            "copy",
            "cliche",
            "placeholder",
            "john doe",
            "acme",
            "emoji",
            "oops",
            "exclamation",
            "unsplash",
            "vanity metric",
            "testimonial",
            "pricing tier",
            "emoji bullet",
            "social proof",
            "round",
            "organic number",
            "picsum",
            "quota",
            "same date",
            "repeated date",
            "copyright year",
            "hardcoded year",
            "vague button",
            "submit",
            "click here",
            "ok button",
            "proceed",
            "loading...",
            "generic loading",
            "loading text",
            "meta description",
            "missing meta",
            "essential for seo",
            "social sharing",
            "seo failure",
            "<meta name",
        ],
        "guidance": "Write real draft copy. Use diverse, realistic names. Replace vanity metrics with real data. Remove emoji bullet lists. Give pricing tiers distinctive names. Use specific button labels (verb+noun). Replace 'Loading...' with contextual copy: 'Saving your draft...', 'Fetching results...'.",
    },
    "components": {
        "keywords": [
            "lucide",
            "icon",
            "pill",
            "badge",
            "dashboard",
            "stat-card",
            "hero",
            "loading state",
            "skeleton",
            "3-equal-column",
            "asymmetric",
            "error state",
            "accordion",
            "faq",
            "missing error",
            "dark mode toggle",
            "sun",
            "moon",
            "themetoggle",
            "darkmodetoggle",
        ],
        "guidance": "Replace lucide-react with Phosphor/Heroicons. Replace pill badges with squared (rounded-md). Replace hero dashboards with inline metrics.",
    },
    "react": {
        "keywords": [
            "missing key prop",
            "key prop",
            ".map() without key",
            "array index as key",
            "key={index}",
            "key={idx}",
            "useeffect",
            "empty dependency array",
            "async useeffect",
            "useeffect doesn't await",
            "framer motion",
            "usereducedmotion",
            "reduced motion check",
            "next/image",
            "next image",
            "raw <img>",
            "next.js image",
            "use client",
            "client boundary",
            "use client directive",
            "redundant boolean",
            "=== true",
            "=== false",
            "boolean comparison",
            "alert()",
            "browser alert",
            "blocking dialog",
            "style tag",
            "<style> tag",
            "style in jsx",
            "index as key",
            "index as react key",
            "deprecated class component",
            "class component",
            "purecomponent",
            "react.lazy",
            "lazy without suspense",
            "forwardref",
            "fragment shorthand",
            "react.fragment",
            "passive scroll",
            "passive: true",
            "scroll listener",
            "type='reset'",
            "discards all form data",
            "button type reset",
            "context provider",
            "inline object literal",
            "new reference on every render",
            "usestate initialized with",
            "constructor runs on every render",
        ],
        "guidance": "Add stable unique key props in .map() callbacks — never index. Fix useEffect dependencies (add missing deps, remove empty [] anti-pattern). Wrap async logic inside useEffect in a named async function, don't make the callback async. Import useReducedMotion from framer-motion and gate all animations. Replace raw <img> with next/image for automatic optimization. Replace === true/false with direct truthy checks. Replace alert() with toast/modal. Move <style> tags to CSS Modules or Tailwind classes. Convert class components to function components. Wrap React.lazy() in Suspense. Use <> shorthand instead of React.Fragment. Add {passive:true} to scroll listeners.",
    },
    "duplication": {
        "keywords": [
            "duplicate",
            "repeated",
            "copy-paste",
            "identical",
            "same className",
            "same hex",
            "duplicate import",
            "same module",
        ],
        "guidance": "Extract repeated className strings to cn()/cva() utilities. Extract copy-pasted markup into shared components. Merge duplicate media queries. Deduplicate event handlers.",
    },
    "dead code": {
        "keywords": [
            "commented-out",
            "unused import",
            "unreachable",
            "empty handler",
            "dead css",
            "empty css class",
            "empty rule block",
            "unused state",
            "deprecated",
            "console",
            "no-op",
            "todo",
            "fixme",
            "debugger statement",
            "prop-types imported",
            "runtime proptypes",
        ],
        "guidance": "Delete commented-out code (git has history). Remove unused imports via linter. Remove empty handlers. Delete dead CSS classes and empty rule blocks. Resolve TODOs or convert to tracked issues.",
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
    config = load_config()
    project_root = get_project_root()
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
            print(
                f"    [{issue.get('id', '?')}] {issue.get('file', '?')}: {issue.get('issue', '?')}"
            )
            print(f"      -> Fix: {issue.get('command', 'manual')}")
        print()

    if dry_run:
        print("[DRY RUN] No changes applied. Remove --dry-run to apply.")
        return

    transforms_dir = Path(__file__).parent.parent / "data" / "transforms"
    pre_existing_changes: set[str] = set()
    if config.get("auto_commit", False):
        pre_existing_changes = tracked_changed_files()

    # Map categories to transform files (multiple categories can share transforms)
    _TRANSFORM_MAP = {
        "typography": "typography.js",
        "color": "color.js",
        "materiality": "color.js",  # Color transform handles materiality patterns too
        "layout": "spacing.js",
        "motion": "typography.js",  # Typography transform handles animation replacements
        "states": "spacing.js",  # Spacing transform handles missing transitions
        "code quality": "spacing.js",  # Spacing transform handles z-index, empty handlers
        "accessibility": "spacing.js",  # Spacing transform handles outline-none → focus-visible
    }

    changed_files = set()
    transforms_run = set()

    def _normalize_issue_path(file_path: str) -> Path:
        path = Path(file_path)
        if path.is_absolute():
            return path
        return (project_root / path).resolve()

    for cat_name, cat_issues in grouped.items():
        # Check for exact category match, then mapped match
        transform_name = _TRANSFORM_MAP.get(cat_name, f"{cat_name}.js")
        transform_file = transforms_dir / transform_name

        if not transform_file.exists():
            continue

        # Avoid running the same transform on the same files twice
        transform_key = str(transform_file)
        if transform_key in transforms_run:
            continue

        # Collect all files needing this transform
        files_to_fix = []
        for cn, ci in grouped.items():
            mapped = _TRANSFORM_MAP.get(cn, f"{cn}.js")
            if mapped == transform_name:
                files_to_fix.extend([i["file"] for i in ci])
        files_to_fix = list(set(files_to_fix))

        # Only transform JS/TS files (jscodeshift doesn't handle CSS)
        js_exts = {".tsx", ".jsx", ".ts", ".js"}
        files_to_fix = [f for f in files_to_fix if Path(f).suffix.lower() in js_exts]

        if not files_to_fix:
            continue

        print(
            f"\n⚙️  Applying {transform_name} transforms via jscodeshift on {len(files_to_fix)} file(s)..."
        )
        transforms_run.add(transform_key)

        for file_path in files_to_fix:
            normalized_path = _normalize_issue_path(file_path)
            before_contents = None
            try:
                before_contents = normalized_path.read_text(encoding="utf-8")
            except OSError:
                pass

            try:
                result = subprocess.run(
                    [
                        "npx",
                        "jscodeshift",
                        "-t",
                        str(transform_file),
                        "--parser",
                        "tsx",
                        str(normalized_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=project_root,
                )
                if result.returncode == 0:
                    after_contents = before_contents
                    try:
                        after_contents = normalized_path.read_text(encoding="utf-8")
                    except OSError:
                        pass

                    if before_contents != after_contents:
                        changed_files.add(str(normalized_path))
                        print(f"    ✓ {normalized_path.name}")
                else:
                    stderr = result.stderr.strip()
                    if stderr:
                        print(f"    ⚠️  {normalized_path.name}: {stderr[:80]}")
            except FileNotFoundError:
                print(
                    "    ⚠️  npx not found. Install Node.js/npm for mechanical auto-fixing."
                )
                print("    Falling back to agent-assisted fixing.")
                break
            except subprocess.TimeoutExpired:
                print(f"    ⚠️  Timeout transforming {normalized_path.name}")
            except OSError as e:
                # subprocess.run raises OSError (not CalledProcessError) on bad exit
                # when check=False; catch generic OS errors from the child process.
                print(f"    ⚠️  Failed to transform {normalized_path.name}: {e}")

    if changed_files:
        print(
            f"\n✅ Automatically transformed {len(changed_files)} file(s) using jscodeshift."
        )

        # Auto-commit the mechanical fixes if enabled
        if config.get("auto_commit", False):
            if pre_existing_changes:
                print(
                    "   ⚠️  Skipped git auto-commit because tracked changes already existed before autofix."
                )
            else:
                try:
                    for f in changed_files:
                        subprocess.run(
                            ["git", "add", f],
                            check=True,
                            capture_output=True,
                            cwd=project_root,
                        )
                    subprocess.run(
                        [
                            "git",
                            "commit",
                            "-m",
                            f"[UIdetox] Autofix: mechanical T1 transforms ({len(changed_files)} files)",
                            "--no-verify",
                        ],
                        check=True,
                        capture_output=True,
                        cwd=project_root,
                    )
                    print("   📦 Auto-committed mechanical fixes to git.")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    print("   ⚠️  Git auto-commit failed.")

        print("Run `uidetox rescan` to update the issue queue.")

        # Mark the issues in transformed files as needing verification
        remaining_t1 = [
            issue
            for issue in t1_issues
            if str(_normalize_issue_path(issue.get("file", ""))) not in changed_files
        ]
        if remaining_t1:
            print(
                f"\n{len(remaining_t1)} T1 issue(s) in non-JS files need manual fixing:"
            )
            for issue in remaining_t1[:10]:
                print(
                    f"    [{issue.get('id', '?')}] {issue.get('file', '?')}: {issue.get('issue', '?')[:60]}"
                )
        return

    auto_commit = config.get("auto_commit", False)

    print("\n[AGENT INSTRUCTION]")
    print(
        f"Apply all {len(t1_issues)} T1 fixes listed above, working category by category."
    )
    print("For each fix:")
    print("  1. Open the file")
    print("  2. Apply the fix using the category guidance above")
    print('  3. Run `uidetox resolve <issue_id> --note "what you changed"` when done')
    if auto_commit:
        print(
            "\n  AUTO-COMMIT is ON — each `resolve` will atomically commit the fix to git."
        )
    print(
        "\nThese are safe, mechanical changes (font swaps, color replacements, spacing)."
    )
    print("Apply them all before moving to T2+ issues.")
