import json
import re
from pathlib import Path

# Tailwind CSS default colors (partial, primarily grays and some standard colors for contrast checks)
TAILWIND_COLORS = {
    "white": "#ffffff", "black": "#000000",
    "gray-50": "#f9fafb", "gray-100": "#f3f4f6", "gray-200": "#e5e7eb", "gray-300": "#d1d5db", "gray-400": "#9ca3af",
    "gray-500": "#6b7280", "gray-600": "#4b5563", "gray-700": "#374151", "gray-800": "#1f2937", "gray-900": "#111827",
    "red-500": "#ef4444", "blue-500": "#3b82f6", "green-500": "#10b981", "yellow-500": "#eab308", "purple-500": "#a855f7"
}

# WCAG AA contrast requirements
WCAG_AA_NORMAL = 4.5   # Normal text (< 18pt or < 14pt bold)
WCAG_AA_LARGE = 3.0    # Large text (>= 18pt or >= 14pt bold)
WCAG_AAA_NORMAL = 7.0  # Enhanced contrast for normal text


def load_dynamic_colors(project_root: Path) -> dict[str, str]:
    """Parse tailwind.config.js/ts, CSS variables, and theme files for custom colors.

    Dynamically reads the project's actual color configuration to cross-reference
    against accessibility standards, instead of relying on hardcoded defaults.
    """
    colors = TAILWIND_COLORS.copy()

    # 1. Try to read tailwind.config.js/ts/mjs via simple regex mapping
    for config_name in ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs", "tailwind.config.cjs"]:
        tailwind_cfg = project_root / config_name
        if tailwind_cfg.exists():
            try:
                content = tailwind_cfg.read_text(encoding="utf-8")
                # Match colors: { brand: '#123456', ... }
                matches = re.findall(r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*[\'"](#[0-9a-fA-F]{3,8})[\'"]', content)
                for name, hexcode in matches:
                    colors[name] = hexcode

                # Match nested color objects: brand: { 50: '#...', 100: '#...', ... }
                nested_matches = re.findall(
                    r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*\{([^}]+)\}',
                    content
                )
                for parent_name, inner in nested_matches:
                    shade_matches = re.findall(r'[\'"]?(\d+|DEFAULT)[\'"]?\s*:\s*[\'"](#[0-9a-fA-F]{3,8})[\'"]', inner)
                    for shade, hexcode in shade_matches:
                        key = f"{parent_name}-{shade}" if shade != "DEFAULT" else parent_name
                        colors[key] = hexcode

                # Match CSS variable references in Tailwind v4 format
                css_var_matches = re.findall(r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*[\'"]var\(--([^)]+)\)[\'"]', content)
                for name, var_name in css_var_matches:
                    colors[f"var-{name}"] = f"var(--{var_name})"

            except (UnicodeDecodeError, OSError) as exc:
                import logging
                logging.getLogger(__name__).debug(
                    "Failed to read Tailwind config %s: %s", config_name, exc
                )
            break  # Only read the first found config

    # 2. Try to read CSS variables from common CSS entry points
    css_candidates = [
        "globals.css", "index.css", "app.css", "styles.css",
        "src/globals.css", "src/index.css", "src/app.css", "src/styles.css",
        "src/styles/globals.css", "src/styles/index.css",
        "app/globals.css", "app/layout.css",
        "styles/globals.css", "styles/index.css",
    ]
    for css_file in css_candidates:
        css_path = project_root / css_file
        if css_path.exists():
            try:
                content = css_path.read_text(encoding="utf-8")
                # Match hex color variables
                matches = re.findall(r'--([a-zA-Z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})', content)
                for name, hexcode in matches:
                    colors[name] = hexcode

                # Match HSL color variables
                hsl_matches = re.findall(
                    r'--([a-zA-Z0-9-]+)\s*:\s*((?:\d+\.?\d*)\s+(?:\d+\.?\d*%?)\s+(?:\d+\.?\d*%?))',
                    content
                )
                for name, hsl_val in hsl_matches:
                    hex_val = _hsl_string_to_hex(hsl_val.strip())
                    if hex_val:
                        colors[name] = hex_val

                # Match oklch color variables (Tailwind v4)
                oklch_matches = re.findall(
                    r'--([a-zA-Z0-9-]+)\s*:\s*oklch\(([^)]+)\)',
                    content
                )
                for name, oklch_val in oklch_matches:
                    # Store as-is for now; full oklch→hex conversion is complex
                    colors[f"oklch-{name}"] = f"oklch({oklch_val})"

            except (UnicodeDecodeError, OSError) as exc:
                import logging
                logging.getLogger(__name__).debug(
                    "Failed to read CSS file %s: %s", css_file, exc
                )

    # 3. Try to read design token JSON files
    for token_file in ["tokens.json", "design-tokens.json", "src/tokens.json", "theme.json"]:
        token_path = project_root / token_file
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text(encoding="utf-8"))
                _extract_tokens_recursive(data, colors, prefix="")
            except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
                import logging
                logging.getLogger(__name__).debug(
                    "Failed to read token file %s: %s", token_file, exc
                )

    return colors


