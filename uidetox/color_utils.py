import json
import re
from pathlib import Path

# Tailwind CSS default colors (partial, primarily grays and some standard colors for contrast checks)
TAILWIND_COLORS = {
    "white": "#ffffff",
    "black": "#000000",
    "gray-50": "#f9fafb",
    "gray-100": "#f3f4f6",
    "gray-200": "#e5e7eb",
    "gray-300": "#d1d5db",
    "gray-400": "#9ca3af",
    "gray-500": "#6b7280",
    "gray-600": "#4b5563",
    "gray-700": "#374151",
    "gray-800": "#1f2937",
    "gray-900": "#111827",
    "red-500": "#ef4444",
    "blue-500": "#3b82f6",
    "green-500": "#10b981",
    "yellow-500": "#eab308",
    "purple-500": "#a855f7",
}

# WCAG AA contrast requirements
WCAG_AA_NORMAL = 4.5  # Normal text (< 18pt or < 14pt bold)
WCAG_AA_LARGE = 3.0  # Large text (>= 18pt or >= 14pt bold)
WCAG_AAA_NORMAL = 7.0  # Enhanced contrast for normal text

TAILWIND_CONFIG_FILES = (
    "tailwind.config.js",
    "tailwind.config.ts",
    "tailwind.config.mjs",
    "tailwind.config.cjs",
)
CSS_COLOR_FILES = (
    "globals.css",
    "index.css",
    "app.css",
    "styles.css",
    "src/globals.css",
    "src/index.css",
    "src/app.css",
    "src/styles.css",
    "src/styles/globals.css",
    "src/styles/index.css",
    "app/globals.css",
    "app/layout.css",
    "styles/globals.css",
    "styles/index.css",
)
TOKEN_COLOR_FILES = (
    "tokens.json",
    "design-tokens.json",
    "src/tokens.json",
    "theme.json",
)


def load_dynamic_colors(project_root: Path) -> dict[str, str]:
    """Parse tailwind.config.js/ts, CSS variables, and theme files for custom colors.

    Dynamically reads the project's actual color configuration to cross-reference
    against accessibility standards, instead of relying on hardcoded defaults.
    """
    colors, _ = _load_project_color_data(project_root)
    return colors


def _load_project_color_data(project_root: Path) -> tuple[dict[str, str], set[str]]:
    """Return the resolved color map plus the keys explicitly declared by the project."""
    colors = TAILWIND_COLORS.copy()
    declared_colors: set[str] = set()

    for config_name in TAILWIND_CONFIG_FILES:
        config_path = project_root / config_name
        if config_path.exists():
            _merge_tailwind_colors(config_path, colors, declared_colors)
            break

    for css_file in CSS_COLOR_FILES:
        css_path = project_root / css_file
        if css_path.exists():
            _merge_css_colors(css_path, colors, declared_colors)

    for token_file in TOKEN_COLOR_FILES:
        token_path = project_root / token_file
        if token_path.exists():
            _merge_token_colors(token_path, colors, declared_colors)

    return colors, declared_colors


