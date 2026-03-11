import re
from pathlib import Path

# Tailwind CSS default colors (partial, primarily grays and some standard colors for contrast checks)
TAILWIND_COLORS = {
    "white": "#ffffff", "black": "#000000",
    "gray-50": "#f9fafb", "gray-100": "#f3f4f6", "gray-200": "#e5e7eb", "gray-300": "#d1d5db", "gray-400": "#9ca3af",
    "gray-500": "#6b7280", "gray-600": "#4b5563", "gray-700": "#374151", "gray-800": "#1f2937", "gray-900": "#111827",
    "red-500": "#ef4444", "blue-500": "#3b82f6", "green-500": "#10b981", "yellow-500": "#eab308", "purple-500": "#a855f7"
}

def load_dynamic_colors(project_root: Path) -> dict[str, str]:
    """Parse tailwind.config.js or globals.css for custom colors."""
    colors = TAILWIND_COLORS.copy()
    
    # 1. Try to read tailwind.config.js via simple regex mapping
    tailwind_cfg = project_root / "tailwind.config.js"
    if tailwind_cfg.exists():
        content = tailwind_cfg.read_text(encoding="utf-8")
        # Match colors: { brand: '#123456', ... }
        matches = re.findall(r'[\'"]?([a-zA-Z0-9-]+)[\'"]?\s*:\s*[\'"](#[0-9a-fA-F]{3,6})[\'"]', content)
        for name, hexcode in matches:
            colors[name] = hexcode

    # 2. Try to read CSS variables from globals.css or index.css
    for css_file in ["globals.css", "index.css", "src/globals.css", "src/index.css"]:
        css_path = project_root / css_file
        if css_path.exists():
            content = css_path.read_text(encoding="utf-8")
            matches = re.findall(r'--([a-zA-Z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})', content)
            for name, hexcode in matches:
                colors[name] = hexcode
                
    return colors

def luminance(hex_code: str) -> float:
    try:
        hex_code = hex_code.lstrip('#')
        if len(hex_code) == 3:
            hex_code = ''.join(c + c for c in hex_code)
        r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        a = [v / 255.0 for v in (r, g, b)]
        a = [(v / 12.92) if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in a]
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722
    except ValueError:
        return 1.0

def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = luminance(hex1)
    l2 = luminance(hex2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

