import colorsys
import math
import re
from functools import lru_cache
from typing import TypeAlias

# WCAG AA contrast requirements
WCAG_AA_NORMAL = 4.5  # Normal text (< 18pt or < 14pt bold)
WCAG_AA_LARGE = 3.0  # Large text (>= 18pt or >= 14pt bold)
WCAG_AAA_NORMAL = 7.0  # Enhanced contrast for normal text

RenderedColor: TypeAlias = tuple[float, float, float, float]


def _clamp_unit(value: float) -> float:
    bounded = max(0.0, min(1.0, value))
    if abs(bounded) < 1e-7:
        return 0.0
    if abs(1.0 - bounded) < 1e-7:
        return 1.0
    return bounded


def _srgb_to_linear(value: float) -> float:
    value = _clamp_unit(value)
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _alpha(value: str | None) -> float:
    if value is None:
        return 1.0
    text = value.strip().lower()
    try:
        return _clamp_unit(
            float(text[:-1]) / 100 if text.endswith("%") else float(text)
        )
    except ValueError:
        raise ValueError("Invalid alpha channel") from None


def _components(value: str) -> tuple[list[str], str | None]:
    normalized = value.replace(",", " ")
    if "/" in normalized:
        channels, alpha = normalized.split("/", 1)
        return channels.split(), alpha.strip()
    parts = normalized.split()
    if len(parts) == 4:
        return parts[:3], parts[3]
    return parts, None


def _rgb_component(value: str) -> float:
    text = value.strip().lower()
    return _clamp_unit(
        float(text[:-1]) / 100 if text.endswith("%") else float(text) / 255
    )


def _angle_degrees(value: str) -> float:
    text = value.strip().lower()
    if text.endswith("turn"):
        return float(text[:-4]) * 360
    if text.endswith("grad"):
        return float(text[:-4]) * 0.9
    if text.endswith("rad"):
        return math.degrees(float(text[:-3]))
    if text.endswith("deg"):
        return float(text[:-3])
    return float(text)


def _percent_or_number(value: str, *, percent_scale: float = 1.0) -> float:
    text = value.strip().lower()
    return float(text[:-1]) / 100 * percent_scale if text.endswith("%") else float(text)


def _oklab_to_linear_srgb(
    lightness: float, axis_a: float, axis_b: float
) -> tuple[float, float, float]:
    l_root = lightness + 0.3963377774 * axis_a + 0.2158037573 * axis_b
    m_root = lightness - 0.1055613458 * axis_a - 0.0638541728 * axis_b
    s_root = lightness - 0.0894841775 * axis_a - 1.2914855480 * axis_b
    l_value, m_value, s_value = l_root**3, m_root**3, s_root**3
    return (
        _clamp_unit(
            4.0767416621 * l_value - 3.3077115913 * m_value + 0.2309699292 * s_value
        ),
        _clamp_unit(
            -1.2684380046 * l_value + 2.6097574011 * m_value - 0.3413193965 * s_value
        ),
        _clamp_unit(
            -0.0041960863 * l_value - 0.7034186147 * m_value + 1.707614701 * s_value
        ),
    )


