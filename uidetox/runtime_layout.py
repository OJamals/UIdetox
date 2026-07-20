"""Typed policy for classifying rendered layout measurements."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class RuntimeMeasuredElement(Protocol):
    tag: str
    measurements: dict[str, Any]


@dataclass(frozen=True)
class RuntimeFinding:
    code: str
    category: str
    severity: str
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeFinding":
        metrics = value.get("metrics", {})
        return cls(
            code=str(value.get("code", "runtime-layout-finding")),
            category=str(value.get("category", "layout")),
            severity=str(value.get("severity", "warning")),
            message=str(value.get("message", "Rendered layout needs review.")),
            metrics=dict(metrics) if isinstance(metrics, dict) else {},
        )


def detect_runtime_findings(
    element: RuntimeMeasuredElement,
) -> tuple[RuntimeFinding, ...]:
    """Classify browser measurements into stable layout finding codes."""

    return (
        *_alignment_findings(element.measurements),
        *_clipping_findings(element.measurements),
        *_spacing_findings(element.measurements),
        *_line_spacing_findings(element),
    )


def _alignment_findings(
    measurements: dict[str, Any],
) -> tuple[RuntimeFinding, ...]:
    findings: list[RuntimeFinding] = []
    layout_deviation = _measurement_float(measurements, "layoutDeviation")
    if layout_deviation > 4:
        axis = str(measurements.get("layoutAxis", "cross-axis"))
        findings.append(
            RuntimeFinding(
                code="runtime-layout-misalignment",
                category="layout",
                severity="warning",
                message=(
                    f"Element is {layout_deviation:.1f}px out of {axis} alignment "
                    "with its peer components."
                ),
                metrics={"axis": axis, "deviation_px": layout_deviation},
            )
        )

    baseline_deviation = _measurement_float(
        measurements, "fontBaselineDeviation"
    )
    font_mismatch = measurements.get("fontMismatch") is True
    if baseline_deviation > 3 or font_mismatch:
        metrics: dict[str, Any] = {}
        reasons: list[str] = []
        if baseline_deviation > 3:
            metrics["baseline_deviation_px"] = baseline_deviation
            reasons.append(f"baseline differs by {baseline_deviation:.1f}px")
        if font_mismatch:
            actual_font = str(measurements.get("fontFamily", "")).strip()
            expected_font = str(
                measurements.get("expectedFontFamily", "")
            ).strip()
            if actual_font:
                metrics["font_family"] = actual_font
            if expected_font:
                metrics["expected_font_family"] = expected_font
            reasons.append("font family differs from equivalent peer text")
        findings.append(
            RuntimeFinding(
                code="runtime-font-misalignment",
                category="typography",
                severity="warning",
                message="Text is misaligned: " + "; ".join(reasons) + ".",
                metrics=metrics,
            )
        )
    return tuple(findings)


def _clipping_findings(
    measurements: dict[str, Any],
) -> tuple[RuntimeFinding, ...]:
    findings: list[RuntimeFinding] = []
    has_text = measurements.get("hasText") is True
    clipped_values = {"clip", "hidden"}
    clipped_x = (
        has_text
        and str(measurements.get("overflowX", "")).lower() in clipped_values
        and _measurement_float(measurements, "scrollWidth")
        > _measurement_float(measurements, "clientWidth") + 1
    )
    clipped_y = (
        has_text
        and str(measurements.get("overflowY", "")).lower() in clipped_values
        and _measurement_float(measurements, "scrollHeight")
        > _measurement_float(measurements, "clientHeight") + 1
    )
    if clipped_x or clipped_y:
        axes = [
            axis
            for axis, clipped in (
                ("horizontal", clipped_x),
                ("vertical", clipped_y),
            )
            if clipped
        ]
        findings.append(
            RuntimeFinding(
                code="runtime-text-clipped",
                category="overflow",
                severity="error",
                message=(
                    "Text is truncated or clipped on the "
                    f"{' and '.join(axes)} axis."
                ),
                metrics={
                    "client_width_px": _measurement_float(
                        measurements, "clientWidth"
                    ),
                    "scroll_width_px": _measurement_float(
                        measurements, "scrollWidth"
                    ),
                    "client_height_px": _measurement_float(
                        measurements, "clientHeight"
                    ),
                    "scroll_height_px": _measurement_float(
                        measurements, "scrollHeight"
                    ),
                },
            )
        )

    if measurements.get("descendantClipped") is True:
        findings.append(
            RuntimeFinding(
                code="runtime-component-clipped",
                category="overflow",
                severity="error",
                message="A child component extends beyond this clipped container.",
            )
        )
    return tuple(findings)


def _spacing_findings(
    measurements: dict[str, Any],
) -> tuple[RuntimeFinding, ...]:
    findings: list[RuntimeFinding] = []
    has_text = measurements.get("hasText") is True
    is_control = measurements.get("isControl") is True
    is_container = (
        is_control or measurements.get("isVisualContainer") is True
    )
    insets = [
        _measurement_optional_float(measurements, f"textInset{side}")
        for side in ("Top", "Right", "Bottom", "Left")
    ]
    present_insets = [value for value in insets if value is not None]
    if has_text and is_container and present_insets and min(present_insets) < 4:
        findings.append(
            RuntimeFinding(
                code="runtime-text-edge-contact",
                category="spacing",
                severity="warning",
                message="Text sits too close to the edge of its card or control.",
                metrics={"minimum_text_inset_px": min(present_insets)},
            )
        )

    horizontal_padding = _padding_pair(measurements, "Left", "Right")
    if is_container and horizontal_padding is not None:
        minimum = 8.0
        if min(horizontal_padding) < minimum or _padding_is_uneven(
            horizontal_padding
        ):
            findings.append(
                RuntimeFinding(
                    code="runtime-horizontal-padding",
                    category="spacing",
                    severity="warning",
                    message="Horizontal padding is too small or visibly uneven.",
                    metrics={
                        "left_px": horizontal_padding[0],
                        "right_px": horizontal_padding[1],
                        "minimum_px": minimum,
                    },
                )
            )

    vertical_padding = _padding_pair(measurements, "Top", "Bottom")
    if is_container and vertical_padding is not None:
        minimum = 6.0 if is_control else 8.0
        if min(vertical_padding) < minimum or _padding_is_uneven(
            vertical_padding
        ):
            findings.append(
                RuntimeFinding(
                    code="runtime-vertical-padding",
                    category="spacing",
                    severity="warning",
                    message="Vertical padding is too small or visibly uneven.",
                    metrics={
                        "top_px": vertical_padding[0],
                        "bottom_px": vertical_padding[1],
                        "minimum_px": minimum,
                    },
                )
            )
    return tuple(findings)


def _line_spacing_findings(
    element: RuntimeMeasuredElement,
) -> tuple[RuntimeFinding, ...]:
    measurements = element.measurements
    font_size = _measurement_float(measurements, "fontSize")
    line_height = _measurement_float(measurements, "lineHeight")
    minimum_ratio = (
        1.05
        if element.tag.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}
        else 1.2
    )
    if not (
        measurements.get("hasText") is True
        and measurements.get("isMultiline") is True
        and font_size > 0
        and line_height / font_size < minimum_ratio
    ):
        return ()
    return (
        RuntimeFinding(
            code="runtime-line-spacing",
            category="typography",
            severity="warning",
            message="Multiline text has inadequate line spacing.",
            metrics={
                "font_size_px": font_size,
                "line_height_px": line_height,
                "line_height_ratio": round(line_height / font_size, 3),
                "minimum_ratio": minimum_ratio,
            },
        ),
    )


def _measurement_optional_float(
    measurements: dict[str, Any], key: str
) -> float | None:
    value = measurements.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _measurement_float(measurements: dict[str, Any], key: str) -> float:
    return _measurement_optional_float(measurements, key) or 0.0


def _padding_pair(
    measurements: dict[str, Any], first: str, second: str
) -> tuple[float, float] | None:
    first_value = _measurement_optional_float(measurements, f"padding{first}")
    second_value = _measurement_optional_float(measurements, f"padding{second}")
    if first_value is None or second_value is None:
        return None
    return (first_value, second_value)


def _padding_is_uneven(values: tuple[float, float]) -> bool:
    return abs(values[0] - values[1]) > max(4.0, max(values) * 0.35)
