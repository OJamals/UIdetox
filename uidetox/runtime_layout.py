"""Typed policy for classifying rendered layout measurements."""

from __future__ import annotations

from typing import Any, Protocol

from uidetox.findings import Finding

_RUNTIME_REMEDIATION_CONSTRAINTS: dict[str, tuple[str, ...]] = {
    "runtime-chart-baseline-misalignment": (
        "Align every chart series to the measured shared baseline; preserve data order and labels.",
    ),
    "runtime-component-clipped": (
        "Restore intrinsic sizing or wrapping at every observed anchor; retain overflow only when source semantics explicitly require it.",
    ),
    "runtime-font-misalignment": (
        "Reconcile the evidenced font family and baseline with equivalent peer text without changing content order.",
    ),
    "runtime-focus-obscured": (
        "Move or resize the authored occluder so the focused control remains fully visible without changing keyboard order.",
    ),
    "runtime-horizontal-padding": (
        "Apply the measured logical inline padding through the owning layout rule without changing intentional scroll boundaries.",
    ),
    "runtime-interactive-scroll-concealment": (
        "Expose every interactive control without requiring scroll discovery; preserve intentional overflow regions.",
    ),
    "runtime-layout-misalignment": (
        "Repair the shared layout parent so the measured peer alignment follows one responsive rule.",
    ),
    "runtime-line-spacing": (
        "Reconcile the measured line-height with the owning type scale while preserving text content and hierarchy.",
    ),
    "runtime-navigation-choice-overload": (
        "Group destinations by user task, expose a clear first choice, and preserve reachable navigation paths.",
    ),
    "runtime-pathological-text-wrap": (
        "Adjust the owning content measure or type rule so measured text wraps remain readable at every observed viewport.",
    ),
    "runtime-text-collision": (
        "Repair the owning layout rule so measured text and peer bounds no longer overlap at observed anchors.",
    ),
    "runtime-text-edge-contact": (
        "Restore measured logical edge spacing through the owning layout rule without changing source order.",
    ),
    "runtime-text-separation": (
        "Restore measured separation between text regions through the shared spacing or type rule.",
    ),
    "runtime-vertical-padding": (
        "Apply the measured logical block padding through the owning layout rule without changing intentional scroll boundaries.",
    ),
}


class RuntimeMeasuredElement(Protocol):
    tag: str
    name: str
    measurements: dict[str, Any]


def RuntimeFinding(
    *,
    code: str,
    category: str,
    severity: str,
    message: str,
    metrics: dict[str, Any] | None = None,
) -> Finding:
    return Finding.create(
        detector_id=code,
        category=category,
        severity=severity,
        confidence=0.9,
        message=message,
        provenance="runtime",
        evidence={
            "basis": "measured",
            "applicability": {"status": "observed"},
            "remediation_constraints": _RUNTIME_REMEDIATION_CONSTRAINTS.get(code, ()),
            "metrics": metrics or {},
        },
        suppression_key=code,
        verifier={"kind": "runtime", "detector_id": code},
        status="informational" if severity == "info" else "pending",
    )


def detect_runtime_findings(
    element: RuntimeMeasuredElement,
) -> tuple[Finding, ...]:
    """Classify browser measurements into stable layout finding codes."""

    if element.measurements.get("obscuredByModal") is True:
        return ()
    return (
        *_alignment_findings(element.measurements),
        *_visual_content_findings(element.measurements),
        *_clipping_findings(element.measurements),
        *_responsive_findings(element.measurements),
        *_focus_findings(element.measurements),
        *_spacing_findings(element.measurements),
        *_line_spacing_findings(element),
    )


