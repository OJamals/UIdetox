import json

from uidetox.color_utils import find_color_config_sources, load_dynamic_colors


def test_load_dynamic_colors_merges_supported_sources(tmp_path):
    (tmp_path / "tailwind.config.js").write_text(
        """
        brand: '#123456',
        accent: { DEFAULT: '#abcdef', 50: '#f0f0f0' },
        surface: 'var(--surface-color)'
        """,
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "globals.css").write_text(
        ":root { --canvas: #010203; --muted: 220 10% 20%; --signal: oklch(60% 0.2 30); }",
        encoding="utf-8",
    )
    (tmp_path / "tokens.json").write_text(
        json.dumps({"semantic": {"success": {"value": "#00ff00"}}}),
        encoding="utf-8",
    )

    colors = load_dynamic_colors(tmp_path)

    assert colors["brand"] == "#123456"
    assert colors["accent"] == "#abcdef"
    assert colors["accent-50"] == "#f0f0f0"
    assert colors["var-surface"] == "var(--surface-color)"
    assert colors["canvas"] == "#010203"
    assert colors["muted"].startswith("#")
    assert colors["oklch-signal"] == "oklch(60% 0.2 30)"
    assert colors["semantic-success"] == "#00ff00"


def test_load_dynamic_colors_uses_first_tailwind_config(tmp_path):
    (tmp_path / "tailwind.config.js").write_text("colors: { brand: '#111111' }", encoding="utf-8")
    (tmp_path / "tailwind.config.ts").write_text("colors: { brand: '#222222' }", encoding="utf-8")

    assert load_dynamic_colors(tmp_path)["brand"] == "#111111"


def test_find_color_config_sources_preserves_precedence_order(tmp_path):
    (tmp_path / "src").mkdir()
    paths = [
        tmp_path / "tailwind.config.ts",
        tmp_path / "src" / "index.css",
        tmp_path / "tokens.json",
    ]
    for path in paths:
        path.write_text("{}", encoding="utf-8")

    assert find_color_config_sources(tmp_path) == paths
