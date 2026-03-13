"""Static Slop Analyzer: Detects AI anti-patterns via regex/AST rules."""

import logging
import os
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

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
        "pattern": None,
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Excessive identical spacing repetition detected (5+ p-4/gap-4).",
        "command": "Introduce spacing scale variation (mix p-3, p-5, p-6) to create visual rhythm.",
        "_custom_check": "spacing_repetition"
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
        "pattern": None,
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Emoji-heavy UI detected (6+ emoji in one file) — common AI pattern.",
        "command": "Replace decorative emoji with proper iconography or remove entirely. Keep emoji only in user content.",
        "_custom_check": "emoji_heavy"
    },
    {
        "id": "OPACITY_ABUSE_SLOP",
        "pattern": None,
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Excessive opacity/transparency usage detected (glassmorphism cousin).",
        "command": "Use solid colors. Reserve transparency for overlays and modals only.",
        "_custom_check": "opacity_abuse"
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
        "pattern": re.compile(r'bg-clip-text[^\n]{0,200}text-transparent|text-transparent[^\n]{0,200}bg-clip-text', re.IGNORECASE),
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
        "pattern": re.compile(r'text-center[^\n]{0,300}mx-auto|mx-auto[^\n]{0,300}text-center', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Centered hero layout detected — banned when DESIGN_VARIANCE > 4.",
        "command": "Use split-screen, left-aligned, or asymmetric layouts instead of centered hero.",
        "_requires_variance_gt": 4
    },
    {
        "id": "CARD_NESTING_SLOP",
        "pattern": re.compile(r'(?:card|Card)["\']?[^<\n]{0,200}(?:card|Card)', re.IGNORECASE),
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
        "pattern": None,
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Excessive large padding repetition detected (overpadded layout).",
        "command": "Reduce padding and vary spacing scale (p-4, p-5, p-6) for visual rhythm.",
        "_custom_check": "overpadded_layout"
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
        "pattern": None,
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Repeated identical long className string detected — extract to component or utility.",
        "command": "Extract duplicated class strings to a shared component, cn() utility, or cva() variant.",
        "_custom_check": "duplicate_tailwind"
    },
    {
        "id": "DUPLICATE_COLOR_LITERAL",
        "pattern": None,
        "tier": "T2",
        "exts": _ALL_FE_EXTS,
        "description": "Same hex color literal repeated 3+ times — extract to CSS variable or design token.",
        "command": "Define a CSS custom property (--color-brand: #XXXXXX) and reference it everywhere.",
        "_custom_check": "duplicate_color"
    },
    {
        "id": "COPY_PASTE_COMPONENT",
        "pattern": None,
        "tier": "T3",
        "exts": _JSX_EXTS,
        "description": "Copy-pasted markup block detected — extract to reusable component.",
        "command": "Extract repeated markup into a shared component with props for variation.",
        "_custom_check": "copy_paste_component"
    },
    {
        "id": "DUPLICATE_HANDLER",
        "pattern": None,
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Identical inline event handler duplicated — extract to named function.",
        "command": "Extract duplicated handler logic into a named function or custom hook.",
        "_custom_check": "duplicate_handler"
    },
    {
        "id": "REPEATED_MEDIA_QUERY",
        "pattern": None,
        "tier": "T2",
        "exts": {".css", ".scss", ".less"},
        "description": "Same @media query duplicated — consolidate into one block.",
        "command": "Merge duplicate media queries into a single block or use container queries.",
        "_custom_check": "repeated_media_query"
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
    "id": "REDUNDANT_STATE_SLOP",
    "pattern": re.compile(
        r'const\s+\[(\w+),\s*set\w+\]\s*=\s*useState\([^)]*\);\s*\n\s*const\s+\[(\w+),\s*set\w+\]\s*=\s*useState\([^)]*\);\s*\n\s*useEffect\(\(\)\s*=>\s*\{\s*set\2\(\1\)',
        re.MULTILINE | re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx"},
    "description": "Redundant state synchronization detected — useState + useEffect mirroring another state.",
    "command": "Remove the redundant state and use the original state directly, or derive with useMemo.",
},
{
    "id": "OVERLY_COMPLEX_CONDITIONAL",
    "pattern": re.compile(
        r'(?:if|while|return\s*\(?)\s*\([^)]*\?(?:[^?]*\?){3,}',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx", ".ts", ".js"},
    "description": "Overly complex conditional with 3+ nested ternaries detected.",
    "command": "Extract to named boolean variables or use early returns for clarity.",
},
{
    "id": "MAGIC_STRING_SLOP",
    "pattern": re.compile(
        r'(?:===|!==)\s*["\'](?:success|error|pending|loading|active|inactive|enabled|disabled)["\']',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx", ".ts", ".js"},
    "description": "Magic string comparison detected — use enum or constant instead.",
    "command": "Define an enum or const object for status values. Never compare against raw strings.",
},
{
    "id": "DEEP_IMPORT_CHAIN",
    "pattern": re.compile(
        r'import\s+.*\s+from\s+["\'][^"\']*\/(?:[^"\']*\/){4,}[^"\']*["\']',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx", ".ts", ".js"},
    "description": "Deep import chain (5+ levels) detected — indicates poor module organization.",
    "command": "Reorganize module structure or use path aliases to flatten import chains.",
},
{
    "id": "INLINE_EVENT_HANDLER_SLOP",
    "pattern": re.compile(
        r'on(?:Click|Change|Submit|Press|Focus|Blur|KeyDown|MouseEnter|MouseLeave)\s*=\s*\{\s*\(\s*\w*\s*\)\s*=>\s*\{[^}]{100,}\}',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx"},
    "description": "Large inline event handler (100+ chars) detected — harms readability.",
    "command": "Extract to a named function or custom hook for testability and clarity.",
},
{
    "id": "UNSAFE_TYPE_ASSERTION",
    "pattern": re.compile(
        r'\bas\s+(?:any|unknown)\b',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".ts"},
    "description": "Unsafe type assertion to `any` or `unknown` detected.",
    "command": "Use proper typing, type guards, or @ts-expect-error with explanation.",
},
{
    "id": "MISSING_ERROR_BOUNDARY",
    "pattern": re.compile(
        r'<(?:ErrorBoundary|Suspense|Provider|Router|Route|Switch|BrowserRouter)',
        re.IGNORECASE,
    ),
    "tier": "T3",
    "exts": {".tsx", ".jsx"},
    "description": "React app structure detected without ErrorBoundary — unhandled errors will crash the app.",
    "command": "Wrap the app in an ErrorBoundary component to catch and display errors gracefully.",
    "_custom_check": "missing_error_boundary"
},
{
    "id": "UNOPTIMIZED_LIST_RENDERING",
    "pattern": re.compile(
        r'\.map\s*\(\s*\(\s*\w+\s*(?:,\s*\w+)?\s*\)\s*=>\s*<(?:div|li|article|section)\s',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx"},
    "description": "List rendering without key prop or with index as key detected.",
    "command": "Use stable unique IDs as keys. Never use array index for dynamic lists.",
    "_custom_check": "unoptimized_list"
},
{
    "id": "REDUNDANT_USE_CALLBACK",
    "pattern": re.compile(
        r'useCallback\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*\},\s*\[\s*\]\s*\)',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx"},
    "description": "useCallback with empty deps returning a simple function — unnecessary wrapping.",
    "command": "Remove useCallback if the function has no dependencies and isn't passed to child components.",
},
{
    "id": "REDUNDANT_USE_MEMO",
    "pattern": re.compile(
        r'useMemo\s*\(\s*\(\s*\)\s*=>\s*[^,]+,\s*\[\s*\]\s*\)',
        re.IGNORECASE,
    ),
    "tier": "T2",
    "exts": {".tsx", ".jsx"},
    "description": "useMemo with empty deps on a simple value — unnecessary memoization.",
    "command": "Remove useMemo if the computation has no dependencies and is inexpensive.",
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
        logger.debug("AST parse failed for %s", filepath)
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
                "file": fpath,
                "tier": "T2",
                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state['div_count']} divs, 0 semantic elements)",
                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>."
            })

        if state["nested_ternaries"] >= 2:
            issues.append({
                "file": fpath,
                "tier": "T2",
                "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state['nested_ternaries']} nested ternaries found)",
                "command": "Extract nested ternaries into named variables or early returns for clarity."
            })

        if state["cards"] >= 3 and state["charts"] >= 1:
            issues.append({
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
                "file": fpath,
                "tier": "T3",
                "issue": f"Deep prop drilling detected via AST — prop(s) '{sample}' passed through 4+ components.",
                "command": "Extract deeply drilled props into React Context, Zustand store, or composition pattern to reduce coupling."
            })

        # ── AST: useState for animation values ──
        if state["usestate_for_animation"]:
            issues.append({
                "file": fpath,
                "tier": "T2",
                "issue": "React useState used for animation values — causes re-renders on every frame.",
                "command": "Use CSS transitions/animations, Framer Motion, or useRef for animation state. Never drive 60fps animations through React state."
            })

        # ── AST: Identical sibling components (generic layout slop) ──
        for parent_id, children in state["sibling_components"].items():
            if len(children) >= 4:
                counts = Counter(children)
                for comp_name, count in counts.items():
                    if count >= 4:
                        issues.append({
                            "file": fpath,
                            "tier": "T3",
                            "issue": f"Generic layout pattern detected via AST: {count} identical <{comp_name}/> siblings — dashboard/feature-grid slop.",
                            "command": f"Vary the {comp_name} instances (different sizes, spans, emphasis) or replace with asymmetric layout. Identical cards = AI fingerprint."
                        })
                        break  # One issue per parent

        # ── AST: Deeply nested styled-components ──
        if state["styled_nesting_depth"] >= 5:
            issues.append({
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
            logger.warning("Skipping %s: file exceeds 1MB size limit", filepath)
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

        # Custom check: spacing_repetition — count repeated identical spacing utilities
        if custom == "spacing_repetition":
            spacing_pattern = re.compile(r'\b(p-4|gap-4|space-y-4)\b')
            hits = spacing_pattern.findall(content)
            if len(hits) >= 5:
                most_common = Counter(hits).most_common(1)[0]
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} (`{most_common[0]}` appears {most_common[1]} times)",
                    "command": rule["command"]
                })
            continue

        # Custom check: emoji_heavy — count emoji in file
        if custom == "emoji_heavy":
            emoji_count = len(re.findall(r'[\U0001f300-\U0001f9ff]', content))
            if emoji_count >= 6:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({emoji_count} emoji found)",
                    "command": rule["command"]
                })
            continue

        # Custom check: opacity_abuse — count opacity/transparency tokens
        if custom == "opacity_abuse":
            opacity_hits = re.findall(r'\b(?:opacity-\d{1,2}|bg-\S+/\d{1,2})\b', content)
            if len(opacity_hits) >= 5:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({len(opacity_hits)} opacity tokens)",
                    "command": rule["command"]
                })
            continue

        # Custom check: overpadded_layout — count large padding repetitions
        if custom == "overpadded_layout":
            large_padding = re.findall(r'\b(p-(?:8|10|12|16))\b', content)
            if len(large_padding) >= 4:
                most_common = Counter(large_padding).most_common(1)[0]
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} (`{most_common[0]}` appears {most_common[1]} times)",
                    "command": rule["command"]
                })
            continue

        # Custom check: duplicate_tailwind — find repeated long className strings
        if custom == "duplicate_tailwind":
            classnames = re.findall(r'class(?:Name)?=["\']([^"\']{40,})["\']', content, re.IGNORECASE)
            class_counts = Counter(classnames)
            dupes = [(cn, c) for cn, c in class_counts.items() if c >= 2]
            if dupes:
                sample = dupes[0][0][:60]
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} (`{sample}...` repeated {dupes[0][1]}x)",
                    "command": rule["command"]
                })
            continue

        # Custom check: duplicate_color — find hex colors repeated 3+ times
        if custom == "duplicate_color":
            hex_colors = re.findall(r'#[0-9a-fA-F]{6}\b', content)
            color_counts = Counter(hex_colors)
            dupes = [(c, n) for c, n in color_counts.items() if n >= 3]
            if dupes:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({dupes[0][0]} appears {dupes[0][1]} times)",
                    "command": rule["command"]
                })
            continue

        # Custom check: copy_paste_component — find repeated opening tag + content blocks
        if custom == "copy_paste_component":
            # Extract blocks: opening tag with attributes + 80-300 chars of content
            blocks = re.findall(
                r'(<(?:div|section|article)\s[^>]{30,}>)([\s\S]{80,300}?)</(?:div|section|article)>',
                content, re.IGNORECASE,
            )
            if len(blocks) >= 2:
                signatures = [f"{tag}{body.strip()[:80]}" for tag, body in blocks]
                sig_counts = Counter(signatures)
                dupes = [(s, c) for s, c in sig_counts.items() if c >= 2]
                if dupes:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"]
                    })
            continue

        # Custom check: duplicate_handler — find repeated inline event handlers
        if custom == "duplicate_handler":
            handlers = re.findall(
                r'(on(?:Click|Change|Submit|Press|Focus|Blur)\s*=\s*\{[^}]{20,}\})',
                content, re.IGNORECASE,
            )
            handler_counts = Counter(handlers)
            dupes = [(h, c) for h, c in handler_counts.items() if c >= 2]
            if dupes:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"]
                })
            continue

        # Custom check: repeated_media_query — find duplicate @media queries
        if custom == "repeated_media_query":
            media_queries = re.findall(r'(@media\s*\([^)]+\))\s*\{', content, re.IGNORECASE)
            mq_counts = Counter(media_queries)
            dupes = [(mq, c) for mq, c in mq_counts.items() if c >= 2]
            if dupes:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} (`{dupes[0][0]}` appears {dupes[0][1]} times)",
                    "command": rule["command"]
                })
            continue

        # Custom check: missing_error_boundary — flag files with app-level
        # structure (Router, Provider, etc.) but no ErrorBoundary wrapping.
        if custom == "missing_error_boundary":
            has_structure = bool(re.search(
                r'<(?:Suspense|Provider|Router|Route|Switch|BrowserRouter)',
                content, re.IGNORECASE,
            ))
            has_boundary = bool(re.search(r'<ErrorBoundary', content))
            if has_structure and not has_boundary:
                issues.append({
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                })
            continue

        # Custom check: unoptimized_list — flag .map() list rendering that
        # is missing a ``key`` prop or uses index as key.
        if custom == "unoptimized_list":
            for m in re.finditer(
                r'\.map\s*\(\s*\(\s*(\w+)\s*(?:,\s*(\w+))?\s*\)\s*=>\s*(<(?:div|li|article|section)\s[^>]*>)',
                content, re.IGNORECASE,
            ):
                opening_tag = m.group(3)
                index_var = m.group(2)  # may be None
                if 'key=' not in opening_tag:
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": "List rendering without key prop detected.",
                        "command": rule["command"],
                    })
                    break
                elif index_var and re.search(r'key=\{' + re.escape(index_var) + r'\}', opening_tag):
                    issues.append({
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": "List rendering using array index as key detected.",
                        "command": rule["command"],
                    })
                    break
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

    from concurrent.futures import ThreadPoolExecutor, Future
    from uidetox.color_utils import load_dynamic_colors, audit_project_colors, find_color_config_sources

    dynamic_colors = load_dynamic_colors(root)
    color_audit_violations = audit_project_colors(root)
    color_sources = find_color_config_sources(root)
    color_issue_file = str((color_sources[0] if color_sources else root).resolve())

    def _analyze_wrapper(fp: Path) -> list:
        return analyze_file(fp, design_variance=design_variance, dynamic_colors=dynamic_colors) # type: ignore

    future_to_path: dict[Future, Path] = {}
    with ThreadPoolExecutor() as executor:
        for dirpath, dirnames, filenames in os.walk(root):
            # Mutate dirnames in-place to skip IGNORE_DIRS + user excludes
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith('.')]

            for filename in filenames:
                file_path = Path(dirpath) / filename

                # Respect zone overrides
                if zone_skip and str(file_path.resolve()) in zone_skip:
                    continue

                f = executor.submit(_analyze_wrapper, file_path) # type: ignore
                future_to_path[f] = file_path

        for future, fpath in future_to_path.items():
            try:
                all_issues.extend(future.result())
            except Exception as exc:
                logger.error("Error analyzing %s: %s", fpath, exc)

    # Deduplicate: same file + same issue description = single entry
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for issue in all_issues:
        key = (issue.get("file", ""), issue.get("issue", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(issue)
    all_issues = deduped

    # Project-level dynamic color audit based on actual Tailwind/theme tokens.
    # Cap output to keep the queue actionable rather than overwhelming.
    for violation in color_audit_violations[:8]:
        all_issues.append({
            "file": color_issue_file,
            "tier": "T1" if violation.get("severity") == "critical" else "T2",
            "issue": (
                f"Dynamic color audit: {violation['foreground']} on {violation['background']} "
                f"fails WCAG AA ({violation['ratio']}:1 < {violation['required']}:1)."
            ),
            "command": "Adjust the theme token pair to meet WCAG AA contrast, then rescan to verify the updated palette."
        })

    return all_issues