@lru_cache(maxsize=4096)
def normalize_rendered_color(value: str) -> RenderedColor | None:
    """Normalize a browser-computed color or persisted round trip to linear sRGB."""

    text = str(value).strip().lower()
    if not text or text in {"currentcolor", "inherit", "initial", "unset", "revert"}:
        return None
    if text == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    try:
        if match := re.fullmatch(r"#([0-9a-f]{3,8})", text):
            digits = match.group(1)
            if len(digits) in {3, 4}:
                digits = "".join(character * 2 for character in digits)
            if len(digits) not in {6, 8}:
                return None
            encoded = tuple(
                int(digits[index : index + 2], 16) / 255 for index in (0, 2, 4)
            )
            alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
            return (*(_srgb_to_linear(channel) for channel in encoded), alpha)

        if match := re.fullmatch(r"rgba?\((.*)\)", text):
            channels, alpha_text = _components(match.group(1))
            if len(channels) != 3:
                return None
            return (
                *(_srgb_to_linear(_rgb_component(channel)) for channel in channels),
                _alpha(alpha_text),
            )

        if match := re.fullmatch(r"hsla?\((.*)\)", text):
            channels, alpha_text = _components(match.group(1))
            if len(channels) != 3:
                return None
            hue = (_angle_degrees(channels[0]) % 360) / 360
            saturation = _percent_or_number(channels[1])
            lightness = _percent_or_number(channels[2])
            encoded = colorsys.hls_to_rgb(hue, lightness, saturation)
            return (
                *(_srgb_to_linear(channel) for channel in encoded),
                _alpha(alpha_text),
            )

        if match := re.fullmatch(r"oklab\((.*)\)", text):
            channels, alpha_text = _components(match.group(1))
            if len(channels) != 3:
                return None
            lightness = _percent_or_number(channels[0])
            axis_a = _percent_or_number(channels[1], percent_scale=0.4)
            axis_b = _percent_or_number(channels[2], percent_scale=0.4)
            return (
                *_oklab_to_linear_srgb(lightness, axis_a, axis_b),
                _alpha(alpha_text),
            )

        if match := re.fullmatch(r"oklch\((.*)\)", text):
            channels, alpha_text = _components(match.group(1))
            if len(channels) != 3:
                return None
            lightness = _percent_or_number(channels[0])
            chroma = _percent_or_number(channels[1], percent_scale=0.4)
            hue = math.radians(_angle_degrees(channels[2]))
            return (
                *_oklab_to_linear_srgb(
                    lightness,
                    chroma * math.cos(hue),
                    chroma * math.sin(hue),
                ),
                _alpha(alpha_text),
            )

        if match := re.fullmatch(r"color\((srgb|srgb-linear)\s+(.+)\)", text):
            space, body = match.groups()
            channels, alpha_text = _components(body)
            if len(channels) != 3:
                return None
            values = tuple(_percent_or_number(channel) for channel in channels)
            linear = (
                tuple(_srgb_to_linear(channel) for channel in values)
                if space == "srgb"
                else tuple(_clamp_unit(channel) for channel in values)
            )
            return (*linear, _alpha(alpha_text))
    except (TypeError, ValueError, OverflowError):
        return None
    return None


def composite_rendered_color(
    foreground: RenderedColor,
    background: RenderedColor,
) -> RenderedColor:
    """Composite two linear-sRGB RGBA colors with source-over alpha."""

    foreground_alpha = _clamp_unit(foreground[3])
    background_alpha = _clamp_unit(background[3])
    output_alpha = foreground_alpha + background_alpha * (1 - foreground_alpha)
    if output_alpha <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    channels = tuple(
        _clamp_unit(
            (
                foreground[index] * foreground_alpha
                + background[index] * background_alpha * (1 - foreground_alpha)
            )
            / output_alpha
        )
        for index in range(3)
    )
    return (*channels, output_alpha)


def contrast_ratio_rgba(first: RenderedColor, second: RenderedColor) -> float:
    """Return WCAG relative-luminance contrast for two opaque rendered colors."""

    first_luminance = first[0] * 0.2126 + first[1] * 0.7152 + first[2] * 0.0722
    second_luminance = second[0] * 0.2126 + second[1] * 0.7152 + second[2] * 0.0722
    return (max(first_luminance, second_luminance) + 0.05) / (
        min(first_luminance, second_luminance) + 0.05
    )


def is_large_text(font_size_px: float, font_weight: float) -> bool:
    """Apply the WCAG 2.2 large-text boundary in CSS pixels."""

    return font_size_px >= 24 or (font_weight >= 700 and font_size_px >= 14 * 96 / 72)


def luminance(color: str) -> float:
    normalized = normalize_rendered_color(color)
    if normalized is None:
        return 1.0
    return normalized[0] * 0.2126 + normalized[1] * 0.7152 + normalized[2] * 0.0722


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = luminance(hex1)
    l2 = luminance(hex2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)
