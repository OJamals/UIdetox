import json

import pytest

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
    (tmp_path / "tailwind.config.js").write_text(
        "colors: { brand: '#111111' }", encoding="utf-8"
    )
    (tmp_path / "tailwind.config.ts").write_text(
        "colors: { brand: '#222222' }", encoding="utf-8"
    )

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


def test_normalize_rendered_color_supports_browser_and_persisted_formats():
    from uidetox.color_utils import normalize_rendered_color

    assert normalize_rendered_color("rgb(255, 0, 0)") == (1.0, 0.0, 0.0, 1.0)
    assert normalize_rendered_color("rgb(100% 0% 0% / 50%)") == (
        1.0,
        0.0,
        0.0,
        0.5,
    )
    assert normalize_rendered_color("hsl(120 100% 50% / 0.25)") == (
        0.0,
        1.0,
        0.0,
        0.25,
    )
    assert normalize_rendered_color("oklab(100% 0 0)") == (1.0, 1.0, 1.0, 1.0)
    assert normalize_rendered_color("oklch(0% 0 0)") == (0.0, 0.0, 0.0, 1.0)
    assert normalize_rendered_color("color(srgb 1 0 0 / 40%)") == (
        1.0,
        0.0,
        0.0,
        0.4,
    )
    assert normalize_rendered_color("#33669980") == pytest.approx(
        (0.0331048, 0.1328683, 0.3185468, 0.5019608),
        abs=1e-6,
    )


def test_normalize_rendered_color_never_guesses_unresolved_cascade_values():
    from uidetox.color_utils import normalize_rendered_color

    assert normalize_rendered_color("var(--foreground)") is None
    assert normalize_rendered_color("linear-gradient(red, blue)") is None
    assert normalize_rendered_color("currentColor") is None
    assert normalize_rendered_color("") is None


def test_alpha_compositing_and_wcag_large_text_boundaries_are_exact():
    from uidetox.color_utils import (
        composite_rendered_color,
        contrast_ratio_rgba,
        is_large_text,
    )

    black_half = (0.0, 0.0, 0.0, 0.5)
    white = (1.0, 1.0, 1.0, 1.0)
    composited = composite_rendered_color(black_half, white)

    assert composited == (0.5, 0.5, 0.5, 1.0)
    assert contrast_ratio_rgba(composited, white) == pytest.approx(
        1.9090909,
        abs=1e-6,
    )
    assert is_large_text(23.99, 400) is False
    assert is_large_text(24.0, 400) is True
    assert is_large_text(18.65, 700) is False
    assert is_large_text(18.6667, 700) is True