def find_color_config_sources(project_root: Path) -> list[Path]:
    """Return likely files that define project color tokens/configuration."""
    sources: list[Path] = []

    for config_name in ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs", "tailwind.config.cjs"]:
        candidate = project_root / config_name
        if candidate.exists():
            sources.append(candidate)

    for css_file in [
        "globals.css", "index.css", "app.css", "styles.css",
        "src/globals.css", "src/index.css", "src/app.css", "src/styles.css",
        "src/styles/globals.css", "src/styles/index.css",
        "app/globals.css", "app/layout.css",
        "styles/globals.css", "styles/index.css",
    ]:
        candidate = project_root / css_file
        if candidate.exists():
            sources.append(candidate)

    for token_file in ["tokens.json", "design-tokens.json", "src/tokens.json", "theme.json"]:
        candidate = project_root / token_file
        if candidate.exists():
            sources.append(candidate)

    return sources


def _extract_tokens_recursive(data: dict, colors: dict[str, str], prefix: str):
    """Recursively extract color tokens from a design token JSON."""
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        full_key = f"{prefix}-{key}" if prefix else key
        if isinstance(value, str) and re.match(r'^#[0-9a-fA-F]{3,8}$', value):
            colors[full_key] = value
        elif isinstance(value, dict):
            if "value" in value and isinstance(value["value"], str):
                val = value["value"]
                if re.match(r'^#[0-9a-fA-F]{3,8}$', val):
                    colors[full_key] = val
            else:
                _extract_tokens_recursive(value, colors, full_key)


def _hsl_string_to_hex(hsl_str: str) -> str | None:
    """Convert an HSL string like '220 14% 10%' to hex."""
    try:
        parts = hsl_str.replace("%", "").split()
        if len(parts) != 3:
            return None
        h = float(parts[0]) / 360.0
        s = float(parts[1]) / 100.0
        l_val = float(parts[2]) / 100.0

        import colorsys
        r, g, b = colorsys.hls_to_rgb(h, l_val, s)
        return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
    except (ValueError, IndexError):
        return None


def audit_project_colors(project_root: Path) -> list[dict]:
    """Cross-reference project colors against WCAG accessibility standards.

    Returns a list of WCAG violations found in the project's color configuration.
    """
    colors = load_dynamic_colors(project_root)
    violations = []

    # Find likely background/foreground pairings from CSS variable naming conventions
    bg_names = {k: v for k, v in colors.items() if any(x in k.lower() for x in ["background", "bg", "surface", "card", "base"])}
    fg_names = {k: v for k, v in colors.items() if any(x in k.lower() for x in ["foreground", "fg", "text", "content", "body"])}

    # Check declared foreground/background pairs
    # Short-circuit once we have enough violations — the downstream cap is 8
    # so there's no value in computing thousands of pairs.
    _MAX_VIOLATIONS = 20
    for fg_name, fg_hex in fg_names.items():
        if len(violations) >= _MAX_VIOLATIONS:
            break
        if not fg_hex.startswith("#"):
            continue
        for bg_name, bg_hex in bg_names.items():
            if len(violations) >= _MAX_VIOLATIONS:
                break
            if not bg_hex.startswith("#"):
                continue
            ratio = contrast_ratio(fg_hex, bg_hex)
            if ratio < WCAG_AA_NORMAL:
                violations.append({
                    "type": "WCAG_AA_VIOLATION",
                    "foreground": f"{fg_name} ({fg_hex})",
                    "background": f"{bg_name} ({bg_hex})",
                    "ratio": round(ratio, 2),
                    "required": WCAG_AA_NORMAL,
                    "severity": "critical" if ratio < WCAG_AA_LARGE else "warning",
                })

    # Check common Tailwind pairings
    _check_common_pairings(colors, violations)

    return violations


def _check_common_pairings(colors: dict[str, str], violations: list[dict]):
    """Check commonly paired Tailwind colors for contrast issues."""
    common_pairs = [
        # (text_color_key, bg_color_key)
        ("gray-400", "white"), ("gray-500", "gray-100"),
        ("gray-300", "gray-800"), ("gray-400", "gray-900"),
    ]
    for text_key, bg_key in common_pairs:
        text_hex = colors.get(text_key)
        bg_hex = colors.get(bg_key)
        if text_hex and bg_hex and text_hex.startswith("#") and bg_hex.startswith("#"):
            ratio = contrast_ratio(text_hex, bg_hex)
            if ratio < WCAG_AA_NORMAL:
                violations.append({
                    "type": "WCAG_COMMON_PAIR",
                    "foreground": f"{text_key} ({text_hex})",
                    "background": f"{bg_key} ({bg_hex})",
                    "ratio": round(ratio, 2),
                    "required": WCAG_AA_NORMAL,
                })

def luminance(hex_code: str) -> float:
    """Compute relative luminance per WCAG 2.x (sRGB).

    Returns a value in [0.0, 1.0].  On invalid input, returns -1.0 so
    callers can detect the error instead of silently treating a bad
    colour as "white" (previous behaviour returned 1.0).
    """
    try:
        hex_code = hex_code.lstrip('#')
        if len(hex_code) == 3:
            hex_code = ''.join(c + c for c in hex_code)
        if len(hex_code) not in (6, 8):
            return -1.0
        r, g, b = (int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        channels = [v / 255.0 for v in (r, g, b)]
        linear = [
            (v / 12.92) if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
            for v in channels
        ]
        return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
    except (ValueError, IndexError):
        return -1.0


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Compute WCAG contrast ratio between two hex colours.

    Returns 1.0 (no contrast) when either colour is invalid, rather
    than silently producing a misleading high ratio.
    """
    l1 = luminance(hex1)
    l2 = luminance(hex2)
    if l1 < 0 or l2 < 0:
        return 1.0  # indeterminate — treat as no contrast
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

