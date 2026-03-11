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
        "pattern": re.compile(r'<button[^>]*(?!hover:)[^>]*className', re.IGNORECASE),
        "tier": "T2",
        "exts": {".tsx", ".jsx", ".html", ".svelte", ".vue"},
        "description": "Button element without hover: state detected.",
        "command": "Add hover:, focus:, and active: states to all interactive elements."
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
        "pattern": re.compile(r'<(?:button|a)\s[^>]*className=["\'][^"]*(?!focus:)[^"]*["\']', re.IGNORECASE),
        "tier": "T2",
        "exts": _JSX_EXTS,
        "description": "Interactive element without focus: state — accessibility gap.",
        "command": "Add focus:ring or focus:outline states for keyboard accessibility."
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
        "pattern": re.compile(r'class(?:Name)?=["\'][^"\']*overflow-[xy]-(?:auto|scroll)(?![^"\']*scrollbar)[^"\']*["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Scrollable container without scrollbar styling or hiding.",
        "command": "Add scrollbar-hide or custom CSS scrollbar for polish."
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
        "pattern": re.compile(r'class(?:Name)?=["\'](?:(?!transition-).)*?hover:(?:(?!transition-).)*?["\']', re.IGNORECASE),
        "tier": "T1",
        "exts": _JSX_EXTS,
        "description": "Interactive element with hover states but missing transition class.",
        "command": "Add 'transition-colors' or 'transition-all' with duration (e.g., duration-200) for smooth easing."
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
]

def analyze_file(filepath: Path, design_variance: int = 8) -> list[dict]:
    """Scan a single file against all slop rules.

    Args:
        filepath: File to scan.
        design_variance: Current DESIGN_VARIANCE dial value (affects conditional rules).
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

    for rule in applicable_rules:
        # Skip rules conditioned on DESIGN_VARIANCE if below threshold
        variance_threshold = rule.get("_requires_variance_gt")
        if isinstance(variance_threshold, (int, float)) and design_variance <= variance_threshold:
            continue

        # Custom check: div_soup requires counting, not just pattern match
        if rule.get("_custom_check") == "div_soup":
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

            found_issues = analyze_file(file_path, design_variance=design_variance)
            all_issues.extend(found_issues)

    return all_issues