def _merge_tailwind_colors(
    path: Path, colors: dict[str, str], declared_colors: set[str]
) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return

    for name, hexcode in re.findall(
        r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*[\'"](#[0-9a-fA-F]{3,8})[\'"]',
        content,
    ):
        colors[name] = hexcode
        declared_colors.add(name)

    nested_pattern = r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*\{([^}]+)\}'
    shade_pattern = r'[\'"]?(\d+|DEFAULT)[\'"]?\s*:\s*[\'"](#[0-9a-fA-F]{3,8})[\'"]'
    for parent_name, inner in re.findall(nested_pattern, content):
        for shade, hexcode in re.findall(shade_pattern, inner):
            key = parent_name if shade == "DEFAULT" else f"{parent_name}-{shade}"
            colors[key] = hexcode
            declared_colors.add(key)

    css_var_pattern = r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*[\'"]var\(--([^)]+)\)[\'"]'
    for name, var_name in re.findall(css_var_pattern, content):
        key = f"var-{name}"
        colors[key] = f"var(--{var_name})"
        declared_colors.add(key)


def _merge_css_colors(
    path: Path, colors: dict[str, str], declared_colors: set[str]
) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return

    for name, hexcode in re.findall(
        r"--([a-zA-Z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})",
        content,
    ):
        colors[name] = hexcode
        declared_colors.add(name)

    hsl_pattern = (
        r"--([a-zA-Z0-9-]+)\s*:\s*"
        r"((?:\d+\.?\d*)\s+(?:\d+\.?\d*%?)\s+(?:\d+\.?\d*%?))"
    )
    for name, hsl_value in re.findall(hsl_pattern, content):
        hex_value = _hsl_string_to_hex(hsl_value.strip())
        if hex_value:
            colors[name] = hex_value
            declared_colors.add(name)

    for name, oklch_value in re.findall(
        r"--([a-zA-Z0-9-]+)\s*:\s*oklch\(([^)]+)\)",
        content,
    ):
        key = f"oklch-{name}"
        colors[key] = f"oklch({oklch_value})"
        declared_colors.add(key)


def _merge_token_colors(
    path: Path, colors: dict[str, str], declared_colors: set[str]
) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return
    _extract_tokens_recursive(data, colors, prefix="", declared_colors=declared_colors)


def find_color_config_sources(project_root: Path) -> list[Path]:
    """Return likely files that define project color tokens/configuration."""
    candidates = TAILWIND_CONFIG_FILES + CSS_COLOR_FILES + TOKEN_COLOR_FILES
    return [
        project_root / name for name in candidates if (project_root / name).exists()
    ]


def _extract_tokens_recursive(
    data: dict,
    colors: dict[str, str],
    prefix: str,
    declared_colors: set[str] | None = None,
):
    """Recursively extract color tokens from a design token JSON."""
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        full_key = f"{prefix}-{key}" if prefix else key
        if isinstance(value, str) and re.match(r"^#[0-9a-fA-F]{3,8}$", value):
            colors[full_key] = value
            if declared_colors is not None:
                declared_colors.add(full_key)
        elif isinstance(value, dict):
            if "value" in value and isinstance(value["value"], str):
                val = value["value"]
                if re.match(r"^#[0-9a-fA-F]{3,8}$", val):
                    colors[full_key] = val
                    if declared_colors is not None:
                        declared_colors.add(full_key)
            else:
                _extract_tokens_recursive(
                    value, colors, full_key, declared_colors=declared_colors
                )


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
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    except (ValueError, IndexError):
        return None


def audit_project_colors(project_root: Path) -> list[dict]:
    """Cross-reference project colors against WCAG accessibility standards.

    Returns a list of WCAG violations found in the project's color configuration.
    """
    if not find_color_config_sources(project_root):
        return []

    colors, declared_colors = _load_project_color_data(project_root)
    if not declared_colors:
        return []

    violations = []

    # Find likely background/foreground pairings from CSS variable naming conventions
    bg_names = {
        k: v
        for k, v in colors.items()
        if k in declared_colors
        and any(x in k.lower() for x in ["background", "bg", "surface", "card", "base"])
    }
    fg_names = {
        k: v
        for k, v in colors.items()
        if k in declared_colors
        and any(x in k.lower() for x in ["foreground", "fg", "text", "content", "body"])
    }

    # Check declared foreground/background pairs
    for fg_name, fg_hex in fg_names.items():
        if not fg_hex.startswith("#"):
            continue
        for bg_name, bg_hex in bg_names.items():
            if not bg_hex.startswith("#"):
                continue
            ratio = contrast_ratio(fg_hex, bg_hex)
            if ratio < WCAG_AA_NORMAL:
                violations.append(
                    {
                        "type": "WCAG_AA_VIOLATION",
                        "foreground": f"{fg_name} ({fg_hex})",
                        "background": f"{bg_name} ({bg_hex})",
                        "ratio": round(ratio, 2),
                        "required": WCAG_AA_NORMAL,
                        "severity": "critical" if ratio < WCAG_AA_LARGE else "warning",
                    }
                )

    # Check common Tailwind pairings
    _check_common_pairings(colors, violations, declared_colors)

    return violations


def _check_common_pairings(
    colors: dict[str, str],
    violations: list[dict],
    declared_colors: set[str] | None = None,
):
    """Check commonly paired Tailwind colors for contrast issues."""
    common_pairs = [
        # (text_color_key, bg_color_key)
        ("gray-400", "white"),
        ("gray-500", "gray-100"),
        ("gray-300", "gray-800"),
        ("gray-400", "gray-900"),
    ]
    for text_key, bg_key in common_pairs:
        if declared_colors is not None and (
            text_key not in declared_colors or bg_key not in declared_colors
        ):
            continue
        text_hex = colors.get(text_key)
        bg_hex = colors.get(bg_key)
        if text_hex and bg_hex and text_hex.startswith("#") and bg_hex.startswith("#"):
            ratio = contrast_ratio(text_hex, bg_hex)
            if ratio < WCAG_AA_NORMAL:
                violations.append(
                    {
                        "type": "WCAG_COMMON_PAIR",
                        "foreground": f"{text_key} ({text_hex})",
                        "background": f"{bg_key} ({bg_hex})",
                        "ratio": round(ratio, 2),
                        "required": WCAG_AA_NORMAL,
                    }
                )


def luminance(hex_code: str) -> float:
    try:
        hex_code = hex_code.lstrip("#")
        if len(hex_code) in (3, 4):
            hex_code = "".join(c + c for c in hex_code)
        r, g, b = tuple(int(hex_code[i : i + 2], 16) for i in (0, 2, 4))
        a = [v / 255.0 for v in (r, g, b)]
        a = [(v / 12.92) if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in a]
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722
    except ValueError:
        return 1.0


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = luminance(hex1)
    l2 = luminance(hex2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
