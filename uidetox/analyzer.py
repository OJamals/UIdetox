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
        "pattern": re.compile(r'(p-(?:8|10|12|16))(?:.*\1){2,}', re.DOTALL),
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
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*flex[^"\']*(?:items-center[^"\']*justify-center|justify-center[^"\']*items-center)[^"\']*["\']', re.IGNORECASE),
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
    # ──────────────────────────────────────────────
    # ACCESSIBILITY RULES
    # ──────────────────────────────────────────────
    {
        "id": "ARIA_HIDDEN_INTERACTIVE_SLOP",
        "pattern": re.compile(r'<(?:button|a)\b[^>]+aria-hidden=["\']true["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Interactive element with aria-hidden=true — invisible to screen readers.",
        "command": "Remove aria-hidden from interactive elements or replace with visually-hidden span.",
    },
    {
        "id": "EMPTY_ARIA_LABEL_SLOP",
        "pattern": re.compile(r'aria-label=(?:""|\'\')', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Empty aria-label provides no accessible name — worse than no label.",
        "command": "Provide a meaningful aria-label value or remove the attribute.",
    },
    {
        "id": "VAGUE_ARIA_LABEL_SLOP",
        "pattern": re.compile(r'aria-label=["\'](?:button|close|icon|link|image)["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Generic single-word aria-label detected — not descriptive enough.",
        "command": "Use specific aria-label values that describe the action (e.g. 'Close dialog', 'Share article').",
    },
    {
        "id": "TABINDEX_POSITIVE_SLOP",
        "pattern": re.compile(r'tabIndex=\{[1-9]\d*\}|tabindex="[1-9]', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Positive tabindex breaks natural focus order (WCAG 2.4.3).",
        "command": "Remove positive tabindex. Use DOM order and tabIndex={0} for focusable elements.",
    },
    {
        "id": "TABINDEX_ZERO_DIV_SLOP",
        "pattern": re.compile(r'<div\b[^>]+tabIndex=\{0\}|<div\b[^>]+tabindex="0"', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "tabIndex={0} on a <div> — use a semantic interactive element instead.",
        "command": "Replace <div tabIndex={0}> with <button> or <a> for proper keyboard semantics.",
    },
    {
        "id": "TABLE_HEADER_NO_SCOPE_SLOP",
        "pattern": re.compile(r'<th\b(?![^>]*scope=)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<th> without scope attribute — table accessibility gap.",
        "command": "Add scope='col' or scope='row' to all <th> elements.",
    },
    {
        "id": "IFRAME_NO_TITLE_SLOP",
        "pattern": re.compile(r'<iframe\b(?![^>]*title=)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<iframe> without title attribute — inaccessible to screen readers.",
        "command": "Add a descriptive title attribute to every <iframe>.",
    },
    {
        "id": "INPUT_NO_TYPE_SLOP",
        "pattern": re.compile(r'<input\b(?![^>]*(?:\btype=|\.\.\.))', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<input> without type attribute defaults to text — may surprise mobile users.",
        "command": "Always specify type= on <input> elements (text, email, password, number, etc.).",
    },
    {
        "id": "BUTTON_TYPE_MISSING_SLOP",
        "pattern": re.compile(r'<button\b(?![^>]*\btype=)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<button> without type= attribute defaults to submit inside forms.",
        "command": "Add type='button' to buttons that don't submit forms.",
    },
    {
        "id": "BUTTON_TYPE_RESET_SLOP",
        "pattern": re.compile(r'type=["\']reset["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "type='reset' button — resets entire form unexpectedly.",
        "command": "Remove reset buttons or implement controlled form state reset manually.",
    },
    {
        "id": "USER_SCALABLE_DISABLED_SLOP",
        "pattern": re.compile(r'user-scalable=(?:no|0)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".html"},
        "description": "user-scalable=no disables pinch-zoom — WCAG 1.4.4 violation.",
        "command": "Remove user-scalable=no from viewport meta tag.",
    },
    {
        "id": "MISSING_ARIA_ROLE_SLOP",
        "pattern": None,
        "_custom_check": "missing_aria_role",
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Div/span with click/key handler but no role= — not accessible.",
        "command": "Add role='button' or role='link' and keyboard handler to interactive divs.",
    },
    {
        "id": "AUTOCOMPLETE_OFF_SLOP",
        "pattern": re.compile(r'auto[Cc]omplete=["\']off["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "autocomplete=off — blocks password managers and hurts UX.",
        "command": "Remove autocomplete=off. Use appropriate autocomplete values instead.",
    },
    {
        "id": "AUTOFOCUS_SLOP",
        "pattern": re.compile(r'autoFocus(?!\s*=\s*\{false\})', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "autoFocus hijacks keyboard flow — disorienting for screen reader users.",
        "command": "Remove autoFocus or manage focus programmatically with useEffect + ref.focus().",
    },
    {
        "id": "ALL_CAPS_HEADER_SLOP",
        "pattern": re.compile(r'<h[123][^>]*class(?:Name)?=["\'][^"\']*\buppercase\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Uppercase heading via CSS class — WCAG 1.3.1, screen readers announce as shouting.",
        "command": "Use proper case in heading text. Apply text-transform only to decorative elements.",
    },
    {
        "id": "VAGUE_BUTTON_LABEL_SLOP",
        "pattern": re.compile(r'<[Bb]utton[^>]*>\s*(?:Submit|OK|Click here)\s*</[Bb]utton>', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Generic button label (Submit/OK/Click here) — not descriptive.",
        "command": "Use specific action labels: 'Save settings', 'Complete order', 'Learn more about X'.",
    },
    {
        "id": "DIALOG_ROLE_ON_DIV_SLOP",
        "pattern": re.compile(r'<(?:div|section|span)[^>]+role=["\']dialog["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "role='dialog' on non-<dialog> element — missing focus trap and ARIA attrs.",
        "command": "Use native <dialog> element or a headless library (Radix, HeadlessUI) for accessible modals.",
    },
    {
        "id": "EMPTY_HREF_SLOP",
        "pattern": re.compile(r'''href=(?:"#"|'#'|"javascript:|'javascript:)''', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "href='#' or javascript: link — bad accessibility and UX.",
        "command": "Use a <button> for actions. Use a real URL for links.",
    },
    {
        "id": "VIDEO_NO_CAPTIONS_SLOP",
        "pattern": re.compile(r'<video\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<video> element — verify captions/subtitles are provided (WCAG 1.2.2).",
        "command": "Add <track kind='captions'> inside <video> for accessibility.",
        "_custom_check": "video_no_captions"
    },
    {
        "id": "GENERIC_LOADING_TEXT_SLOP",
        "pattern": re.compile(r'"Loading\.\.\."|\>Loading\.\.\.<', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".js"},
        "description": "Generic 'Loading...' text — not descriptive for screen readers.",
        "command": "Use descriptive loading messages with aria-live='polite' and meaningful context.",
    },
    # ──────────────────────────────────────────────
    # CSS RULES
    # ──────────────────────────────────────────────
    {
        "id": "HARDCODED_BREAKPOINT_SLOP",
        "pattern": re.compile(r'@media\s*\((?:max|min)-width:\s*\d+px\)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Hardcoded px breakpoint in @media query — no responsive token system.",
        "command": "Extract breakpoints to CSS custom properties or use a design token system.",
    },
    {
        "id": "WILL_CHANGE_ABUSE_SLOP",
        "pattern": re.compile(r'will-change:\s*(?:transform|opacity|all)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "will-change used — confirm it actually improves performance (overuse causes memory issues).",
        "command": "Apply will-change only to elements that actually animate. Remove after animation via JS.",
    },
    {
        "id": "HEIGHT_ANIMATION_SLOP",
        "pattern": re.compile(r'transition:\s*height', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Animating height triggers layout — janky and battery-draining.",
        "command": "Use max-height animation, grid-template-rows, or JS for smooth expand/collapse.",
    },
    {
        "id": "TRANSITION_ALL_SLOP",
        "pattern": re.compile(r'transition:\s*all\b|\btransition-all\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less", ".tsx", ".jsx"},
        "description": "transition: all — animates everything including layout properties.",
        "command": "Specify only compositor-safe properties: transition: transform, opacity, filter.",
    },
    {
        "id": "HSL_COLOR_TOKEN_SLOP",
        "pattern": re.compile(r'--[a-z][-a-z0-9]*:\s*hsl\(', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "CSS custom property defined as hsl() function — use channel notation for composability.",
        "command": "Use oklch() or HSL channels: --color: 220 100% 50% (no hsl() wrapper).",
    },
    {
        "id": "OVERSIZED_BORDER_RADIUS_SLOP",
        "pattern": re.compile(r'border-radius:\s*(?:(?!9999)(?:[2-9]\d|[1-9]\d{2,3})px|[3-9]rem)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Excessive border-radius detected — pill/blob shape overuse.",
        "command": "Use modest radius (4-12px). Reserve large radius for intentional pill shapes.",
    },
    {
        "id": "HEIGHT_100VH_SLOP",
        "pattern": re.compile(r'(?<![a-z-])height:\s*100vh', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "height: 100vh clips content on iOS Safari (address bar collapse).",
        "command": "Use min-height: 100vh or min-height: 100dvh instead.",
    },
    {
        "id": "OUTER_GLOW_SLOP",
        "pattern": re.compile(r'box-shadow:\s*0\s+0\s+\d+px', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Outer glow box-shadow (0 0 Npx) detected — cheap AI decoration pattern.",
        "command": "Use directional shadows or inner borders instead of glow effects.",
    },
    {
        "id": "PURE_GRAY_NEUTRAL_SLOP",
        "pattern": re.compile(r'--[a-z][-a-z0-9]*:\s*oklch\([^)]*\s+0\s+', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Pure gray oklch neutral (chroma=0) — no color temperature or tint.",
        "command": "Add slight chroma (0.01-0.03) for warm or cool-tinted neutrals.",
    },
    {
        "id": "VALUE_NAMED_TOKEN_SLOP",
        "pattern": re.compile(r'--[a-z][a-z-]*-\d+\s*:', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Value-embedded CSS token name (--font-size-16) — encode semantics, not values.",
        "command": "Rename to semantic tokens: --font-size-sm, --font-size-base, --color-brand-primary.",
    },
    {
        "id": "PURE_WHITE_BACKGROUND_SLOP",
        "pattern": re.compile(r'(?<!:root\s)background(?:-color)?:\s*(?:#fff(?:fff)?|white)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Pure white (#fff) background — rarely used in premium designs.",
        "command": "Use off-white with subtle warm/cool tint: #fafaf9, oklch(98% 0.005 85).",
    },
    {
        "id": "PURE_BLACK_TEXT_SLOP",
        "pattern": re.compile(r'(?<!:root\s)color:\s*(?:#000(?:000)?|black)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Pure black (#000) text — too harsh, no premium designs use pure black.",
        "command": "Use off-black: #1a1a1a, #0f172a, or oklch(18% 0 0).",
    },
    {
        "id": "GRADIENT_TEXT_CSS_SLOP",
        "pattern": re.compile(r'background-clip:\s*text', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "CSS gradient text (background-clip: text) detected — AI decoration cliche.",
        "command": "Replace with solid color and intentional font weight.",
    },
    {
        "id": "FOCUS_OUTLINE_REMOVED_SLOP",
        "pattern": re.compile(r':focus\s*\{[^}]*outline:\s*(?:none|0)\b', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": ":focus outline removed — keyboard users cannot see focus (WCAG 2.4.7).",
        "command": "Use :focus-visible instead of :focus. Never remove outline entirely.",
        "_custom_check": "focus_outline_removed"
    },
    {
        "id": "TEXT_TRANSFORM_UPPERCASE_SLOP",
        "pattern": re.compile(r'text-transform:\s*uppercase', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "text-transform: uppercase — over-used in AI UIs, reduces readability.",
        "command": "Use uppercase sparingly for short labels (3 words max). Never for paragraphs.",
    },
    {
        "id": "FONT_WEIGHT_TOO_LIGHT_SLOP",
        "pattern": re.compile(r'font-weight:\s*(?:100|200)\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Ultra-light font weight (100/200) — poor readability on most screens.",
        "command": "Use font-weight 300+ for body text. Reserve ultra-light only for large display headings.",
    },
    {
        "id": "FONT_SIZE_ZERO_SLOP",
        "pattern": re.compile(r'font-size:\s*0\b(?!\.)(?!\d)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "font-size: 0 hiding text — use clip/sr-only pattern for screen reader text.",
        "command": "Use .sr-only utility class instead of font-size: 0.",
    },
    {
        "id": "CSS_OVERFLOW_SCROLL_SLOP",
        "pattern": re.compile(r'overflow(?:-x|-y)?:\s*scroll\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "overflow: scroll always shows scrollbar even when not needed.",
        "command": "Use overflow: auto to show scrollbar only when content overflows.",
    },
    {
        "id": "BACKGROUND_ATTACHMENT_FIXED_SLOP",
        "pattern": re.compile(r'background-attachment:\s*fixed', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "background-attachment: fixed — broken on iOS Safari, causes repaint on scroll.",
        "command": "Remove or use JS-based parallax with transform instead.",
    },
    {
        "id": "RESIZE_NONE_SLOP",
        "pattern": re.compile(r'resize:\s*none', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "resize: none on textarea removes user control — accessibility concern.",
        "command": "Allow vertical resize at minimum: resize: vertical.",
    },
    {
        "id": "CSS_VENDOR_PREFIX_SLOP",
        "pattern": re.compile(r'\s-(?:webkit|moz|ms|o)-', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Manual vendor prefix detected — use autoprefixer/PostCSS instead.",
        "command": "Remove manual prefixes and configure autoprefixer in your build toolchain.",
    },
    {
        "id": "FLOAT_LAYOUT_SLOP",
        "pattern": re.compile(r'float:\s*(?:left|right)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "float layout detected — obsolete, use flexbox or grid.",
        "command": "Replace float-based layouts with flexbox (display: flex) or grid.",
    },
    {
        "id": "CSS_OVERFLOW_HIDDEN_BODY_SLOP",
        "pattern": re.compile(r'(?:body|html)\s*\{[^}]*overflow:\s*hidden', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "overflow: hidden on body/html — blocks all page scrolling.",
        "command": "Remove body overflow:hidden or implement proper modal scroll-lock via JS.",
    },
    {
        "id": "ABSOLUTE_FONT_SIZE_BODY_SLOP",
        "pattern": re.compile(r'(?:html|body)\s*\{[^}]*font-size:\s*\d+px', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Absolute px font-size on html/body overrides user browser preferences.",
        "command": "Use font-size: 100% or remove body font-size to respect user settings.",
    },
    {
        "id": "CSS_UNIVERSAL_SELECTOR_SLOP",
        "pattern": re.compile(r'^\*\s*\{', re.MULTILINE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Universal selector (*) reset — performance concern on large DOMs.",
        "command": "Use targeted resets (*, *::before, *::after) with only box-sizing.",
    },
    {
        "id": "FOCUS_VISIBLE_MISSING_SLOP",
        "pattern": re.compile(r':focus\s*\{', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": ":focus styles without :focus-visible pairing — over-triggers on mouse clicks.",
        "command": "Use :focus-visible instead of :focus for ring/outline styles.",
        "_custom_check": "focus_visible_missing"
    },
    {
        "id": "GRADIENT_BORDER_SLOP",
        "pattern": re.compile(r'border-image:\s*linear-gradient', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Gradient border via border-image — AI decoration cliche.",
        "command": "Use a solid accent border or subtle outline. Gradient borders are a cheap effect.",
    },
    {
        "id": "CSS_SCROLL_BEHAVIOR_SLOP",
        "pattern": re.compile(r'scroll-behavior:\s*smooth', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "scroll-behavior: smooth without prefers-reduced-motion guard.",
        "command": "Wrap in @media (prefers-reduced-motion: no-preference) { scroll-behavior: smooth; }",
        "_custom_check": "css_scroll_behavior"
    },
    {
        "id": "CSS_IMPORTANT_ANIMATION_SLOP",
        "pattern": re.compile(r'(?:transition|animation):[^;]*!important', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "!important on transition/animation — cannot be overridden by prefers-reduced-motion.",
        "command": "Remove !important from animation properties to allow accessibility overrides.",
    },
    {
        "id": "CSS_EMPTY_RULE_SLOP",
        "pattern": re.compile(r'\.[a-zA-Z][\w-]*\s*\{\s*\}', re.MULTILINE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Empty CSS rule with no declarations — dead code.",
        "command": "Remove empty CSS classes or add declarations.",
    },
    {
        "id": "STICKY_WITHOUT_TOP_SLOP",
        "pattern": re.compile(r'position:\s*sticky', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "position: sticky without top/left offset — won't stick.",
        "command": "Add top: 0 (or appropriate offset) alongside position: sticky.",
        "_custom_check": "sticky_without_top"
    },
    {
        "id": "SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP",
        "pattern": re.compile(r'scroll-snap-type:', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "scroll-snap-type without scroll-behavior: smooth — abrupt snapping.",
        "command": "Add scroll-behavior: smooth to the scroll container for smooth snap transitions.",
        "_custom_check": "scroll_snap_without_behavior"
    },
    {
        "id": "ASPECT_RATIO_HACK_SLOP",
        "pattern": re.compile(r'padding-(?:top|bottom):\s*(?:56\.25|75|66\.67|33\.33)%', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "Padding-based aspect ratio hack — use aspect-ratio property instead.",
        "command": "Replace padding-top hack with aspect-ratio: 16/9 (or appropriate ratio).",
    },
    {
        "id": "GENERIC_FONT_FAMILY_SLOP",
        "pattern": re.compile(r"font-family:\s*(?:'Inter'|Inter|'Roboto'|Roboto|'Open Sans'|'Montserrat'|Montserrat|'Poppins'|Poppins|'Lato'|Lato)\b", re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Generic 'web default' font family — Inter/Roboto/Poppins are AI defaults.",
        "command": "Choose a distinctive typeface pairing that reflects the brand personality.",
        "_custom_check": "generic_font_family"
    },
    {
        "id": "FONT_DISPLAY_MISSING_SLOP",
        "pattern": re.compile(r'@font-face\s*\{', re.IGNORECASE),
        "tier": "T1",
        "exts": {".css", ".scss", ".less"},
        "description": "@font-face block — verify font-display is specified to avoid FOIT.",
        "command": "Add font-display: swap or font-display: optional inside @font-face.",
        "_custom_check": "font_display_missing"
    },
    {
        "id": "ALPHA_COLOR_ABUSE_SLOP",
        "pattern": re.compile(r'(?:rgba|hsla)\s*\(', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Excessive alpha colors detected — overuse creates muddy compositions.",
        "command": "Limit rgba/hsla to 4 or fewer per file. Use oklch() with / for alpha.",
        "_custom_check": "alpha_color_abuse"
    },
    {
        "id": "GRID_AUTO_FIT_MISSING_SLOP",
        "pattern": re.compile(r'grid-template-columns:\s*repeat\(\s*(?:[2-9]|\d{2,})\s*,', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Fixed-count grid without auto-fit — breaks at narrow viewports.",
        "command": "Use repeat(auto-fit, minmax(min(100%, 280px), 1fr)) for responsive grids.",
        "_custom_check": "grid_auto_fit_missing"
    },
    # ──────────────────────────────────────────────
    # TAILWIND RULES
    # ──────────────────────────────────────────────
    {
        "id": "ARBITRARY_PX_VALUE_SLOP",
        "pattern": re.compile(r'(?:w|h|p|m|gap|space)-\[\d+px\]', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Tailwind arbitrary px value detected — use spacing scale instead.",
        "command": "Use Tailwind's spacing scale (w-8, p-4) or CSS custom property instead of w-[42px].",
    },
    {
        "id": "TAILWIND_V4_GRADIENT_SLOP",
        "pattern": re.compile(r'from-(?:blue|indigo|purple|violet|cyan|sky)-\d+.*?to-(?:blue|indigo|purple|violet|cyan|sky)-\d+', re.IGNORECASE | re.DOTALL),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "Purple-to-blue Tailwind gradient — #1 AI default gradient. Banned.",
        "command": "Remove gradient or use brand-specific color stops. No blue/purple rainbow.",
    },
    {
        "id": "EASE_DEFAULT_SLOP",
        "pattern": re.compile(r'\bease-in-out\b|\bease-in\b|\bease\b(?!-)'),
        "tier": "T2",
        "exts": {".css", ".scss", ".less", ".tsx", ".jsx"},
        "description": "CSS 'ease' easing — generic browser default, use intentional curves.",
        "command": "Use cubic-bezier(0.16, 1, 0.3, 1) (expo-out) or linear() for spring-like motion.",
    },
    {
        "id": "SVG_HARDCODED_FILL_SLOP",
        "pattern": re.compile(r'fill=["\'](?:#000000|#000|white|black)["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "SVG with hardcoded fill color — won't adapt to theme changes.",
        "command": "Use fill='currentColor' so SVG inherits text color from parent.",
    },
    {
        "id": "SCROLL_SMOOTH_NO_MOTION_SLOP",
        "pattern": re.compile(r'\bscroll-smooth\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "scroll-smooth Tailwind class without motion-reduce:scroll-auto.",
        "command": "Add motion-reduce:scroll-auto alongside scroll-smooth for accessibility.",
        "_custom_check": "scroll_smooth_no_motion"
    },
    {
        "id": "NO_SELECT_CONTENT_SLOP",
        "pattern": re.compile(r'\bselect-none\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "select-none (user-select: none) prevents text selection — UX concern.",
        "command": "Only use select-none on UI controls (buttons, sliders), not on content.",
        "_custom_check": "no_select_content"
    },
    {
        "id": "TAILWIND_APPLY_OVERUSE_SLOP",
        "pattern": re.compile(r'@apply\s+[\w\s-]{40,}', re.IGNORECASE),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "@apply with 6+ utility classes — defeats Tailwind's purpose.",
        "command": "Extract to a React component instead of @apply mega-blocks.",
    },
    {
        "id": "OUTLINE_NONE_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*outline-none[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "outline-none/outline-0 without focus-visible: replacement — invisible keyboard focus (WCAG 2.4.7).",
        "command": "Replace outline-none with focus-visible:ring-2.",
        "_custom_check": "outline_none"
    },
    {
        "id": "REDUCED_MOTION_MISSING_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*animate-[^"\']*["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Tailwind animate- class without motion-reduce: variant.",
        "command": "Add motion-reduce:animate-none alongside every animate- class.",
        "_custom_check": "reduced_motion_missing"
    },
    {
        "id": "TAILWIND_FONT_CONFLICT_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "Conflicting Tailwind font-size classes in same className (e.g. text-sm text-lg).",
        "command": "Remove redundant size class.",
        "_custom_check": "tailwind_font_conflict"
    },
    {
        "id": "TAILWIND_WEIGHT_CONFLICT_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*font-(?:bold|medium|semibold|light|thin|normal|extrabold|black)[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "Conflicting Tailwind font-weight classes in same className.",
        "command": "Remove redundant font-weight class.",
        "_custom_check": "tailwind_weight_conflict"
    },
    {
        "id": "TAILWIND_DISPLAY_CONFLICT_SLOP",
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*(?:flex|block|inline)[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "Conflicting Tailwind display classes (flex + hidden, flex + block) in same className.",
        "command": "Remove conflicting display class — only one display class per element.",
        "_custom_check": "tailwind_display_conflict"
    },
    # ──────────────────────────────────────────────
    # TYPESCRIPT / JS RULES
    # ──────────────────────────────────────────────
    {
        "id": "TYPE_ASSERTION_ABUSE_SLOP",
        "pattern": re.compile(r'as\s+unknown\s+as\s+|as\s+any\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".ts"},
        "description": "Unsafe type assertion (as unknown as X, as any) detected.",
        "command": "Use proper generics or type guards instead of unsafe casts.",
    },
    {
        "id": "ASYNC_USEEFFECT_SLOP",
        "pattern": re.compile(r'useEffect\(async\s*\(', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "async useEffect callback — can't cancel, leaks on unmount.",
        "command": "Declare async function inside useEffect body: const load = async () => { ... }; load();",
    },
    {
        "id": "HARDCODED_COLOR_STYLE_SLOP",
        "pattern": re.compile(r'style=\{\{[^}]*(?:#[0-9a-fA-F]{3,6}|rgb\()[^}]*\}\}', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Hardcoded color in inline style — use CSS variables or Tailwind.",
        "command": "Extract color to CSS custom property or Tailwind class.",
    },
    {
        "id": "CONTEXT_VALUE_INLINE_SLOP",
        "pattern": re.compile(r'\.Provider\s+value=\{\{', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Context Provider with inline object value — re-creates object on every render.",
        "command": "Memoize context value: const value = useMemo(() => ({...}), [deps]);",
    },
    {
        "id": "USE_STATE_INIT_SLOP",
        "pattern": re.compile(r'useState\s*\(\s*new\s+(?:Map|Set|Array)\s*\(', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "useState initializer creates new Map/Set/Array on every render.",
        "command": "Use lazy initializer: useState(() => new Map()) to avoid recreating on re-renders.",
    },
    {
        "id": "NON_NULL_ASSERTION_SLOP",
        "pattern": re.compile(r'\w+![.\[]'),
        "tier": "T2",
        "exts": {".tsx", ".ts"},
        "description": "Non-null assertion (!) detected — runtime risk if value is actually null.",
        "command": "Use optional chaining (?.) or explicit null check instead of !.",
    },
    {
        "id": "EVAL_USAGE_SLOP",
        "pattern": re.compile(r'\beval\s*\((?!uate\()'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "eval() detected — critical security and performance issue.",
        "command": "Remove eval(). Parse JSON with JSON.parse, compute with actual functions.",
    },
    {
        "id": "EMPTY_INTERFACE_SLOP",
        "pattern": re.compile(r'interface\s+\w+(?:\s+extends\s+\w+)?\s*\{\s*\}', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".ts"},
        "description": "Empty interface declaration — use type alias or add members.",
        "command": "Replace empty interface with type alias or add required members.",
    },
    {
        "id": "FRAGMENT_SHORTHAND_SLOP",
        "pattern": re.compile(r'<React\.Fragment>'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Verbose React.Fragment syntax — use shorthand <>...</>.",
        "command": "Replace <React.Fragment> with the shorthand fragment syntax <>...</>.",
    },
    {
        "id": "USER_AGENT_SNIFF_SLOP",
        "pattern": re.compile(r'navigator\.userAgent\b'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "navigator.userAgent sniffing — brittle, use feature detection instead.",
        "command": "Use feature detection (if ('geolocation' in navigator)) or CSS @supports.",
    },
    {
        "id": "DEBUGGER_STATEMENT_SLOP",
        "pattern": re.compile(r'\bdebugger\s*;'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "debugger statement in production code — halts execution in DevTools.",
        "command": "Remove all debugger statements before shipping.",
    },
    {
        "id": "PROCESS_BROWSER_DEPRECATED_SLOP",
        "pattern": re.compile(r'\bprocess\.browser\b'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "process.browser is deprecated — use typeof window !== 'undefined'.",
        "command": "Replace process.browser with typeof window !== 'undefined'.",
    },
    {
        "id": "WINDOW_CONFIRM_SLOP",
        "pattern": re.compile(r'\bwindow\.confirm\s*\('),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "window.confirm() blocks the UI thread — use a modal instead.",
        "command": "Replace window.confirm with a custom confirmation modal component.",
    },
    {
        "id": "HARDCODED_DEV_URL_SLOP",
        "pattern": re.compile(r'["\']https?://(?:localhost(?::\d+)?|127\.0\.0\.1(?::\d+)?)(?:[/"\']|$)'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Hardcoded localhost/127.0.0.1 URL in code — breaks in production.",
        "command": "Use environment variables: process.env.NEXT_PUBLIC_API_URL",
    },
    {
        "id": "EMPTY_CATCH_SLOP",
        "pattern": re.compile(r'catch\s*\([^)]*\)\s*\{\s*\}'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Empty catch block silently swallows errors.",
        "command": "Log the error at minimum: catch (err) { console.error(err); }",
    },
    {
        "id": "HARDCODED_SECRET_SLOP",
        "pattern": re.compile(r'["\'](?:sk-|AKIA|ghp_|xoxb-)[A-Za-z0-9_\-]{16,}["\']'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Hardcoded API secret/token detected — CRITICAL security issue.",
        "command": "Move to environment variables immediately. Rotate the exposed secret.",
    },
    {
        "id": "REDUNDANT_BOOL_COMPARE_SLOP",
        "pattern": re.compile(r'===\s*true\b|!==\s*false\b'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Redundant boolean comparison (=== true, !== false) — verbose.",
        "command": "Use the value directly: if (isLoading) instead of if (isLoading === true).",
    },
    {
        "id": "ALERT_USAGE_SLOP",
        "pattern": re.compile(r'\balert\s*\('),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "alert() detected — blocks UI, terrible UX.",
        "command": "Replace alert() with a toast notification or inline error message.",
    },
    {
        "id": "DEPRECATED_FINDDOMNODE_SLOP",
        "pattern": re.compile(r'(?:ReactDOM\.)?findDOMNode\s*\('),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "findDOMNode() is deprecated in React 18 — use ref callback instead.",
        "command": "Replace findDOMNode with useRef() and attach ref directly to the element.",
    },
    {
        "id": "DEPRECATED_CLASS_COMPONENT_SLOP",
        "pattern": re.compile(r'extends\s+(?:React\.)?(?:Component|PureComponent)\b'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Class component detected — migrate to functional component + hooks.",
        "command": "Rewrite as functional component using useState, useEffect, useMemo.",
    },
    {
        "id": "USEEFFECT_EMPTY_DEPS_SLOP",
        "pattern": re.compile(r'useEffect\s*\([^,]{30,},\s*\[\]\)'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Large useEffect with empty deps — likely missing dependencies.",
        "command": "Add all referenced variables to deps array or extract to a custom hook.",
    },
    {
        "id": "USE_CLIENT_DIRECTIVE_SLOP",
        "pattern": re.compile(r"""^['"]use client['"]""", re.MULTILINE),
        "tier": "T2",
        "exts": {".tsx"},
        "description": "'use client' directive — verify this component actually needs client-side rendering.",
        "command": "Move state/effects to a small child component. Keep parent as RSC.",
    },
    {
        "id": "STAR_RATING_SLOP",
        "pattern": re.compile(r'★{5}|⭐{5}'),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Hardcoded 5-star rating emoji — fake social proof, AI cliche.",
        "command": "Use a real rating component with dynamic data or remove.",
    },
    {
        "id": "FAKE_METRIC_SLOP",
        "pattern": re.compile(r'99\.9+%|10x\s+faster|\$\d+[KM]\+\s+saved|\d{1,3}x\s+(?:faster|more|better)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Unverified marketing metric detected (99.9%, 10x faster) — AI credibility filler.",
        "command": "Use real, sourced metrics or remove. Fake metrics erode user trust.",
    },
    {
        "id": "ROUND_NUMBER_SLOP",
        "pattern": re.compile(r'(?<!\d)99%(?!\d)|(?<!\d)100%(?!\.\d)|(?<!\d)\d+\.0+%'),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Suspiciously round metric percentage (99%, 100%, N.00%) — fake precision.",
        "command": "Use real measurements or remove. Round numbers signal fabricated metrics.",
    },
    {
        "id": "STYLE_TAG_IN_JSX_SLOP",
        "pattern": re.compile(r'<style\s*(?:jsx)?\s*(?:global)?\s*>'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "<style> tag in JSX — use CSS modules or Tailwind instead.",
        "command": "Extract styles to .module.css, Tailwind classes, or CSS-in-JS properly.",
    },
    {
        "id": "USE_INDEX_AS_KEY_SLOP",
        "pattern": re.compile(r'\.map\s*\(\s*\([^)]*,\s*(?:index|idx|i)\s*\)\s*=>\s*(?:[^)]*\bkey=\{(?:index|idx|i)\})', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Array index used as React key — breaks reconciliation on reorder.",
        "command": "Use a stable unique identifier (id, slug, UUID) as key.",
    },
    {
        "id": "PROP_SPREADING_SLOP",
        "pattern": re.compile(r'\{\.\.\.(?:props|rest|other)\}'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Prop spreading ({...props}) passes unknown props to DOM elements.",
        "command": "Destructure only the props you need. Avoid blind spreading.",
    },
    {
        "id": "STAR_IMPORT_SLOP",
        "pattern": re.compile(r'import\s*\*\s*as\s+\w+\s+from\s+["\'](?!react)'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Star import (import * as) — defeats tree-shaking.",
        "command": "Use named imports: import { specific, exports } from 'module'.",
    },
    {
        "id": "PROP_TYPES_IN_TS_SLOP",
        "pattern": re.compile(r"import\s+PropTypes\s+from\s+['\"]prop-types['\"]"),
        "tier": "T2",
        "exts": {".tsx", ".ts"},
        "description": "PropTypes import in TypeScript file — TypeScript types replace PropTypes.",
        "command": "Remove prop-types and use TypeScript interfaces/types instead.",
    },
    {
        "id": "DUPLICATE_IMPORT_SLOP",
        "pattern": None,
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Duplicate import from same module detected.",
        "command": "Merge duplicate imports into a single import statement.",
        "_custom_check": "duplicate_import"
    },
    {
        "id": "HARDCODED_TIMEOUT_SLOP",
        "pattern": re.compile(r'set(?:Timeout|Interval)\s*\([^,]+,\s*(\d{4,})'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Hardcoded long timeout/interval value — extract to named constant.",
        "command": "Define as const POLL_INTERVAL_MS = 5000; and reference by name.",
    },
    {
        "id": "DOCUMENT_WRITE_SLOP",
        "pattern": re.compile(r'\bdocument\.write\s*\('),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "document.write() is dangerous and blocks parsing.",
        "command": "Use DOM manipulation APIs (createElement, appendChild) instead.",
    },
    {
        "id": "DOCUMENT_COOKIE_SSR_SLOP",
        "pattern": re.compile(r'\bdocument\.cookie\b'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "document.cookie without typeof window guard — SSR crash risk.",
        "command": "Guard with: if (typeof window !== 'undefined') { document.cookie = ...; }",
        "_custom_check": "document_cookie_ssr"
    },
    {
        "id": "CATCH_CONSOLE_ONLY_SLOP",
        "pattern": re.compile(r'catch\s*\([^)]*\)\s*\{\s*console\.\w+\s*\([^)]*\)\s*;?\s*\}'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Catch block only logs to console — no user feedback or error recovery.",
        "command": "Add user-facing error handling: set error state, show toast, or rethrow.",
    },
    {
        "id": "NO_PASSIVE_SCROLL_LISTENER_SLOP",
        "pattern": re.compile(r"addEventListener\s*\(\s*['\"](?:scroll|touchstart|touchmove|wheel)['\"]"),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Scroll event listener without {passive: true} — janks scroll performance.",
        "command": "Add passive option: addEventListener('scroll', handler, { passive: true })",
    },
    {
        "id": "INNER_HTML_ASSIGN_SLOP",
        "pattern": re.compile(r'\.innerHTML\s*[+]?=\s*'),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "innerHTML assignment — XSS risk without sanitization.",
        "command": "Use DOMPurify.sanitize() before assigning innerHTML, or use textContent.",
        "_custom_check": "inner_html_assign"
    },
    {
        "id": "LOCALSTORAGE_SENSITIVE_SLOP",
        "pattern": re.compile(r"localStorage\.setItem\s*\(\s*['\"](?:token|password|secret|auth|jwt)['\"]", re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Sensitive data stored in localStorage — vulnerable to XSS.",
        "command": "Use httpOnly cookies for tokens/secrets. Never store credentials in localStorage.",
    },
    {
        "id": "OPEN_REDIRECT_SLOP",
        "pattern": re.compile(r'(?:window\.)?location(?:\.href)?\s*=\s*[a-zA-Z_]\w*\s*(?:[+;]|$)', re.MULTILINE),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Potential open redirect — location.href set from variable without validation.",
        "command": "Validate redirect URLs against an allowlist before assigning to location.href.",
    },
    {
        "id": "NAVIGATOR_SSR_SLOP",
        "pattern": re.compile(r'\bnavigator\.\w+'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "navigator.* access without typeof window guard — SSR crash risk.",
        "command": "Guard with: if (typeof window !== 'undefined') { ... navigator.xxx }",
        "_custom_check": "navigator_ssr"
    },
    {
        "id": "POSTMESSAGE_ORIGIN_MISSING_SLOP",
        "pattern": re.compile(r"addEventListener\s*\(\s*['\"]message['\"]"),
        "tier": "T1",
        "exts": {".tsx", ".ts", ".js"},
        "description": "postMessage listener without event.origin validation — XSS/phishing risk.",
        "command": "Add origin check: if (event.origin !== 'https://trusted.example.com') return;",
        "_custom_check": "postmessage_origin_missing"
    },
    {
        "id": "LOCALSTORAGE_SSR_SLOP",
        "pattern": re.compile(r'\blocalStorage\b'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "localStorage access without typeof window guard — SSR crash risk.",
        "command": "Guard with: if (typeof window !== 'undefined') { localStorage.xxx }",
        "_custom_check": "localstorage_ssr"
    },
    {
        "id": "WINDOW_OBJECT_SSR_SLOP",
        "pattern": re.compile(r'\bwindow\.\w+'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "window.* access without typeof window guard — SSR crash risk.",
        "command": "Guard with: if (typeof window !== 'undefined') { window.xxx }",
        "_custom_check": "window_object_ssr"
    },
    # ──────────────────────────────────────────────
    # HTML / SEMANTIC RULES
    # ──────────────────────────────────────────────
    {
        "id": "UNSPLASH_URL_SLOP",
        "pattern": re.compile(r'images\.unsplash\.com', re.IGNORECASE),
        "tier": "T1",
        "exts": _ALL_FE_EXTS,
        "description": "Direct Unsplash image URL detected — hotlinking, unreliable in production.",
        "command": "Use picsum.photos/seed/{name}/800/600 or download and self-host images.",
    },
    {
        "id": "TITLE_CASE_HEADER_SLOP",
        "pattern": re.compile(r'<h[123][^>]*>\s*(?:[A-Z][a-z]+\s+){3,}[A-Z][a-z]+\s*</h[123]>'),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Title Case heading detected — reads as UI template, not intentional copy.",
        "command": "Use sentence case for headings. Reserve Title Case for proper nouns.",
    },
    {
        "id": "MISSING_META_DESCRIPTION_SLOP",
        "pattern": re.compile(r'<head\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".html"},
        "description": "<head> present — verify a <meta name='description'> tag exists.",
        "command": "Add <meta name='description' content='...'> for SEO.",
        "_custom_check": "missing_meta_description"
    },
    {
        "id": "SKIP_TO_CONTENT_MISSING_SLOP",
        "pattern": re.compile(r'<nav\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".html"},
        "description": "Navigation present without skip-to-content link — keyboard accessibility.",
        "command": "Add <a href='#main-content' class='sr-only focus:not-sr-only'>Skip to content</a> as first element.",
        "_custom_check": "skip_to_content_missing"
    },
    {
        "id": "MISSING_FAVICON_SLOP",
        "pattern": re.compile(r'<head\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".html"},
        "description": "<head> without rel='icon' favicon link.",
        "command": "Add <link rel='icon' href='/favicon.ico'> to <head>.",
        "_custom_check": "missing_favicon"
    },
    {
        "id": "MISSING_LANG_SLOP",
        "pattern": re.compile(r'<html\b(?![^>]*\blang=)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".html"},
        "description": "<html> without lang attribute — screen readers can't determine language.",
        "command": "Add lang='en' (or appropriate language code) to the <html> tag.",
    },
    {
        "id": "IMG_ALT_MISSING_SLOP",
        "pattern": re.compile(r'<img\b(?![^>]*\balt=)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<img> without alt attribute — WCAG 1.1.1 failure.",
        "command": "Add meaningful alt text or alt='' for decorative images.",
    },
    {
        "id": "IMG_MISSING_DIMENSIONS_SLOP",
        "pattern": re.compile(r'<img\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<img> without explicit width and height — causes layout shift (CLS).",
        "command": "Add width and height attributes to all <img> tags.",
        "_custom_check": "img_missing_dimensions"
    },
    {
        "id": "MISSING_TABULAR_NUMS_SLOP",
        "pattern": re.compile(r'<table\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<table> without tabular-nums — numbers shift alignment when they change.",
        "command": "Add font-variant-numeric: tabular-nums to the table or use Tailwind tabular-nums.",
        "_custom_check": "missing_tabular_nums"
    },
    {
        "id": "PLACEHOLDER_ONLY_INPUT_SLOP",
        "pattern": re.compile(r'<input\b[^>]*\bplaceholder=', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<input> with placeholder but no accessible label (id/aria-label) — WCAG fail.",
        "command": "Add a <label htmlFor='id'> or aria-label to identify the input.",
        "_custom_check": "placeholder_only_input"
    },
    {
        "id": "SRCSET_MISSING_SLOP",
        "pattern": re.compile(r'<img\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<img> without srcset — serves same large image to all viewports.",
        "command": "Add srcset with multiple resolutions or use next/image for automatic optimization.",
        "_custom_check": "srcset_missing"
    },
    {
        "id": "ANCHOR_TARGET_BLANK_SLOP",
        "pattern": re.compile(r'target=["\']_blank["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "target='_blank' without rel='noopener noreferrer' — security risk.",
        "command": "Add rel='noopener noreferrer' to all target='_blank' links.",
        "_custom_check": "anchor_target_blank"
    },
    {
        "id": "DANGEROUS_HTML_SLOP",
        "pattern": re.compile(r'dangerouslySetInnerHTML', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "dangerouslySetInnerHTML without DOMPurify — XSS risk.",
        "command": "Sanitize with DOMPurify.sanitize() before passing to dangerouslySetInnerHTML.",
        "_custom_check": "dangerous_html"
    },
    {
        "id": "FORM_NO_SUBMIT_SLOP",
        "pattern": re.compile(r'<form\b(?![^>]*(?:onSubmit|action)=)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<form> without onSubmit handler or action — form does nothing.",
        "command": "Add onSubmit handler with e.preventDefault() or server action attribute.",
    },
    {
        "id": "INPUT_AUTOCOMPLETE_MISSING_SLOP",
        "pattern": re.compile(r'<input\s[^>]*type=["\'](?:email|password)["\'](?![^>]*(?:autocomplete|autoComplete)=)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Email/password input without autocomplete attribute.",
        "command": "Add autocomplete='email' or autocomplete='current-password' for password managers.",
    },
    {
        "id": "ICON_ARIA_MISSING_SLOP",
        "pattern": re.compile(r'<(?:svg|i)\s[^>]*class[^>]*>', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Icon (SVG/i) element — verify aria-label or aria-hidden is present.",
        "command": "Add aria-hidden='true' for decorative icons, aria-label for meaningful ones.",
        "_custom_check": "icon_aria_missing"
    },
    {
        "id": "SVG_WITHOUT_VIEWBOX_SLOP",
        "pattern": re.compile(r'<svg\b(?![^>]*viewBox=)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<svg> without viewBox — won't scale properly.",
        "command": "Add viewBox='0 0 24 24' (or appropriate dimensions) to all SVG elements.",
    },
    {
        "id": "ICON_ONLY_BUTTON_SLOP",
        "pattern": re.compile(r'<button\b[^>]*>(?:\s*<(?:svg|i)\b[^>]*>)', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": "Icon-only button without aria-label — inaccessible to screen readers.",
        "command": "Add aria-label='Descriptive action' to icon-only buttons.",
        "_custom_check": "icon_only_button"
    },
    {
        "id": "TOUCH_TARGET_SLOP",
        "pattern": re.compile(r'<button\b[^>]*className=["\'][^"\']*(?:w-[1-6]|h-[1-6])\b[^"\']*["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Button with small w-/h- class — may be below 44px touch target (WCAG 2.5.5).",
        "command": "Ensure all touch targets are at least 44x44px (w-11 h-11 minimum).",
    },
    {
        "id": "NEXT_IMAGE_RAW_SLOP",
        "pattern": re.compile(r'<img\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "<img> tag in a Next.js file — use next/image for automatic optimization.",
        "command": "Import Image from 'next/image' and replace <img> with <Image width={} height={}>.",
        "_custom_check": "next_image_raw"
    },
    # ──────────────────────────────────────────────
    # REACT PATTERNS
    # ──────────────────────────────────────────────
    {
        "id": "MISSING_KEY_PROP_SLOP",
        "pattern": re.compile(r'\.map\s*\('),
        "tier": "T1",
        "exts": {".tsx", ".jsx"},
        "description": ".map() call returning JSX — verify each element has a key prop.",
        "command": "Add key={item.id} to each element returned from .map().",
        "_custom_check": "missing_key_prop"
    },
    {
        "id": "FRAMER_NO_REDUCED_MOTION_SLOP",
        "pattern": re.compile(r"from ['\"]framer-motion['\"]"),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "framer-motion import without useReducedMotion hook — ignores user motion preferences.",
        "command": "Import useReducedMotion and conditionally disable animations.",
        "_custom_check": "framer_no_reduced_motion"
    },
    {
        "id": "LAZY_WITHOUT_SUSPENSE_SLOP",
        "pattern": re.compile(r'(?:React\.)?lazy\s*\('),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".js"},
        "description": "React.lazy() without nearby Suspense boundary — runtime error.",
        "command": "Wrap lazy-loaded component with <Suspense fallback={<Loading />}>.",
        "_custom_check": "lazy_without_suspense"
    },
    {
        "id": "MEDIA_AUTOPLAY_SLOP",
        "pattern": re.compile(r'<(?:video|audio)\b[^>]*autoPlay', re.IGNORECASE),
        "tier": "T1",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "autoPlay media without muted attribute — browsers block autoplaying with sound.",
        "command": "Add muted attribute to autoPlay videos. Autoplaying audio is banned.",
        "_custom_check": "media_autoplay"
    },
    {
        "id": "SELECT_NO_LABEL_SLOP",
        "pattern": re.compile(r'<select\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "<select> without accessible label — WCAG 1.3.1 failure.",
        "command": "Add <label htmlFor='id'> or aria-label attribute to all <select> elements.",
        "_custom_check": "select_no_label"
    },
    # ──────────────────────────────────────────────
    # CONTENT / COPY RULES
    # ──────────────────────────────────────────────
    {
        "id": "SAME_DATE_REPEAT_SLOP",
        "pattern": re.compile(r'(\d{4}-\d{2}-\d{2})(?:.*\1){2,}', re.DOTALL),
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Same ISO date repeated 3+ times — hardcoded placeholder date.",
        "command": "Extract the date to a constant or use dynamic date formatting.",
    },
    {
        "id": "HARDCODED_COPYRIGHT_YEAR_SLOP",
        "pattern": re.compile(r'©\s*20\d{2}|&copy;\s*20\d{2}', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Hardcoded copyright year — will be stale next year.",
        "command": "Use {new Date().getFullYear()} for dynamic copyright year.",
        "_custom_check": "hardcoded_copyright_year"
    },
    {
        "id": "EMOJI_BULLET_LIST_SLOP",
        "pattern": re.compile(r'(?:^|\n)\s*[\u2600-\u27FF\U0001F000-\U0001FFFF].*(?:\n\s*[\u2600-\u27FF\U0001F000-\U0001FFFF].*){2,}'),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".md"},
        "description": "Emoji-as-bullets list detected (3+ lines) — AI content pattern.",
        "command": "Use semantic <ul>/<li> elements with proper icons or remove emoji bullets.",
    },
    {
        "id": "TESTIMONIAL_GRID_SLOP",
        "pattern": re.compile(r'(?:\"[^\"]{20,}\".*?[\u2014\u2013-]\s*\w+.*?(?:\n|$)){3,}', re.DOTALL),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "Testimonial grid pattern (3+ quote — Name blocks) — generic AI social proof.",
        "command": "Use varied testimonial formats: video quotes, inline stats, or real customer logos.",
    },
    {
        "id": "PRICING_TABLE_SLOP",
        "pattern": None,
        "_custom_check": "pricing_table",
        "tier": "T3",
        "exts": {".tsx", ".jsx", ".html"},
        "description": "3-tier pricing table detected (Free/Pro/Enterprise) — #1 AI landing page cliche.",
        "command": "Redesign pricing with varied layouts: comparison table, slider, or interactive calculator.",
    },
    {
        "id": "VERBOSE_HANDLER_NAME_SLOP",
        "pattern": re.compile(r'\bhandle(?!Submit\b|Change\b|Click\b|Focus\b|Blur\b|Key)[A-Z][a-z]+(?:Click|Change|Submit|Press)\b'),
        "tier": "T2",
        "exts": {".tsx", ".ts", ".js"},
        "description": "Verbose event handler name (handleXxxClick) — redundant suffix.",
        "command": "Use action-focused names: onSave, onDelete, submitOrder instead of handleSaveClick.",
    },
    # ──────────────────────────────────────────────
    # LAYOUT / COMPONENT RULES
    # ──────────────────────────────────────────────
    {
        "id": "THREE_EQUAL_COLUMN_SLOP",
        "pattern": re.compile(r'grid-cols-3\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Uniform 3-column grid — classic AI feature-grid layout.",
        "command": "Break the 3-col monotony: vary column spans, use bento layout, or asymmetric grid.",
        "_custom_check": "three_equal_column"
    },
    {
        "id": "FONT_WEIGHT_EXTREMES_SLOP",
        "pattern": re.compile(r'\bfont-bold\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Only bold/normal weight usage without intermediate weights — poor typographic hierarchy.",
        "command": "Add font-medium or font-semibold for intermediate hierarchy levels.",
        "_custom_check": "font_weight_extremes"
    },
    {
        "id": "MISSING_LOADING_STATE_SLOP",
        "pattern": re.compile(r'\buseQuery\b'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "useQuery without isLoading handling — blank screen during fetch.",
        "command": "Handle loading state: const { data, isLoading } = useQuery(...); if (isLoading) return <Skeleton/>",
        "_custom_check": "missing_loading_state"
    },
    {
        "id": "MISSING_ERROR_STATE_SLOP",
        "pattern": re.compile(r'\buseQuery\b'),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "useQuery without isError handling — silent failure on network errors.",
        "command": "Handle error state: const { data, isLoading, isError } = useQuery(...); if (isError) return <Error/>",
        "_custom_check": "missing_error_state"
    },
    {
        "id": "ACCORDION_FAQ_SLOP",
        "pattern": re.compile(r'\bAccordion\b', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Accordion used as FAQ section — #2 AI landing page cliche.",
        "command": "Replace FAQ accordion with a search box, contextual help tooltips, or docs link.",
        "_custom_check": "accordion_faq"
    },
    {
        "id": "DARK_MODE_TOGGLE_SLOP",
        "pattern": re.compile(r'(?:ThemeToggle|toggleDarkMode|DarkModeToggle|darkMode)', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Dark mode toggle without respecting prefers-color-scheme.",
        "command": "Use CSS prefers-color-scheme as the default, with user toggle as override.",
        "_custom_check": "dark_mode_toggle"
    },
    {
        "id": "CENTERED_PARAGRAPH_SLOP",
        "pattern": re.compile(r'<p\b[^>]*className=["\'][^"\']*text-center[^"\']*["\'][^>]*>[^<]{30,}', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Centered paragraph text — readability degrades beyond 2 lines.",
        "command": "Left-align body text. Reserve text-center for headings and short captions only.",
    },
    {
        "id": "MODAL_NO_ARIA_SLOP",
        "pattern": re.compile(r'(?:modal|Modal)(?![^"]*role=["\']dialog["\'])', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx"},
        "description": "Modal component without role='dialog' and ARIA attributes.",
        "command": "Add role='dialog', aria-modal='true', and aria-labelledby to modal containers.",
        "_custom_check": "modal_no_aria"
    },
    {
        "id": "FLEXBOX_PERCENTAGE_MATH_SLOP",
        "pattern": re.compile(r'width:\s*(?:33\.33|25|16\.67|12\.5|20)%'),
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Percentage-based flex column width — use grid with auto-fit instead.",
        "command": "Replace manual percentage math with CSS grid: grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))",
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
    fpath = str(filepath.resolve())

    if ext in {".tsx", ".jsx", ".js", ".ts"}:
        state = {
            "div_count": 0, "semantic_count": 0, "nested_ternaries": 0,
            "cards": 0, "charts": 0,
            # Deep prop drilling detection
            "prop_pass_depth": 0,  # max depth of a prop passed through components
            "prop_names_seen": {},  # prop name -> list of component names where it appears
            # useState for animation detection
            "usestate_for_animation": False,
            # Identical sibling components (e.g., 4 KPI cards in a row)
            "sibling_components": {},  # parent_id -> list of child component names
            # Styled-component nesting depth
            "styled_nesting_depth": 0,
        }

        def _node_text(node) -> str:
            try:
                return node.text.decode("utf-8", errors="ignore")
            except AttributeError:
                return str(node.text)

        def walk(node, depth=0):
            if node.type in ("jsx_element", "jsx_self_closing_element"):
                open_tag = node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
                if open_tag:
                    name_node = open_tag.child_by_field_name("name")
                    if name_node:
                        tag_name = _node_text(name_node)

                        if tag_name == "div":
                            state["div_count"] += 1
                        elif tag_name in {"nav", "main", "article", "section", "aside", "header", "footer"}:
                            state["semantic_count"] += 1

                        # Detect Dashboard Slop
                        if "Card" in tag_name or "Stat" in tag_name or "Metric" in tag_name:
                            state["cards"] += 1
                        elif "Chart" in tag_name or "Graph" in tag_name or "Activity" in tag_name:
                            state["charts"] += 1

                        # Track sibling component repetition for layout-level slop
                        parent_id = id(node.parent) if node.parent else 0
                        if tag_name[0:1].isupper():  # React component (capitalized)
                            state["sibling_components"].setdefault(parent_id, []).append(tag_name)

                        # Detect deep prop drilling: props passed through with same name
                        for attr in (open_tag.children or []):
                            if attr.type == "jsx_attribute":
                                attr_name_node = attr.child_by_field_name("name")
                                if attr_name_node:
                                    attr_name = _node_text(attr_name_node)
                                    state["prop_names_seen"].setdefault(attr_name, set()).add(tag_name)

            elif node.type == "ternary_expression":
                for child in node.children:
                    if child.type == "ternary_expression":
                        state["nested_ternaries"] += 1

            # Detect useState used for animation values (bad pattern)
            elif node.type == "lexical_declaration":
                text = _node_text(node)
                if "useState" in text:
                    animation_signals = ["opacity", "scale", "translate", "rotate", "transform",
                                          "position", "top", "left", "right", "bottom",
                                          "animat", "transit", "x", "y"]
                    text_lower = text.lower()
                    for sig in animation_signals:
                        if sig in text_lower and "useState" in text:
                            state["usestate_for_animation"] = True
                            break

            # Detect deeply nested styled-components tagged templates
            elif node.type == "tagged_template_expression":
                tag = node.child_by_field_name("function")
                if tag:
                    tag_text = _node_text(tag)
                    if "styled" in tag_text or "css" in tag_text:
                        # Count nesting depth of CSS selectors within
                        tmpl = node.child_by_field_name("arguments") or node
                        nesting = _node_text(tmpl).count("{")
                        if nesting > state["styled_nesting_depth"]:
                            state["styled_nesting_depth"] = nesting

            for child in node.children:
                walk(child, depth + 1)

        walk(tree.root_node)

        if state["div_count"] > 20 and state["semantic_count"] == 0:
            issues.append({
                "id": "DIV_SOUP_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state['div_count']} divs, 0 semantic elements)",
                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>."
            })

        if state["nested_ternaries"] >= 2:
            issues.append({
                "id": "NESTED_TERNARY_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state['nested_ternaries']} nested ternaries found)",
                "command": "Extract nested ternaries into named variables or early returns for clarity."
            })

        if state["cards"] >= 3 and state["charts"] >= 1:
            issues.append({
                "id": "HERO_DASHBOARD_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Hero metric dashboard pattern detected via AST ({state['cards']} cards, {state['charts']} charts) — cliché AI layout.",
                "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow."
            })

        # ── AST: Deep prop drilling ──
        drilled_props = [
            name for name, components in state["prop_names_seen"].items()
            if len(components) >= 4 and name not in {"className", "children", "key", "id", "style", "ref", "onClick", "onChange"}
        ]
        if drilled_props:
            sample = ", ".join(sorted(drilled_props)[:5])
            issues.append({
                "id": "PROP_DRILLING_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Deep prop drilling detected via AST — prop(s) '{sample}' passed through 4+ components.",
                "command": "Extract deeply drilled props into React Context, Zustand store, or composition pattern to reduce coupling."
            })

        # ── AST: useState for animation values ──
        if state["usestate_for_animation"]:
            issues.append({
                "id": "ANIMATE_STATE_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": "React useState used for animation values — causes re-renders on every frame.",
                "command": "Use CSS transitions/animations, Framer Motion, or useRef for animation state. Never drive 60fps animations through React state."
            })

        # ── AST: Identical sibling components (generic layout slop) ──
        for parent_id, children in state["sibling_components"].items():
            if len(children) >= 4:
                from collections import Counter
                counts = Counter(children)
                for comp_name, count in counts.items():
                    if count >= 4:
                        issues.append({
                            "id": "IDENTICAL_SIBLINGS_SLOP",
                            "file": fpath,
                            "tier": "T3",
                            "issue": f"Generic layout pattern detected via AST: {count} identical <{comp_name}/> siblings — dashboard/feature-grid slop.",
                            "command": f"Vary the {comp_name} instances (different sizes, spans, emphasis) or replace with asymmetric layout. Identical cards = AI fingerprint."
                        })
                        break  # One issue per parent

        # ── AST: Deeply nested styled-components ──
        if state["styled_nesting_depth"] >= 5:
            issues.append({
                "id": "STYLED_NESTING_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Deeply nested styled-component selectors detected ({state['styled_nesting_depth']} levels) — specificity war.",
                "command": "Flatten CSS nesting. Use component composition instead of deeply nested selectors."
            })

    return issues


def _analyze_component_layout(filepath: Path, content: str, ext: str) -> list[dict]:
    """Component-level heuristic analysis for layout-level slop detection.

    Analyzes entire file structure, not individual patterns, to detect:
    - Generic dashboard layouts (N identical KPI cards + chart)
    - Feature-grid slop (3-column identical items)
    - Pricing table clichés
    - Hero-section-heavy pages
    - Component files with zero interactivity
    """
    issues = []
    fpath = str(filepath.resolve())

    if ext not in {".tsx", ".jsx"}:
        return issues

    lines = content.splitlines()
    file_len = len(lines)

    # ── Heuristic 1: KPI Card Dashboard Pattern ──
    # Look for repeated card-like structures with metrics/numbers
    card_patterns = re.findall(
        r'(?:<(?:\w+Card|\w+Stat|\w+Metric|\w+KPI)\b[^>]*>)',
        content, re.IGNORECASE
    )
    chart_patterns = re.findall(
        r'(?:<(?:\w*Chart|\w*Graph|LineChart|BarChart|PieChart|AreaChart|ResponsiveContainer)\b)',
        content, re.IGNORECASE
    )
    if len(card_patterns) >= 4 and len(chart_patterns) >= 1:
        issues.append({
            "id": "DASHBOARD_LAYOUT_SLOP",
            "file": fpath,
            "tier": "T3",
            "issue": f"Generic dashboard layout: {len(card_patterns)} KPI/stat cards + {len(chart_patterns)} chart(s) — classic AI dashboard slop.",
            "command": "Replace identical card grid with varied sizes (span-2 hero metric, inline sparklines). Weave data into contextual narrative."
        })

    # ── Heuristic 2: Feature Grid Slop (identical feature items) ──
    # Detect 3+ identical JSX blocks with icon + heading + description pattern
    feature_block = re.findall(
        r'(?:<(?:div|section|article|li)\s[^>]*>[\s\S]{30,300}?'
        r'(?:<\w+Icon|<Icon\b|icon=|<svg\b)[\s\S]{10,200}?'
        r'(?:<h[23456]|<(?:Title|Heading|CardTitle))'
        r'[\s\S]{10,200}?'
        r'(?:<p\b|<(?:Description|Text|CardDescription))'
        r')',
        content, re.IGNORECASE
    )
    if len(feature_block) >= 3:
        issues.append({
            "id": "FEATURE_GRID_SLOP",
            "file": fpath,
            "tier": "T3",
            "issue": f"Feature grid slop: {len(feature_block)} identical icon+heading+description blocks — generic SaaS landing pattern.",
            "command": "Vary feature presentations (alternate image/text, use different card sizes, stagger layouts). Break the 3-column monotony."
        })

    # ── Heuristic 3: Pricing Table Cliché ──
    pricing_signals = len(re.findall(r'(?:\$\d+|/mo(?:nth)?|/yr|/year|popular|recommended|enterprise|pro|starter|basic|premium)', content, re.IGNORECASE))
    pricing_cards = len(re.findall(r'(?:PricingCard|PricingTier|PricingPlan|price-card)', content, re.IGNORECASE))
    if pricing_signals >= 6 or pricing_cards >= 3:
        issues.append({
            "id": "PRICING_TABLE_SLOP",
            "file": fpath,
            "tier": "T3",
            "issue": "Pricing table cliché detected — 3-column pricing grid with 'Popular' badge is the #1 AI SaaS template.",
            "command": "Design pricing as a comparison flow, slider, or interactive calculator. Vary card sizes. Make the recommended plan visually dominant, not just badged."
        })

    # ── Heuristic 4: Zero Interactivity File ──
    has_interactivity = bool(re.search(
        r'(?:onClick|onChange|onSubmit|onPress|onFocus|onBlur|onKeyDown|onMouseEnter|onHover|hover:|focus:|active:|useState|useReducer|motion\.|animate)',
        content
    ))
    jsx_count = len(re.findall(r'<[A-Z]\w+', content))
    if not has_interactivity and jsx_count >= 5 and file_len > 50:
        issues.append({
            "id": "STATIC_COMPONENT_SLOP",
            "file": fpath,
            "tier": "T2",
            "issue": f"Static component detected: {jsx_count} JSX elements but zero interactivity (no handlers, no hover/focus, no animation).",
            "command": "Add hover states, transitions, or micro-interactions. Static pages feel dead — every component should respond to user input."
        })

    # ── Heuristic 5: Hero Section Heavy Page ──
    hero_count = len(re.findall(r'(?:hero|Hero|HERO)', content))
    section_count = len(re.findall(r'<(?:section|Section)\b', content, re.IGNORECASE))
    if hero_count >= 2 and section_count <= 3:
        issues.append({
            "id": "HERO_HEAVY_SLOP",
            "file": fpath,
            "tier": "T2",
            "issue": "Hero-section-heavy page — multiple hero blocks without enough content sections.",
            "command": "A page needs one hero at most. Replace additional heroes with content sections, testimonials, or data-driven blocks."
        })

    # ── Heuristic 6: Testimonial Grid Slop ──
    testimonial_signals = len(re.findall(
        r'(?:testimonial|review|quote|avatar.*?(?:name|title)|rating|stars?.*?(?:5|five))',
        content, re.IGNORECASE
    ))
    if testimonial_signals >= 6:
        issues.append({
            "id": "TESTIMONIAL_GRID_SLOP",
            "file": fpath,
            "tier": "T2",
            "issue": "Generic testimonial grid detected — avatar + quote + name pattern repeated.",
            "command": "Use varied testimonial layouts: full-width quotes, video testimonials, inline social proof, or rotating carousel with real data."
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

    # Component-level layout heuristics (runs regardless of AST)
    layout_issues = _analyze_component_layout(filepath, content, ext)
    issues.extend(layout_issues)

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
                    "id": rule["id"],
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
                        "id": rule["id"],
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
                        "id": rule["id"],
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
                        "id": rule["id"],
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
                        "id": rule["id"],
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
                    "id": rule["id"],
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
                        "id": rule["id"],
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
                    "id": rule["id"],
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
                            "id": rule["id"],
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
                    "id": rule["id"],
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
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} `{state_var}` appears unused.",
                        "command": rule["command"]
                    })
                    break  # Flag once per file
            continue

        # ── New custom check handlers ─────────────────────────────────────
        if custom == "video_no_captions":
            if re.search(r'<video\b', content, re.IGNORECASE) and not re.search(r'<track\b', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "focus_outline_removed":
            # :focus { outline: none } or :focus { outline: 0 }
            if re.search(r':focus\s*\{[^}]*outline:\s*(?:none|0)\b', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "focus_visible_missing":
            if re.search(r':focus\s*\{', content, re.IGNORECASE) and not re.search(r':focus-visible\s*\{', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "css_scroll_behavior":
            if re.search(r'scroll-behavior:\s*smooth', content, re.IGNORECASE) and not re.search(r'prefers-reduced-motion', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "sticky_without_top":
            for block_m in re.finditer(r'position:\s*sticky[^}]*', content, re.IGNORECASE | re.DOTALL):
                block = block_m.group(0)
                if not re.search(r'\btop\s*:', block, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "scroll_snap_without_behavior":
            if re.search(r'scroll-snap-type:', content, re.IGNORECASE) and not re.search(r'scroll-behavior:', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "generic_font_family":
            AI_FONTS = re.compile(r"font-family:\s*(?:'Inter'|Inter|'Roboto'|Roboto|'Open Sans'|Open Sans|'Montserrat'|Montserrat|'Poppins'|Poppins|'Lato'|Lato)", re.IGNORECASE)
            if AI_FONTS.search(content) and not re.search(r'-apple-system', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "font_display_missing":
            for ff_m in re.finditer(r'@font-face\s*\{([^}]*)\}', content, re.IGNORECASE | re.DOTALL):
                if 'font-display' not in ff_m.group(1):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "alpha_color_abuse":
            count = len(re.findall(r'(?:rgba|hsla)\s*\(', content, re.IGNORECASE))
            if count >= 5:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": f"{rule['description']} ({count} instances found)", "command": rule["command"]})
            continue

        if custom == "grid_auto_fit_missing":
            if re.search(r'grid-template-columns:\s*repeat\(\s*(?:[2-9]|\d{2,})\s*,', content, re.IGNORECASE):
                if not re.search(r'auto-fit|auto-fill', content, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "scroll_smooth_no_motion":
            if re.search(r'\bscroll-smooth\b', content) and not re.search(r'motion-reduce:scroll-auto', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "no_select_content":
            if re.search(r'\bselect-none\b', content):
                # Flag if used on non-button elements (not inside <button>)
                # Simple heuristic: flag if it appears in className on a non-button
                if re.search(r'<(?!button)(?:[a-z][a-z0-9]*)(?:\s[^>]*)?\bclassName=[^>]*select-none', content, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "outline_none":
            for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']*outline-none[^"\']*)["\']', content, re.IGNORECASE):
                cls = m_cls.group(1)
                if 'focus-visible:' not in cls and 'focus:ring' not in cls:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "reduced_motion_missing":
            for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']*animate-[^"\']*)["\']', content, re.IGNORECASE):
                cls = m_cls.group(1)
                if 'motion-reduce:' not in cls:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "tailwind_font_conflict":
            SIZE_CLASSES = ['text-xs', 'text-sm', 'text-base', 'text-lg', 'text-xl',
                            'text-2xl', 'text-3xl', 'text-4xl', 'text-5xl', 'text-6xl', 'text-7xl', 'text-8xl', 'text-9xl']
            for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE):
                cls = m_cls.group(1)
                found = [s for s in SIZE_CLASSES if re.search(r'(?<![a-z-])' + re.escape(s) + r'(?![a-zA-Z0-9-])', cls)]
                if len(found) >= 2:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": f"{rule['description']} Found: {', '.join(found)}", "command": rule["command"]})
                    break
            continue

        if custom == "tailwind_weight_conflict":
            WEIGHT_CLASSES = ['font-thin', 'font-extralight', 'font-light', 'font-normal',
                               'font-medium', 'font-semibold', 'font-bold', 'font-extrabold', 'font-black']
            for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE):
                cls = m_cls.group(1)
                found = [w for w in WEIGHT_CLASSES if re.search(r'(?<![a-z-])' + re.escape(w) + r'(?![a-zA-Z0-9-])', cls)]
                if len(found) >= 2:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": f"{rule['description']} Found: {', '.join(found)}", "command": rule["command"]})
                    break
            continue

        if custom == "tailwind_display_conflict":
            DISPLAY_CLASSES = ['flex', 'block', 'inline-flex', 'inline-block', 'inline', 'hidden', 'grid', 'contents']
            for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE):
                cls = m_cls.group(1)
                found = [d for d in DISPLAY_CLASSES if re.search(r'(?<![a-z-])' + re.escape(d) + r'(?![a-zA-Z0-9-])', cls)]
                # Conflict: flex+hidden, flex+block, etc.
                if ('hidden' in found and ('flex' in found or 'block' in found or 'grid' in found)) or \
                   ('flex' in found and 'block' in found) or \
                   ('grid' in found and 'block' in found):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": f"{rule['description']} Found: {', '.join(found)}", "command": rule["command"]})
                    break
            continue

        if custom == "missing_meta_description":
            if re.search(r'<head\b', content, re.IGNORECASE) and not re.search(r'<meta\s[^>]*name=["\']description["\']', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "skip_to_content_missing":
            if re.search(r'<nav\b', content, re.IGNORECASE) and re.search(r'<main\b', content, re.IGNORECASE):
                if not re.search(r'href=["\']#', content, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "missing_favicon":
            if re.search(r'<head\b', content, re.IGNORECASE) and not re.search(r'rel=["\'](?:shortcut icon|icon)["\']', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "img_missing_dimensions":
            for m_img in re.finditer(r'<img\b[^>]*>', content, re.IGNORECASE):
                img_tag = m_img.group(0)
                has_width = re.search(r'\bwidth=', img_tag, re.IGNORECASE)
                has_height = re.search(r'\bheight=', img_tag, re.IGNORECASE)
                if not (has_width and has_height):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "missing_tabular_nums":
            if re.search(r'<table\b', content, re.IGNORECASE) and not re.search(r'tabular-nums', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "placeholder_only_input":
            for m_inp in re.finditer(r'<input\b[^>]*>', content, re.IGNORECASE):
                tag = m_inp.group(0)
                if re.search(r'\bplaceholder=', tag, re.IGNORECASE):
                    has_id = re.search(r'\bid=', tag, re.IGNORECASE)
                    has_label = re.search(r'\baria-label(?:ledby)?=', tag, re.IGNORECASE)
                    if not (has_id or has_label):
                        issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                        "issue": rule["description"], "command": rule["command"]})
                        break
            continue

        if custom == "srcset_missing":
            if re.search(r'<img\b', content, re.IGNORECASE) and not re.search(r'\bsrcset=|\bsrcSet=', content):
                # Skip if all img tags use data URIs or Next.js Image component is used
                img_tags = re.findall(r'<img\b[^>]*>', content, re.IGNORECASE)
                non_data_imgs = [t for t in img_tags if not re.search(r'src=["\']data:', t, re.IGNORECASE)]
                if non_data_imgs:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "anchor_target_blank":
            if re.search(r'target=["\']_blank["\']', content, re.IGNORECASE):
                if not re.search(r'noopener', content, re.IGNORECASE) or not re.search(r'noreferrer', content, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "dangerous_html":
            if re.search(r'dangerouslySetInnerHTML', content) and not re.search(r'DOMPurify', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "duplicate_import":
            import_modules: list[str] = []
            for m_imp in re.finditer(r"import\s+[^;]+\s+from\s+['\"]([^'\"]+)['\"]", content):
                mod = m_imp.group(1)
                if mod in import_modules:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": f"{rule['description']} Module: '{mod}'", "command": rule["command"]})
                    break
                import_modules.append(mod)
            continue

        if custom == "document_cookie_ssr":
            if re.search(r'\bdocument\.cookie\b', content) and not re.search(r'typeof\s+(?:window|document)\s*!==', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "inner_html_assign":
            if re.search(r'\.innerHTML\s*[+]?=\s*', content) and not re.search(r'DOMPurify', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "navigator_ssr":
            if re.search(r'\bnavigator\.\w+', content) and not re.search(r'typeof\s+window\s*!==', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "postmessage_origin_missing":
            if re.search(r"addEventListener\s*\(\s*['\"]message['\"]", content) and not re.search(r'event\.origin|e\.origin', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "localstorage_ssr":
            if re.search(r'\b(?:localStorage|sessionStorage)\b', content):
                if not re.search(r'typeof\s+window\s*!==\s*["\']undefined["\']', content):
                    # Don't flag if it's inside a useEffect (client-only)
                    in_use_effect = bool(re.search(r'useEffect\s*\(\s*(?:\(\s*\)|[^,)]+)\s*=>\s*\{[^}]*(?:localStorage|sessionStorage)', content, re.DOTALL))
                    if not in_use_effect:
                        issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                        "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "window_object_ssr":
            if re.search(r'\bwindow\.\w+', content):
                if not re.search(r'typeof\s+window\s*!==\s*["\']undefined["\']', content):
                    in_use_effect = bool(re.search(r'useEffect\s*\(\s*(?:\(\s*\)|[^,)]+)\s*=>\s*\{[^}]*window\.', content, re.DOTALL))
                    if not in_use_effect:
                        issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                        "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "missing_key_prop":
            # .map() that returns JSX but none of the returned elements have key=
            for m_map in re.finditer(r'\.map\s*\(', content):
                start = m_map.end()
                # Grab up to 500 chars of context
                chunk = content[start:start + 500]
                if re.search(r'<[A-Z][a-zA-Z]*\b|<[a-z][a-z-]+\b', chunk) and not re.search(r'\bkey=', chunk):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "framer_no_reduced_motion":
            if re.search(r"from ['\"]framer-motion['\"]", content) and re.search(r'\bmotion\.', content):
                if not re.search(r'useReducedMotion', content):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "lazy_without_suspense":
            if re.search(r'(?:React\.)?lazy\s*\(', content) and not re.search(r'Suspense', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "media_autoplay":
            for m_av in re.finditer(r'<(?:video|audio)\b([^>]*)', content, re.IGNORECASE):
                attrs = m_av.group(1)
                if re.search(r'\bautoPlay\b|\bautoplay\b', attrs, re.IGNORECASE) and not re.search(r'\bmuted\b', attrs, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "select_no_label":
            for m_sel in re.finditer(r'<select\b([^>]*)', content, re.IGNORECASE):
                attrs = m_sel.group(1)
                # Check nearby (within 200 chars) for a label
                pos = m_sel.start()
                context = content[max(0, pos - 200):pos + 200]
                if not re.search(r'<label\b|aria-label=|aria-labelledby=', context, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "icon_aria_missing":
            for m_icon in re.finditer(r'<svg\b[^>]*>|<i\s+class=[^>]+>', content, re.IGNORECASE):
                pos = m_icon.start()
                context = content[max(0, pos - 100):pos + 200]
                if not re.search(r'aria-(?:label|hidden|labelledby)=', context, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "icon_only_button":
            for m_btn in re.finditer(r'<button\b([^>]*)>\s*<(?:svg|i)\b', content, re.IGNORECASE):
                attrs = m_btn.group(1)
                if not re.search(r'aria-label=', attrs, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        if custom == "next_image_raw":
            if re.search(r"from ['\"]next/", content) and re.search(r'<img\b', content, re.IGNORECASE):
                if not re.search(r"from ['\"]next/image['\"]", content):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "three_equal_column":
            if re.search(r'grid-cols-3\b', content, re.IGNORECASE):
                # Flag if there are 3+ child elements with identical classNames (crude check)
                child_classes = re.findall(r'className=["\']([^"\']+)["\']', content)
                if len(child_classes) >= 3:
                    from collections import Counter
                    cls_counts = Counter(child_classes)
                    if cls_counts.most_common(1)[0][1] >= 3:
                        issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                        "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "font_weight_extremes":
            if re.search(r'\bfont-bold\b', content) and re.search(r'\bfont-normal\b', content):
                if not re.search(r'\bfont-medium\b|\bfont-semibold\b', content):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "missing_loading_state":
            if re.search(r'\buseQuery\b', content) and not re.search(r'\bisLoading\b', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "missing_error_state":
            if re.search(r'\buseQuery\b', content) and re.search(r'\bisLoading\b', content):
                if not re.search(r'\bisError\b|\berror\b', content):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "accordion_faq":
            if re.search(r'\bAccordion\b', content, re.IGNORECASE) and re.search(r'\bFAQ\b', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "dark_mode_toggle":
            if re.search(r'(?:ThemeToggle|toggleDarkMode|DarkModeToggle|darkMode)', content, re.IGNORECASE):
                if not re.search(r'prefers-color-scheme', content, re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "hardcoded_copyright_year":
            if re.search(r'©\s*20\d{2}|&copy;\s*20\d{2}', content, re.IGNORECASE):
                if not re.search(r'getFullYear\s*\(\s*\)', content):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "modal_no_aria":
            if re.search(r'(?:modal|Modal)', content) and not re.search(r'role=["\']dialog["\']', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "pricing_table":
            PRICING_KW = ['Free', 'Pro', 'Enterprise', 'Starter', 'Basic', 'Premium']
            count = sum(1 for kw in PRICING_KW if re.search(r'\b' + kw + r'\b', content, re.IGNORECASE))
            if count >= 3:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
            continue

        if custom == "missing_aria_role":
            for m_el in re.finditer(r'<(?:div|span)\s[^>]*on(?:Click|Keydown|Keyup)[^>]*>', content, re.IGNORECASE):
                if not re.search(r'\brole=', m_el.group(0), re.IGNORECASE):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
            continue

        # ── End of new custom check handlers ─────────────────────────────

        # Standard regex match — flag once per file
        pattern = rule.get("pattern")
        if isinstance(pattern, re.Pattern):
            m = pattern.search(content)
            if m:
                line_number = content.count('\n', 0, m.start()) + 1
                col = m.start() - content.rfind('\n', 0, m.start())
                lines_list = content.splitlines()
                snippet = lines_list[line_number - 1].strip() if line_number <= len(lines_list) else ""
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                    "line": line_number,
                    "column": col,
                    "snippet": snippet,
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
    from uidetox.color_utils import load_dynamic_colors, audit_project_colors, find_color_config_sources

    color_sources = find_color_config_sources(root)
    dynamic_colors = load_dynamic_colors(root)
    color_audit_violations = audit_project_colors(root) if color_sources else []
    color_issue_file = str((color_sources[0] if color_sources else root).resolve())

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

    # Project-level dynamic color audit based on actual Tailwind/theme tokens.
    # Cap output to keep the queue actionable rather than overwhelming.
    for violation in color_audit_violations[:8]:
        all_issues.append({
            "id": "LOW_CONTRAST_SLOP",
            "file": color_issue_file,
            "tier": "T1" if violation.get("severity") == "critical" else "T2",
            "issue": (
                f"Dynamic color audit: {violation['foreground']} on {violation['background']} "
                f"fails WCAG AA ({violation['ratio']}:1 < {violation['required']}:1)."
            ),
            "command": "Adjust the theme token pair to meet WCAG AA contrast, then rescan to verify the updated palette."
        })

    return all_issues
