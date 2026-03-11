"""Static Slop Analyzer: Detects AI anti-patterns via regex/AST rules."""

import os
import re
from pathlib import Path

# Directories to always skip during traversal
IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "out", ".next",
    ".nuxt", "coverage", ".uidetox", ".claude", ".cursor", "vendor"
}

# File extensions frequently scanned
_FE_EXTS = {".css", ".scss", ".tsx", ".jsx", ".html", ".svelte", ".vue"}
_JSX_EXTS = {".tsx", ".jsx", ".html", ".svelte", ".vue"}
_ALL_FE_EXTS = _FE_EXTS | {".ts", ".js", ".less"}

HAS_AST = False
try:
    import tree_sitter
    import tree_sitter_javascript as ts_js
    import tree_sitter_typescript as ts_ts
    import tree_sitter_css as ts_css
    HAS_AST = True
    JS_LANG = tree_sitter.Language(ts_js.language())
    TSX_LANG = tree_sitter.Language(ts_ts.language_tsx())
    CSS_LANG = tree_sitter.Language(ts_css.language())
except ImportError:
    pass

# The Anti-Pattern Rule Catalog
RULES = [
    {
        "id": "TYPOGRAPHY_SLOP",
        "pattern": re.compile(r'\b(font-(inter|roboto|sans|arial|open-sans)|font-family:\s*(Inter|Roboto|Arial|System-ui))\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Generic AI Typography detected (Inter/Roboto/sans).",
        "command": "Swap font family to a distinctive typeface (Geist, Outfit, Satoshi, etc.) and update scale."
    },
    {
        "id": "COLOR_GRADIENT_SLOP",
        "pattern": re.compile(r'\b(from-(blue|purple|indigo)-[4-6]00.*?to-(purple|blue|indigo)-[4-6]00)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "AI Pipeline Palette (Purple-Blue gradient) detected.",
        "command": "Replace generic gradient with a high-contrast solid accent color on a neutral base."
    },
    {
        "id": "COLOR_BLACK_SLOP",
        "pattern": re.compile(r'\b(#000000|bg-black|text-black)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Pure black (#000000) detected. Pure black rarely exists in nature.",
        "command": "Replace true black with tinted dark neutrals (e.g. zinc-950 or slate-900)."
    },
    {
        "id": "ICONOGRAPHY_SLOP",
        "pattern": re.compile(r'\blucide-react\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Generic 'lucide-react' standard icons detected.",
        "command": "Swap icon library for Phosphor Icons, Heroicons, or custom SVG to build unique identity."
    },
    {
        "id": "MATERIALITY_RADIUS_SLOP",
        "pattern": re.compile(r'\b(rounded-2xl|rounded-3xl)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Oversized AI border radii (2xl/3xl) detected outside of modals/avatars.",
        "command": "Reduce border-radius to tighter bounds (rounded-lg or rounded-xl) for precision."
    },
    {
        "id": "LAYOUT_MATH_SLOP",
        "pattern": re.compile(r'\b(w-1/3|grid-cols-3)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Generic 3-Column feature card layout detected.",
        "command": "Refactor into an asymmetrical grid, zig-zag layout, or masonry flow to break predictability."
    },
    {
        "id": "GLASSMORPHISM_SLOP",
        "pattern": re.compile(r'\b(backdrop-blur|glass-?morphism|bg-white/\d|bg-opacity-)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Glassmorphism pattern detected — strong AI fingerprint.",
        "command": "Replace with solid surfaces, subtle borders, or elevation via shadow hierarchy."
    },
    {
        "id": "SHADOW_SLOP",
        "pattern": re.compile(r'\b(shadow-2xl|shadow-3xl|shadow-\[0_\d+px)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Oversized AI shadow detected (2xl/3xl).",
        "command": "Use subtle shadows (shadow-sm, shadow-md) or border-based elevation instead."
    },
    {
        "id": "HERO_DASHBOARD_SLOP",
        "pattern": re.compile(r'\b(stat-?card|metric-?card|dashboard-?hero|stats-?grid|kpi-?card)\b', re.IGNORECASE),
        "tier": "T3",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Hero metric dashboard pattern detected — cliché AI layout.",
        "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow."
    },
    {
        "id": "BOUNCE_ANIMATION_SLOP",
        "pattern": re.compile(r'\b(animate-bounce|animate-pulse|animate-spin)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Generic Tailwind animation (bounce/pulse/spin) detected.",
        "command": "Replace with intentional micro-interactions using CSS transitions or spring physics."
    },
    {
        "id": "GRAY_ON_COLOR_SLOP",
        "pattern": re.compile(r'text-gray-[3-5]00.*?bg-(blue|purple|green|indigo|violet)-', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Gray text on colored background detected — low contrast AI pattern.",
        "command": "Use white or high-contrast text on colored backgrounds. Check WCAG AA contrast ratio."
    },
    {
        "id": "MISSING_DARK_MODE",
        "pattern": re.compile(r'(?:bg-(white|gray|slate|zinc)-[12]00|bg-white)\b(?!.*dark:)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Light background without dark: variant detected.",
        "command": "Add dark mode variants (dark:bg-zinc-900) for every light surface color."
    },
    {
        "id": "SPACING_REPETITION_SLOP",
        "pattern": re.compile(r'(p-4|gap-4|space-y-4)(?:.*\1){4,}', re.DOTALL),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Excessive identical spacing repetition detected (5+ p-4/gap-4).",
        "command": "Introduce spacing scale variation (mix p-3, p-5, p-6) to create visual rhythm."
    },
    {
        "id": "CSS_GRADIENT_SLOP",
        "pattern": re.compile(r'linear-gradient\s*\([^)]*(?:purple|indigo|violet).*?(?:blue|cyan|sky)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less", ".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "CSS linear-gradient with purple-to-blue spectrum detected.",
        "command": "Replace with a single accent color or a more subtle, brand-aligned gradient."
    },
    {
        "id": "GENERIC_COPY_SLOP",
        "pattern": re.compile(r'\b(Supercharge|Revolutionize|Unlock the power|Seamlessly|Take your .* to the next level|Effortlessly)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue", ".md"},
        "description": "Generic AI startup marketing copy detected.",
        "command": "Rewrite copy to be specific, concrete, and human. Describe what the product does, not what it 'unlocks'."
    },
    {
        "id": "MISSING_HOVER_STATES",
        "pattern": re.compile(r'<button[^>]*className=["\'][^"\']*["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Button element without hover: state detected.",
        "command": "Add hover:, focus:, and active: states to all interactive elements.",
        "_custom_check": "missing_hover"
    },
    {
        "id": "EMOJI_HEAVY_SLOP",
        "pattern": re.compile(r'[\U0001f300-\U0001f9ff](?:.*[\U0001f300-\U0001f9ff]){5,}', re.DOTALL),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Emoji-heavy UI detected (6+ emoji in one file) — common AI pattern.",
        "command": "Replace decorative emoji with proper iconography or remove entirely. Keep emoji only in user content."
    },
    {
        "id": "OPACITY_ABUSE_SLOP",
        "pattern": re.compile(r'(?:opacity-\d{1,2}|bg-.*?/\d{1,2})(?:.*(?:opacity-\d{1,2}|bg-.*?/\d{1,2})){4,}', re.DOTALL),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Excessive opacity/transparency usage detected (glassmorphism cousin).",
        "command": "Use solid colors. Reserve transparency for overlays and modals only."
    },
    # ──────────────────────────────────────────────
    # NEW RULES (14 additional detections)
    # ──────────────────────────────────────────────
    {
        "id": "VIEWPORT_HEIGHT_SLOP",
        "pattern": re.compile(r'\bh-screen\b(?!.*min-h-)', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "h-screen without min-h-[100dvh] — breaks on iOS Safari.",
        "command": "Replace h-screen with min-h-[100dvh] for reliable full-height."
    },
    {
        "id": "GRADIENT_TEXT_SLOP",
        "pattern": re.compile(r'bg-clip-text.*?text-transparent|text-transparent.*?bg-clip-text', re.IGNORECASE | re.DOTALL),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Gradient text (bg-clip-text + text-transparent) — AI decoration cliche.",
        "command": "Replace gradient text with solid color and intentional font weight."
    },
    {
        "id": "NEON_GLOW_SLOP",
        "pattern": re.compile(r'\b(shadow-\[0_0_|shadow-glow|shadow-neon|ring-.*glow|drop-shadow.*0_0_)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": _FE_EXTS,
        "description": "Neon/outer glow shadow detected — cheap depth illusion.",
        "command": "Replace with inner borders or tinted subtle shadows. Remove decorative glows."
    },
    {
        "id": "PILL_BADGE_SLOP",
        "pattern": re.compile(r'rounded-full[^"]*(?:badge|tag|chip|label|pill)', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Pill-shaped badge/tag/chip detected — generic SaaS pattern.",
        "command": "Use square badges (rounded-md), flags, or plain text indicators instead."
    },
    {
        "id": "LOREM_IPSUM_SLOP",
        "pattern": re.compile(r'\b(lorem ipsum|dolor sit amet|consectetur adipiscing)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": _ALL_FE_EXTS,
        "description": "Lorem Ipsum placeholder text detected.",
        "command": "Write real, contextual draft copy. No placeholder Latin text."
    },
    {
        "id": "GENERIC_NAME_SLOP",
        "pattern": re.compile(r'\b(John Doe|Jane (?:Smith|Doe)|Acme (?:Corp|Inc)|SmartFlow|NexusAI)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Generic AI placeholder name detected (John Doe / Acme Corp).",
        "command": "Use diverse, realistic, creative names. Invent premium contextual brands."
    },
    {
        "id": "AI_COPY_CLICHE_SLOP",
        "pattern": re.compile(r'\b(Next-Gen|Game[- ]?changer|Cutting[- ]?edge|\bDelve\b|\bTapestry\b|Elevate your|Unleash the)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "AI copywriting cliche detected.",
        "command": "Replace with specific, concrete, benefit-driven language. No buzzwords."
    },
    {
        "id": "MISSING_FOCUS_SLOP",
        "pattern": re.compile(r'<(?:button|a)\s[^>]*className=["\'][^"\']*["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Interactive element without focus: state — accessibility gap.",
        "command": "Add focus:ring or focus:outline states for keyboard accessibility.",
        "_custom_check": "missing_focus"
    },
    {
        "id": "DIV_SOUP_SLOP",
        "pattern": re.compile(r'(?:<div[\s>])', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Div-heavy file with no semantic HTML elements detected.",
        "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>.",
        "_custom_check": "div_soup"
    },
    {
        "id": "CENTER_BIAS_SLOP",
        "pattern": re.compile(r'text-center.*mx-auto|mx-auto.*text-center', re.IGNORECASE | re.DOTALL),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Centered hero layout detected — banned when DESIGN_VARIANCE > 4.",
        "command": "Use split-screen, left-aligned, or asymmetric layouts instead of centered hero.",
        "_requires_variance_gt": 4
    },
    {
        "id": "CARD_NESTING_SLOP",
        "pattern": re.compile(r'(?:card|Card)["\']?[^<]{0,200}(?:card|Card)', re.IGNORECASE | re.DOTALL),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Nested card pattern detected (card inside card).",
        "command": "Flatten hierarchy. Use spacing, borders, or typography for inner grouping."
    },
    {
        "id": "CSS_PURE_BLACK_SLOP",
        "pattern": re.compile(r'(?:color|background(?:-color)?)\s*:\s*#000(?:000)?\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Pure black (#000) in CSS — rarely exists in nature.",
        "command": "Replace with off-black tinted neutral (e.g., #0f0f0f, #1a1a2e, #0d1117)."
    },
    {
        "id": "HARDCODED_ZINDEX_SLOP",
        "pattern": re.compile(r'\b(z-index:\s*9{3,}|z-\[9{3,}\])\b', re.IGNORECASE),
        "tier": "T1",
        "exts": _ALL_FE_EXTS,
        "description": "Arbitrary z-index (9999+) detected — no z-index system.",
        "command": "Create a semantic z-index scale (dropdown=10, sticky=20, modal=30, toast=40, tooltip=50)."
    },
    {
        "id": "OVERPADDED_LAYOUT_SLOP",
        "pattern": re.compile(r'(p-(?:8|10|12|16))(?:.*\1){3,}', re.DOTALL),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Excessive large padding repetition detected (overpadded layout).",
        "command": "Reduce padding and vary spacing scale (p-4, p-5, p-6) for visual rhythm."
    },
    {
        "id": "SOLID_DIVIDER_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*border-(?:gray|slate|zinc|neutral|stone)-(?:200|300|700|800)(?!\/\d+)[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Solid opaque borders for dividers detected. Harsh on the eyes.",
        "command": "Use opacity (e.g., border-gray-200/50 or border-white/10) for softer blending."
    },
    {
        "id": "HARDCODED_PX_FONT_SLOP",
        "pattern": re.compile(r'(?:font-size:\s*\d+px|text-\[\d+px\])', re.IGNORECASE),
        "tier": "T1",
        "exts": _ALL_FE_EXTS,
        "description": "Hardcoded px font sizes break accessible scaling.",
        "command": "Use rem or Tailwind text-sm/text-lg scale for accessibility."
    },
    {
        "id": "UGLY_SCROLLBAR_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*overflow-[xy]-(?:auto|scroll)[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Scrollable container without scrollbar styling or hiding.",
        "command": "Add scrollbar-hide or custom CSS scrollbar for polish.",
        "_custom_check": "ugly_scrollbar"
    },
    {
        "id": "TIGHT_LINE_HEIGHT_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*(?:text-(?:sm|xs|base)[^"\']*leading-(?:none|tight)|leading-(?:none|tight)[^"\']*text-(?:sm|xs|base))[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Overly tight line-height on body text reduces readability.",
        "command": "Use leading-relaxed or leading-normal for paragraphs."
    },
    {
        "id": "MISSING_TRANSITION_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*hover:[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Interactive element with hover states but missing transition class.",
        "command": "Add 'transition-colors' or 'transition-all' with duration (e.g., duration-200) for smooth easing.",
        "_custom_check": "missing_transition"
    },
    {
        "id": "ORPHANED_LABEL_SLOP",
        "pattern": re.compile(r'<label\b(?![^>]*htmlFor=)[^>]*>', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Accessible forms require 'htmlFor' on <label>.",
        "command": "Add htmlFor attribute to <label> pointing to the input ID."
    },
    {
        "id": "LAZY_FLEX_CENTER_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*flex(?:\s+)justify-center(?:\s+)items-center[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Verbose flex centering detected.",
        "command": "Use 'grid place-items-center' instead of 'flex items-center justify-center' for cleaner markup."
    },
    {
        "id": "RAW_COLOR_SLOP",
        "pattern": re.compile(r'(?:color|background-color):\s*(?:red|blue|green|purple|orange|yellow)\b\s*[;}]', re.IGNORECASE),
        "tier": "T1",
        "exts": _ALL_FE_EXTS,
        "description": "Using basic named CSS colors (red, blue). Looks unpolished.",
        "command": "Use a curated hex/hsl palette or Tailwind colors (e.g. text-blue-500) instead."
    },
    # ──────────────────────────────────────────────
    # ADDITIONAL RULES (10 more detections for 2024+ patterns)
    # ──────────────────────────────────────────────
    {
        "id": "IMPORTANT_ABUSE_SLOP",
        "pattern": re.compile(r'!important', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "!important override detected — indicates specificity war.",
        "command": "Refactor CSS specificity. Use lower-specificity selectors or CSS layers instead of !important."
    },
    {
        "id": "INLINE_STYLE_SLOP",
        "pattern": re.compile(r'\bstyle=\{?\{[^}]{40,}\}\}?', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Large inline style object detected (40+ chars). Harms maintainability.",
        "command": "Extract inline styles to Tailwind classes, CSS modules, or styled-components."
    },
    {
        "id": "CONSOLE_LOG_SLOP",
        "pattern": re.compile(r'\bconsole\.(log|warn|error|debug|info)\s*\(', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Console statement detected in production code.",
        "command": "Remove console statements or replace with a proper logging utility."
    },
    {
        "id": "TODO_FIXME_SLOP",
        "pattern": re.compile(r'(?://|/\*|<!--)\s*(?:TODO|FIXME|HACK|XXX|TEMP)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "TODO/FIXME/HACK comment detected — unfinished work.",
        "command": "Resolve the TODO or convert to a tracked issue. No orphan comments in production."
    },
    {
        "id": "MAGIC_NUMBER_SLOP",
        "pattern": re.compile(r'(?:margin|padding|gap|top|left|right|bottom|width|height):\s*\d{3,}px', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Magic number (large px value) in CSS — no spacing system.",
        "command": "Use spacing tokens or CSS custom properties. Map values to a design scale."
    },
    {
        "id": "NESTED_TERNARY_SLOP",
        "pattern": re.compile(r'\?[^:]*\?[^:]*:', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Nested ternary operator detected — harms readability in JSX.",
        "command": "Extract nested ternaries into named variables or early returns for clarity.",
        "_custom_check": "nested_ternary"
    },
    {
        "id": "DISABLED_NO_CURSOR_SLOP",
        "pattern": re.compile(r'disabled[^"\']*(?:className|class)=["\'][^"\']*["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Disabled element without cursor-not-allowed style.",
        "command": "Add 'disabled:cursor-not-allowed disabled:opacity-50' for clear disabled state.",
        "_custom_check": "disabled_cursor"
    },
    {
        "id": "BROKEN_IMAGE_SLOP",
        "pattern": re.compile(r'(?:src|href)=["\']https?://(?:unsplash\.com|images\.unsplash\.com|source\.unsplash\.com)', re.IGNORECASE),
        "tier": "T1",
        "exts": _ALL_FE_EXTS,
        "description": "Direct Unsplash URL detected — likely to break. Use picsum.photos instead.",
        "command": "Replace with https://picsum.photos/seed/{name}/800/600 for reliable placeholders."
    },
    {
        "id": "EXCLAMATION_UX_SLOP",
        "pattern": re.compile(r'(?:Success|Saved|Done|Created|Updated|Deleted|Welcome)[^.]*!', re.IGNORECASE),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Exclamation mark in success/status message — feels unprofessional.",
        "command": "Remove exclamation marks from status messages. Use calm, confident tone."
    },
    {
        "id": "OOPS_ERROR_SLOP",
        "pattern": re.compile(r'\b(?:Oops|Whoops|Uh[- ]?oh|Oh no)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Infantile error messaging detected (Oops/Whoops/Uh-oh).",
        "command": "Replace with direct, actionable error messages. Be specific about what went wrong."
    },
    # ──────────────────────────────────────────────
    # DUPLICATION SMELLS
    # ──────────────────────────────────────────────
    {
        "id": "DUPLICATE_TAILWIND_BLOCK",
        "pattern": re.compile(
            r'class(?:Name)?=["\']([^"\']{40,})["\']'
            r'(?:[\s\S]{0,2000})'
            r'class(?:Name)?=["\'](\1)["\']',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Repeated identical long className string detected — extract to component or utility.",
        "command": "Extract duplicated class strings to a shared component, cn() utility, or cva() variant."
    },
    {
        "id": "DUPLICATE_COLOR_LITERAL",
        "pattern": re.compile(
            r'(#[0-9a-fA-F]{6})\b(?:[\s\S]{0,3000})\1(?:[\s\S]{0,3000})\1',
        ),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Same hex color literal repeated 3+ times — extract to CSS variable or design token.",
        "command": "Define a CSS custom property (--color-brand: #XXXXXX) and reference it everywhere."
    },
    {
        "id": "COPY_PASTE_COMPONENT",
        "pattern": re.compile(
            r'(<(?:div|section|article)\s[^>]{30,}>)'
            r'([\s\S]{80,300}?)'
            r'</(?:div|section|article)>'
            r'[\s\S]{0,200}'
            r'\1\2',
            re.IGNORECASE,
        ),
        "tier": "T3",
        "exts": _JSX_EXTS,
        "description": "Copy-pasted markup block detected — extract to reusable component.",
        "command": "Extract repeated markup into a shared component with props for variation."
    },
    {
        "id": "DUPLICATE_HANDLER",
        "pattern": re.compile(
            r'((?:on(?:Click|Change|Submit|Press|Focus|Blur))\s*=\s*\{[^}]{20,}\})'
            r'[\s\S]{0,2000}\1',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Identical inline event handler duplicated — extract to named function.",
        "command": "Extract duplicated handler logic into a named function or custom hook."
    },
    {
        "id": "REPEATED_MEDIA_QUERY",
        "pattern": re.compile(
            r'(@media\s*\([^)]+\)\s*\{)'
            r'[\s\S]{0,5000}'
            r'\1',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Same @media query duplicated — consolidate into one block.",
        "command": "Merge duplicate media queries into a single block or use container queries."
    },
    # ──────────────────────────────────────────────
    # DEAD CODE SMELLS
    # ──────────────────────────────────────────────
    {
        "id": "COMMENTED_OUT_CODE",
        "pattern": re.compile(
            r'(?://|/\*|{/\*)\s*(?:'
            r'<[A-Z][a-zA-Z]+|'               # Commented JSX component
            r'(?:const|let|var|function|import|export|return|if|for)\s|'  # Commented JS
            r'(?:className|onClick|onChange|style)='  # Commented JSX attrs
            r')',
            re.IGNORECASE,
        ),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Commented-out code detected — use version control, not comments.",
        "command": "Delete commented-out code. Git preserves history. Ship only live code.",
        "_custom_check": "commented_code"
    },
    {
        "id": "UNUSED_IMPORT",
        "pattern": re.compile(
            r'^import\s+(?:\{[^}]+\}|[A-Za-z_$]+)\s+from\s+["\'][^"\']+["\'];?\s*$',
            re.MULTILINE,
        ),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Potentially unused import detected — verify and remove.",
        "command": "Run `uidetox check --fix` to auto-remove unused imports via linter.",
        "_custom_check": "unused_import"
    },
    {
        "id": "UNREACHABLE_CODE",
        "pattern": re.compile(
            r'(?:return|throw|break|continue)\s[^;]*;\s*\n\s*(?![\s})\]*/])'
            r'(?:const|let|var|function|if|for|while|switch|try)\b',
            re.MULTILINE,
        ),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Unreachable code after return/throw/break detected.",
        "command": "Remove dead code after return/throw/break statements."
    },
    {
        "id": "EMPTY_HANDLER",
        "pattern": re.compile(
            r'(?:on(?:Click|Change|Submit|Press|Focus|Blur|Key\w+))\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}',
            re.IGNORECASE,
        ),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Empty event handler (no-op arrow function) detected.",
        "command": "Either implement the handler or remove the prop. No-op handlers confuse readers."
    },
    {
        "id": "DEAD_CSS_CLASS",
        "pattern": re.compile(
            r'^\s*\.(?:[a-zA-Z_][\w-]*)\s*\{\s*\}',
            re.MULTILINE,
        ),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Empty CSS rule (no declarations) detected — dead code.",
        "command": "Remove empty CSS classes or add declarations."
    },
    {
        "id": "UNUSED_STATE",
        "pattern": re.compile(
            r'const\s+\[(\w+),\s*set\w+\]\s*=\s*useState',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "useState declaration where state variable may be unused.",
        "command": "Verify the state variable is referenced in JSX or effects. Remove if unused.",
        "_custom_check": "unused_state"
    },
    {
        "id": "DEPRECATED_LIFECYCLE",
        "pattern": re.compile(
            r'\b(?:componentWillMount|componentWillReceiveProps|componentWillUpdate|UNSAFE_componentWillMount|UNSAFE_componentWillReceiveProps|UNSAFE_componentWillUpdate)\b',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "Deprecated React lifecycle method detected.",
        "command": "Migrate to functional components with hooks (useEffect, useMemo)."
    },
    {
        "id": "DISABLED_LINT_RULE",
        "pattern": re.compile(
            r'(?://\s*eslint-disable(?:-next-line)?|/\*\s*eslint-disable)',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".ts", ".js"},
        "description": "ESLint disable directive detected — suppressing lint rules.",
        "command": "Fix the underlying lint issue instead of suppressing it."
    },
    {
        "id": "ANY_TYPE_SLOP",
        "pattern": re.compile(
            r':\s*any\b|as\s+any\b|<any>',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": {".tsx", ".ts"},
        "description": "TypeScript `any` type detected — defeats type safety.",
        "command": "Replace `any` with a proper type, `unknown`, or a generic parameter."
    },
    {
        "id": "TS_IGNORE_SLOP",
        "pattern": re.compile(
            r'(?://\s*@ts-ignore|//\s*@ts-expect-error|//\s*@ts-nocheck)',
            re.IGNORECASE,
        ),
        "tier": "T2",
        "exts": {".tsx", ".ts"},
        "description": "TypeScript suppression directive detected (@ts-ignore/@ts-nocheck).",
        "command": "Fix the type error instead of suppressing it. Use @ts-expect-error only as last resort with explanation."
    },
    {
        "id": "LOW_CONTRAST_SLOP",
        "pattern": None,
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Text contrast ratio below WCAG AA standard (4.5:1).",
        "command": "Increase text contrast against background color.",
        "_custom_check": "contrast_ratio"
    },
]

def _get_parser(ext: str):
    if not HAS_AST:
        return None
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return tree_sitter.Parser(JS_LANG)
    elif ext in {".ts", ".tsx"}:
        return tree_sitter.Parser(TSX_LANG)
    elif ext in {".css", ".scss", ".less"}:
        return tree_sitter.Parser(CSS_LANG)
    return None

def _analyze_ast(filepath: Path, content: str, ext: str) -> list[dict]:
    parser = _get_parser(ext)
    if not parser:
        return []
        
    try:
        tree = parser.parse(content.encode("utf-8", errors="ignore"))
    except Exception:
        return []
        
    issues = []
    
    if ext in {".tsx", ".jsx", ".js", ".ts"}:
        state = {"div_count": 0, "semantic_count": 0, "nested_ternaries": 0, "cards": 0, "charts": 0}
        
        def walk(node):
            if node.type in ("jsx_element", "jsx_self_closing_element"):
                open_tag = node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
                if open_tag:
                    name_node = open_tag.child_by_field_name("name")
                    if name_node:
                        try:
                            tag_name = name_node.text.decode("utf-8", errors="ignore")
                        except AttributeError:
                            tag_name = str(name_node.text)
                        
                        if tag_name == "div":
                            state["div_count"] += 1
                        elif tag_name in {"nav", "main", "article", "section", "aside", "header", "footer"}:
                            state["semantic_count"] += 1
                            
                        # Detect Dashboard Slop
                        if "Card" in tag_name or "Stat" in tag_name or "Metric" in tag_name:
                            state["cards"] += 1
                        elif "Chart" in tag_name or "Graph" in tag_name or "Activity" in tag_name:
                            state["charts"] += 1
                            
            elif node.type == "ternary_expression":
                for child in node.children:
                    if child.type == "ternary_expression":
                        state["nested_ternaries"] += 1
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        
        if state["div_count"] > 20 and state["semantic_count"] == 0:
            issues.append({
                "file": str(filepath.resolve()),
                "tier": "T2",
                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state['div_count']} divs, 0 semantic elements)",
                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>."
            })
            
        if state["nested_ternaries"] >= 2:
            issues.append({
                "file": str(filepath.resolve()),
                "tier": "T2",
                "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state['nested_ternaries']} nested ternaries found)",
                "command": "Extract nested ternaries into named variables or early returns for clarity."
            })
            
        if state["cards"] >= 3 and state["charts"] >= 1:
            issues.append({
                "file": str(filepath.resolve()),
                "tier": "T3",
                "issue": f"Hero metric dashboard pattern detected via AST ({state['cards']} cards, {state['charts']} charts) — cliché AI layout.",
                "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow."
            })

    return issues

def analyze_file(filepath: Path, design_variance: int = 8, dynamic_colors: dict[str, str] | None = None) -> list[dict]:
    """Scan a single file against all slop rules.

    Args:
        filepath: File to scan.
        design_variance: Current DESIGN_VARIANCE dial value (affects conditional rules).
        dynamic_colors: Tailwind configuration colors mappings.
    """
    issues = []
    ext = filepath.suffix.lower()

    # Filter rules that apply to this file extension
    applicable_rules = []
    for r in RULES:
        exts = r.get("exts", [])
        if isinstance(exts, (list, set, tuple)) and ext in exts:
            applicable_rules.append(r)
    if not applicable_rules:
        return issues

    try:
        # 1MB size guard to prevent regex engine freezing on massive bundled files
        if filepath.stat().st_size > 1_000_000:
            return issues
            
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return issues  # Skip binary or unreadable files

    if HAS_AST:
        ast_issues = _analyze_ast(filepath, content, ext)
        issues.extend(ast_issues)

    for rule in applicable_rules:
        # Skip rules conditioned on DESIGN_VARIANCE if below threshold
        variance_threshold = rule.get("_requires_variance_gt")
        if isinstance(variance_threshold, (int, float)) and design_variance <= variance_threshold:
            continue

        # Custom check: div_soup requires counting, not just pattern match
        custom = rule.get("_custom_check")
        if custom == "div_soup":
            if HAS_AST and ext in {".tsx", ".jsx", ".js", ".ts"}:
                continue # Handled by AST
            div_count = len(re.findall(r'<div[\s>]', content, re.IGNORECASE))
            semantic_count = len(re.findall(
                r'<(?:nav|main|article|section|aside|header|footer)[\s>]',
                content, re.IGNORECASE
            ))
            if div_count > 20 and semantic_count == 0:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({div_count} divs, 0 semantic elements)",
                    "command": rule["command"]
                })
            continue

        # Custom check: missing_hover — buttons with className but no hover: class
        if custom == "missing_hover":
            for m in re.finditer(r'<button[^>]*className=["\']([^"\']*)["\']', content, re.IGNORECASE):
                classes = m.group(1)
                if "hover:" not in classes:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"]
                    })
                    break  # Flag once per file
            continue

        # Custom check: missing_focus — interactive elements without focus: class
        if custom == "missing_focus":
            for m in re.finditer(r'<(?:button|a)\s[^>]*className=["\']([^"\']*)["\']', content, re.IGNORECASE):
                classes = m.group(1)
                if "focus:" not in classes:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"]
                    })
                    break  # Flag once per file
            continue

        # Custom check: missing_transition — hover: classes without transition-
        if custom == "missing_transition":
            for m in re.finditer(r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE):
                classes = m.group(1)
                if "hover:" in classes and "transition" not in classes:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"]
                    })
                    break  # Flag once per file
            continue

        # Custom check: ugly_scrollbar — overflow scroll without scrollbar styling
        if custom == "ugly_scrollbar":
            for m in re.finditer(r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE):
                classes = m.group(1)
                if re.search(r'overflow-[xy]-(?:auto|scroll)', classes) and "scrollbar" not in classes:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"]
                    })
                    break  # Flag once per file
            continue

        # Custom check: nested_ternary — only flag in JSX return blocks (rough heuristic)
        if custom == "nested_ternary":
            if HAS_AST and ext in {".tsx", ".jsx", ".js", ".ts"}:
                continue # Handled by AST
            # Count nested ternaries: lines with ? ... ? ... : pattern
            ternary_nests = len(re.findall(r'\?[^:?\n]{0,80}\?', content))
            if ternary_nests >= 2:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({ternary_nests} nested ternaries found)",
                    "command": rule["command"]
                })
            continue

        # Custom check: disabled_cursor — disabled elements missing cursor-not-allowed
        if custom == "disabled_cursor":
            # Find elements with disabled prop/attr
            disabled_elements = re.findall(
                r'(?:disabled|isDisabled)[^>]*class(?:Name)?=["\']([^"\']*)["\']',
                content, re.IGNORECASE
            )
            for classes in disabled_elements:
                if "cursor-not-allowed" not in classes and "disabled:" not in classes:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"]
                    })
                    break
            continue

        # Custom check: commented_code — blocks of commented-out source code (not doc comments)
        if custom == "commented_code":
            lines = content.splitlines()
            commented_code_lines = 0
            for line in lines:
                stripped = line.strip()
                # Match single-line commented code patterns
                if re.match(
                    r'^(?://|/\*|\*|{/\*)\s*(?:'
                    r'<[A-Z]|'
                    r'(?:const|let|var|function|import|export|return|if|for|while)\s|'
                    r'(?:className|onClick|onChange|style)=|'
                    r'\w+\.\w+\(|'
                    r'\}\s*(?:else|catch|finally)|'
                    r'(?:await|async)\s'
                    r')',
                    stripped,
                ):
                    commented_code_lines += 1
            if commented_code_lines >= 3:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({commented_code_lines} lines of commented-out code)",
                    "command": rule["command"]
                })
            continue

        # Custom check: contrast_ratio
        if custom == "contrast_ratio" and dynamic_colors:
            for m in re.finditer(r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE):
                classes = m.group(1).split()
                bg_color = None
                text_color = None
                
                for c in classes:
                    if c.startswith("bg-"):
                        bg_name = c[3:].split('/')[0]
                        if bg_name in dynamic_colors:
                            bg_color = dynamic_colors[bg_name]
                    elif c.startswith("text-"):
                        text_name = c[5:].split('/')[0]
                        if text_name in dynamic_colors:
                            text_color = dynamic_colors[text_name]
                            
                if bg_color and text_color:
                    from uidetox.color_utils import contrast_ratio
                    ratio = contrast_ratio(text_color, bg_color)
                    if ratio < 4.5:
                        issues.append({
                            "file": str(filepath.resolve()),
                            "tier": rule["tier"],
                            "issue": f"Low contrast detected: {text_color} on {bg_color} (ratio {ratio:.1f}:1).",
                            "command": rule["command"]
                        })
                        break
            continue

        # Custom check: unused_import — imports whose identifiers appear nowhere else in the file
        if custom == "unused_import":
            import_pattern = re.compile(
                r'^import\s+'
                r'(?:'
                r'(?:type\s+)?(\w+)(?:\s*,\s*\{([^}]+)\})?'  # default + named
                r'|\{([^}]+)\}'                                 # named only
                r'|\*\s+as\s+(\w+)'                             # namespace
                r')'
                r'\s+from\s+["\'][^"\']+["\'];?\s*$',
                re.MULTILINE,
            )
            unused_names: list[str] = []
            for m in import_pattern.finditer(content):
                names: list[str] = []
                if m.group(1):
                    names.append(m.group(1))
                for g in (m.group(2), m.group(3)):
                    if g:
                        for part in g.split(","):
                            part = part.strip()
                            if " as " in part:
                                part = part.split(" as ")[-1].strip()
                            if part and part != "type":
                                names.append(part)
                if m.group(4):
                    names.append(m.group(4))
                for name in names:
                    # Count occurrences beyond the import line itself
                    occurrences = len(re.findall(r'\b' + re.escape(name) + r'\b', content))
                    if occurrences <= 1:
                        unused_names.append(name)
            if unused_names:
                sample = ", ".join(unused_names[:5])
                suffix = f" (+{len(unused_names) - 5} more)" if len(unused_names) > 5 else ""
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} Likely unused: {sample}{suffix}",
                    "command": rule["command"]
                })
            continue

        # Custom check: unused_state — useState where the state var is never read
        if custom == "unused_state":
            for m in re.finditer(r'const\s+\[(\w+),\s*set(\w+)\]\s*=\s*useState', content):
                state_var = m.group(1)
                # Check if state var is referenced beyond the declaration
                occurrences = len(re.findall(r'\b' + re.escape(state_var) + r'\b', content))
                if occurrences <= 1:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} `{state_var}` appears unused.",
                        "command": rule["command"]
                    })
                    break  # Flag once per file
            continue

        # Standard regex match — flag once per file
        pattern = rule.get("pattern")
        if isinstance(pattern, re.Pattern) and pattern.search(content):
            issues.append({
                "file": str(filepath.resolve()),
                "tier": rule["tier"],
                "issue": rule["description"],
                "command": rule["command"]
            })

    return issues

def analyze_directory(root_path: str = ".", exclude_paths: list[str] | None = None,
                      zone_overrides: dict[str, str] | None = None,
                      design_variance: int = 8) -> list[dict]:
    """Walk directory and return a flat list of all detected slop issues.

    Args:
        root_path: Directory to scan.
        exclude_paths: Additional directory names/paths to skip (from ``uidetox exclude``).
        zone_overrides: File-to-zone mapping; files in 'vendor' or 'generated' zones are skipped.
        design_variance: DESIGN_VARIANCE dial value passed to per-file analysis.
    """
    all_issues = []
    root = Path(root_path).resolve()

    # Merge user excludes with built-in ignore list
    skip_dirs = set(IGNORE_DIRS)
    if exclude_paths:
        for ep in exclude_paths:
            skip_dirs.add(ep.strip("/").split("/")[-1] if "/" in ep else ep)

    # Build a set of absolute paths to skip via zone overrides
    zone_skip: set[str] = set()
    if zone_overrides:
        for fpath, zone in zone_overrides.items():
            if zone in ("vendor", "generated"):
                zone_skip.add(str(Path(fpath).resolve()))

    from concurrent.futures import ThreadPoolExecutor
    from uidetox.color_utils import load_dynamic_colors

    dynamic_colors = load_dynamic_colors(root)

    def _analyze_wrapper(fp: Path) -> list:
        return analyze_file(fp, design_variance=design_variance, dynamic_colors=dynamic_colors) # type: ignore

    futures = []
    with ThreadPoolExecutor() as executor:
        for dirpath, dirnames, filenames in os.walk(root):
            # Mutate dirnames in-place to skip IGNORE_DIRS + user excludes
            new_dir = [d for d in dirnames if d not in skip_dirs and not d.startswith('.')]
            dirnames.clear()
            dirnames.extend(new_dir)
    
            for filename in filenames:
                file_path = Path(dirpath) / filename
    
                # Respect zone overrides
                if zone_skip and str(file_path.resolve()) in zone_skip:
                    continue
    
                futures.append(executor.submit(_analyze_wrapper, file_path)) # type: ignore
                
        for future in futures:
            all_issues.extend(future.result())

    return all_issues