def _alignment_findings(
    measurements: dict[str, Any],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
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

    baseline_deviation = _measurement_float(measurements, "fontBaselineDeviation")
    font_mismatch = measurements.get("fontMismatch") is True
    if measurements.get("isTextFlow") is False:
        baseline_deviation = 0
        font_mismatch = False
    if baseline_deviation > 3 or font_mismatch:
        metrics: dict[str, Any] = {}
        reasons: list[str] = []
        if baseline_deviation > 3:
            metrics["baseline_deviation_px"] = baseline_deviation
            reasons.append(f"baseline differs by {baseline_deviation:.1f}px")
        if font_mismatch:
            actual_font = str(measurements.get("fontFamily", "")).strip()
            expected_font = str(measurements.get("expectedFontFamily", "")).strip()
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


def _visual_content_findings(
    measurements: dict[str, Any],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    bar_count = int(_measurement_float(measurements, "chartBarCount"))
    baseline_spread = _measurement_float(measurements, "chartBarBaselineSpread")
    if bar_count >= 3 and baseline_spread > 4:
        findings.append(
            RuntimeFinding(
                code="runtime-chart-baseline-misalignment",
                category="layout",
                severity="warning",
                message=(
                    f"Bar chart baselines vary by {baseline_spread:.1f}px; "
                    "bars should share one horizontal baseline."
                ),
                metrics={
                    "bar_count": bar_count,
                    "baseline_spread_px": baseline_spread,
                },
            )
        )

    collision_count = int(_measurement_float(measurements, "textCollisionCount"))
    if collision_count:
        findings.append(
            RuntimeFinding(
                code="runtime-text-collision",
                category="layout",
                severity="error",
                message="Rendered text overlaps adjacent content.",
                metrics={
                    "collision_count": collision_count,
                    "max_collision_area_px2": _measurement_float(
                        measurements, "maxTextCollisionArea"
                    ),
                    "colliding_selector": str(
                        measurements.get("collidingTextSelector", "")
                    ),
                },
            )
        )

    boundary_count = int(
        _measurement_float(measurements, "unseparatedTextBoundaryCount")
    )
    if boundary_count:
        findings.append(
            RuntimeFinding(
                code="runtime-text-separation",
                category="typography",
                severity="warning",
                message="Adjacent text fragments render without visible separation.",
                metrics={
                    "boundary_count": boundary_count,
                    "minimum_gap_px": _measurement_float(
                        measurements, "minimumAdjacentTextGap"
                    ),
                },
            )
        )
    return tuple(findings)


def _clipping_findings(
    measurements: dict[str, Any],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    has_text = measurements.get("hasText") is True
    contains_scroll_x = measurements.get("containsScrollRegionX") is True
    contains_scroll_y = measurements.get("containsScrollRegionY") is True
    clipped_values = {"clip", "hidden"}
    clipped_x = (
        has_text
        and not contains_scroll_x
        and str(measurements.get("overflowX", "")).lower() in clipped_values
        and _measurement_float(measurements, "scrollWidth")
        > _measurement_float(measurements, "clientWidth") + 1
    )
    clipped_y = (
        has_text
        and not contains_scroll_y
        and str(measurements.get("overflowY", "")).lower() in clipped_values
        and _measurement_float(measurements, "scrollHeight")
        > _measurement_float(measurements, "clientHeight") + 1
    )
    clipped_by_ancestor = measurements.get("clippedByAncestor") is True
    ancestor_clipped_x = any(
        _measurement_float(measurements, key) > 1
        for key in (
            "ancestorClipOverflowInlineStart",
            "ancestorClipOverflowInlineEnd",
        )
    )
    ancestor_clipped_y = any(
        _measurement_float(measurements, key) > 1
        for key in (
            "ancestorClipOverflowBlockStart",
            "ancestorClipOverflowBlockEnd",
        )
    )
    inside_scroll_x = measurements.get("insideScrollRegionX") is True
    inside_scroll_y = measurements.get("insideScrollRegionY") is True
    clipped_by_unmanaged_ancestor = clipped_by_ancestor and (
        (ancestor_clipped_x and not inside_scroll_x)
        or (ancestor_clipped_y and not inside_scroll_y)
        or not (ancestor_clipped_x or ancestor_clipped_y)
    )
    if clipped_x or clipped_y or (has_text and clipped_by_unmanaged_ancestor):
        axes = [
            axis
            for axis, clipped in (
                ("the horizontal axis", clipped_x),
                ("the vertical axis", clipped_y),
            )
            if clipped
        ]
        if clipped_by_unmanaged_ancestor:
            axes.append("an ancestor clipping boundary")
        intentional = measurements.get("intentionalTruncation") is True
        metrics: dict[str, Any] = {
            "client_width_px": _measurement_float(measurements, "clientWidth"),
            "scroll_width_px": _measurement_float(measurements, "scrollWidth"),
            "client_height_px": _measurement_float(measurements, "clientHeight"),
            "scroll_height_px": _measurement_float(measurements, "scrollHeight"),
        }
        clipping_ancestor = str(
            measurements.get("clippingAncestorSelector", "")
        ).strip()
        if clipping_ancestor:
            metrics["clipping_ancestor"] = clipping_ancestor
        for logical_side in (
            "InlineStart",
            "InlineEnd",
            "BlockStart",
            "BlockEnd",
        ):
            value = _measurement_optional_float(
                measurements, f"ancestorClipOverflow{logical_side}"
            )
            if value is not None:
                metrics[f"ancestor_overflow_{_snake_case(logical_side)}_px"] = value
        location = " and ".join(axes) if axes else "the rendered boundary"
        findings.append(
            RuntimeFinding(
                code=(
                    "runtime-text-truncated" if intentional else "runtime-text-clipped"
                ),
                category="overflow",
                severity="info" if intentional else "error",
                message=(
                    f"Text uses an intentional truncation treatment at {location}."
                    if intentional
                    else f"Text is truncated or clipped at {location}."
                ),
                metrics=metrics,
            )
        )

    descendant_clipped = measurements.get("descendantClipped") is True
    if (descendant_clipped and not (contains_scroll_x or contains_scroll_y)) or (
        clipped_by_unmanaged_ancestor and not has_text
    ):
        findings.append(
            RuntimeFinding(
                code="runtime-component-clipped",
                category="overflow",
                severity="error",
                message="A child component extends beyond this clipped container.",
            )
        )
    return tuple(findings)


def _responsive_findings(
    measurements: dict[str, Any],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    client_width = _measurement_float(measurements, "clientWidth")
    scroll_width = _measurement_float(measurements, "scrollWidth")
    concealed_actions_x = _measurement_float(
        measurements,
        (
            "concealedInteractiveDescendantCountX"
            if "concealedInteractiveDescendantCountX" in measurements
            else "concealedInteractiveDescendantCount"
        ),
    )
    if (
        measurements.get("isScrollRegionX") is True
        and concealed_actions_x > 0
        and client_width > 0
        and scroll_width > client_width + 1
    ):
        findings.append(
            RuntimeFinding(
                code="runtime-interactive-scroll-concealment",
                category="responsive",
                severity="error",
                message=(
                    f"{int(concealed_actions_x)} interactive action(s) start outside "
                    "the visible horizontal scroll region."
                ),
                metrics={
                    "concealed_action_count": concealed_actions_x,
                    "client_width_px": client_width,
                    "scroll_width_px": scroll_width,
                    "scroll_width_ratio": round(scroll_width / client_width, 2),
                },
            )
        )
    else:
        client_height = _measurement_float(measurements, "clientHeight")
        scroll_height = _measurement_float(measurements, "scrollHeight")
        concealed_actions_y = _measurement_float(
            measurements, "concealedInteractiveDescendantCountY"
        )
        if (
            measurements.get("isScrollRegionY") is True
            and concealed_actions_y > 0
            and client_height > 0
            and scroll_height > client_height + 1
        ):
            findings.append(
                RuntimeFinding(
                    code="runtime-interactive-scroll-concealment",
                    category="responsive",
                    severity="error",
                    message=(
                        f"{int(concealed_actions_y)} interactive action(s) start "
                        "outside the visible vertical scroll region."
                    ),
                    metrics={
                        "concealed_action_count": concealed_actions_y,
                        "client_height_px": client_height,
                        "scroll_height_px": scroll_height,
                        "scroll_height_ratio": round(scroll_height / client_height, 2),
                    },
                )
            )

    table = measurements.get("table")
    if (
        isinstance(table, dict)
        and table.get("scrollable") is True
        and table.get("scrollbarVisible") is False
        and table.get("affordance") is False
        and _measurement_float(table, "rowCount") >= 2
        and _measurement_float(table, "headerCount") >= 1
    ):
        findings.append(
            RuntimeFinding(
                code="runtime-responsive-table-inaccessible",
                category="responsive",
                severity="error",
                message=(
                    "Responsive table content overflows horizontally without a "
                    "visible or programmatic scrolling affordance."
                ),
                metrics={
                    "header_count": _measurement_float(table, "headerCount"),
                    "row_count": _measurement_float(table, "rowCount"),
                },
            )
        )

    navigation_links = _measurement_float(measurements, "navigationLinkCount")
    navigation_groups = _measurement_float(measurements, "navigationGroupCount")
    if (
        navigation_links > 12
        and (
            measurements.get("isScrollRegionX") is True
            or measurements.get("isScrollRegionY") is True
        )
        and navigation_groups < 2
    ):
        client_height = _measurement_float(measurements, "clientHeight")
        scroll_height = _measurement_float(measurements, "scrollHeight")
        metrics = {
            "link_count": navigation_links,
            "group_count": navigation_groups,
            "recommended_maximum": 12,
        }
        if client_width > 0:
            metrics["scroll_width_ratio"] = round(scroll_width / client_width, 2)
        if client_height > 0:
            metrics["scroll_height_ratio"] = round(scroll_height / client_height, 2)
        findings.append(
            RuntimeFinding(
                code="runtime-navigation-choice-overload",
                category="navigation",
                severity="warning",
                message=(
                    f"Primary navigation exposes {int(navigation_links)} destinations "
                    "through one scroll-dependent surface."
                ),
                metrics=metrics,
            )
        )
    return tuple(findings)


def _focus_findings(measurements: dict[str, Any]) -> tuple[Finding, ...]:
    raw_visibility = measurements.get("focusVisibility")
    if not isinstance(raw_visibility, dict):
        return ()
    occluded_by = str(raw_visibility.get("occludedBy", "")).strip()
    occluded_fraction = _measurement_float(raw_visibility, "occludedFraction")
    if (
        raw_visibility.get("fullyVisible") is not False
        or not occluded_by
        or occluded_fraction < 0.2
    ):
        return ()
    return (
        RuntimeFinding(
            code="runtime-focus-obscured",
            category="accessibility",
            severity="error",
            message="The focused control is partly or fully obscured by authored content.",
            metrics={
                "occluded_by": occluded_by,
                "occluded_fraction": round(occluded_fraction, 2),
            },
        ),
    )


def _spacing_findings(
    measurements: dict[str, Any],
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    has_text = measurements.get("hasText") is True
    is_box_control = measurements.get("isBoxControl") is True
    is_visual_container = measurements.get("isVisualContainer") is True
    has_visual_surface = measurements.get("hasVisualSurface") is not False
    is_container = is_box_control or is_visual_container
    has_axis_scroll_evidence = any(
        key in measurements
        for key in (
            "isScrollRegionX",
            "isScrollRegionY",
            "containsScrollRegionX",
            "containsScrollRegionY",
        )
    )
    legacy_scroll_boundary = not has_axis_scroll_evidence and (
        measurements.get("isScrollRegion") is True
        or measurements.get("containsScrollRegion") is True
    )
    crosses_x_scroll_boundary = legacy_scroll_boundary or (
        measurements.get("isScrollRegionX") is True
        or measurements.get("containsScrollRegionX") is True
    )
    crosses_y_scroll_boundary = legacy_scroll_boundary or (
        measurements.get("isScrollRegionY") is True
        or measurements.get("containsScrollRegionY") is True
    )
    vertical_writing = str(measurements.get("writingMode", "")).startswith(
        ("vertical", "sideways")
    )
    crosses_inline_scroll_boundary = (
        crosses_y_scroll_boundary if vertical_writing else crosses_x_scroll_boundary
    )
    crosses_block_scroll_boundary = (
        crosses_x_scroll_boundary if vertical_writing else crosses_y_scroll_boundary
    )
    insets = _logical_values(
        measurements,
        ("textInsetInlineStart", "textInsetInlineEnd"),
        ("textInsetBlockStart", "textInsetBlockEnd"),
        fallback_keys=(
            "textInsetTop",
            "textInsetRight",
            "textInsetBottom",
            "textInsetLeft",
        ),
    )
    edge_insets = [
        *([] if crosses_inline_scroll_boundary else insets[:2]),
        *([] if crosses_block_scroll_boundary else insets[2:]),
    ]
    present_edge_insets = [value for value in edge_insets if value is not None]
    if (
        has_text
        and is_container
        and measurements.get("isTextFlow") is not False
        and present_edge_insets
        and min(present_edge_insets) < 4
    ):
        findings.append(
            RuntimeFinding(
                code="runtime-text-edge-contact",
                category="spacing",
                severity="warning",
                message="Text sits too close to the edge of its card or control.",
                metrics={"minimum_text_inset_px": min(present_edge_insets)},
            )
        )

    horizontal_padding = _padding_pair(
        measurements,
        ("InlineStart", "InlineEnd"),
        fallback=("Left", "Right"),
    )
    inline_insets = [value for value in insets[:2] if value is not None]
    needs_visual_inline_padding = (
        is_visual_container
        and has_visual_surface
        and not crosses_inline_scroll_boundary
        and bool(inline_insets)
        and min(inline_insets) < 8.0
    )
    if (
        is_box_control or needs_visual_inline_padding
    ) and horizontal_padding is not None:
        minimum = 8.0
        if min(horizontal_padding) < minimum or _padding_is_uneven(horizontal_padding):
            findings.append(
                RuntimeFinding(
                    code="runtime-horizontal-padding",
                    category="spacing",
                    severity="warning",
                    message="Horizontal padding is too small or visibly uneven.",
                    metrics={
                        "inline_start_px": horizontal_padding[0],
                        "inline_end_px": horizontal_padding[1],
                        "minimum_px": minimum,
                    },
                )
            )

    vertical_padding = _padding_pair(
        measurements,
        ("BlockStart", "BlockEnd"),
        fallback=("Top", "Bottom"),
    )
    block_insets = [value for value in insets[2:] if value is not None]
    needs_visual_block_padding = (
        is_visual_container
        and has_visual_surface
        and not crosses_block_scroll_boundary
        and bool(block_insets)
        and min(block_insets) < 8.0
    )
    if (is_box_control or needs_visual_block_padding) and vertical_padding is not None:
        minimum = 6.0 if is_box_control else 8.0
        if min(vertical_padding) < minimum or _padding_is_uneven(vertical_padding):
            findings.append(
                RuntimeFinding(
                    code="runtime-vertical-padding",
                    category="spacing",
                    severity="warning",
                    message="Vertical padding is too small or visibly uneven.",
                    metrics={
                        "block_start_px": vertical_padding[0],
                        "block_end_px": vertical_padding[1],
                        "minimum_px": minimum,
                    },
                )
            )
    return tuple(findings)


def _line_spacing_findings(
    element: RuntimeMeasuredElement,
) -> tuple[Finding, ...]:
    measurements = element.measurements
    findings: list[Finding] = []
    character_count = len("".join(getattr(element, "name", "").split()))
    line_count = int(_measurement_float(measurements, "lineCount"))
    characters_per_line = character_count / line_count if line_count else 0
    if (
        measurements.get("paintedText") is True
        and character_count >= 32
        and line_count >= 4
        and characters_per_line <= 8
    ):
        findings.append(
            RuntimeFinding(
                code="runtime-pathological-text-wrap",
                category="typography",
                severity="error",
                message="Text wraps into pathologically short lines.",
                metrics={
                    "character_count": character_count,
                    "line_count": line_count,
                    "characters_per_line": round(characters_per_line, 2),
                },
            )
        )
    font_size = _measurement_float(measurements, "fontSize")
    line_height = _measurement_float(measurements, "lineHeight")
    minimum_line_gap = _measurement_optional_float(measurements, "minimumLineGap")
    minimum_ratio = (
        1.05 if element.tag.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"} else 1.2
    )
    if not (
        measurements.get("hasText") is True
        and measurements.get("isMultiline") is True
        and measurements.get("isTextFlow") is not False
        and font_size > 0
    ):
        return tuple(findings)
    line_height_ratio = line_height / font_size if line_height > 0 else 0
    line_overlap = (
        minimum_line_gap is not None
        and minimum_line_gap < -1
        and 0 < line_height_ratio < 1
    )
    tight_ratio = 0 < line_height_ratio < minimum_ratio
    if not (line_overlap or tight_ratio):
        return tuple(findings)
    metrics = {
        "font_size_px": font_size,
        "line_height_px": line_height,
        "line_height_ratio": round(line_height_ratio, 3),
        "minimum_ratio": minimum_ratio,
    }
    if minimum_line_gap is not None:
        metrics["minimum_line_gap_px"] = minimum_line_gap
    findings.append(
        RuntimeFinding(
            code="runtime-line-spacing",
            category="typography",
            severity="error" if line_overlap else "warning",
            message=(
                "Adjacent text lines overlap."
                if line_overlap
                else "Multiline text has inadequate line spacing."
            ),
            metrics=metrics,
        )
    )
    return tuple(findings)


def _measurement_optional_float(measurements: dict[str, Any], key: str) -> float | None:
    value = measurements.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _measurement_float(measurements: dict[str, Any], key: str) -> float:
    return _measurement_optional_float(measurements, key) or 0.0


def _padding_pair(
    measurements: dict[str, Any],
    logical: tuple[str, str],
    *,
    fallback: tuple[str, str],
) -> tuple[float, float] | None:
    first_value = _measurement_optional_float(measurements, f"padding{logical[0]}")
    second_value = _measurement_optional_float(measurements, f"padding{logical[1]}")
    if first_value is None or second_value is None:
        first_value = _measurement_optional_float(measurements, f"padding{fallback[0]}")
        second_value = _measurement_optional_float(
            measurements, f"padding{fallback[1]}"
        )
    if first_value is None or second_value is None:
        return None
    return (first_value, second_value)


def _padding_is_uneven(values: tuple[float, float]) -> bool:
    return abs(values[0] - values[1]) > max(4.0, max(values) * 0.35)


def _logical_values(
    measurements: dict[str, Any],
    *logical_pairs: tuple[str, str],
    fallback_keys: tuple[str, ...],
) -> list[float | None]:
    logical_keys = [key for pair in logical_pairs for key in pair]
    values = [_measurement_optional_float(measurements, key) for key in logical_keys]
    if all(value is not None for value in values):
        return values
    return [_measurement_optional_float(measurements, key) for key in fallback_keys]


def _snake_case(value: str) -> str:
    return "".join(
        f"_{character.lower()}" if character.isupper() else character
        for character in value
    ).lstrip("_")
