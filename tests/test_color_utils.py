import pytest


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


def test_public_luminance_and_contrast_accept_modern_rendered_colors():
    from uidetox.color_utils import contrast_ratio, luminance

    assert luminance("oklch(0% 0 0)") == 0.0
    assert luminance("color(srgb 1 1 1)") == 1.0
    assert contrast_ratio("rgb(0 0 0)", "hsl(0 0% 100%)") == pytest.approx(21.0)
