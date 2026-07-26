"""Pure causal design-quality policy over canonical runtime page evidence."""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any, Protocol

from uidetox.color_utils import (
    WCAG_AA_LARGE,
    WCAG_AA_NORMAL,
    RenderedColor,
    composite_rendered_color,
    contrast_ratio_rgba,
    is_large_text,
)
from uidetox.findings import Finding


class DesignElement(Protocol):
    kind: str
    tag: str
    role: str
    selector: str
    order: int
    bounds: dict[str, float]
    styles: dict[str, str]
    source_hint: str
    states: dict[str, Any]
    measurements: dict[str, Any]


class DesignViewport(Protocol):
    width: int
    height: int


class DesignPage(Protocol):
    elements: Sequence[DesignElement]
    viewport: DesignViewport


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, str):
        match = re.fullmatch(
            r"\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(?:px)?\s*",
            value,
        )
        if match is None:
            return default
        value = match.group(1)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _rgba(value: object) -> RenderedColor | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    channels = tuple(_number(channel, math.nan) for channel in value)
    if any(not math.isfinite(channel) for channel in channels):
        return None
    if any(channel < 0 or channel > 1 for channel in channels):
        return None
    return channels  # type: ignore[return-value]


def _metrics(
    values: Mapping[str, Any],
    *,
    peers: Sequence[str] = (),
    constraints: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        **dict(values),
        "peers": list(peers),
        "remediation_constraints": list(constraints),
    }


def _finding(
    *,
    code: str,
    category: str,
    severity: str,
    confidence: float,
    message: str,
    metrics: Mapping[str, Any],
    status: str = "pending",
) -> Finding:
    return Finding.create(
        detector_id=code,
        category=category,
        severity=severity,
        confidence=confidence,
        message=message,
        provenance="runtime",
        evidence={"metrics": dict(metrics)},
        suppression_key=code,
        verifier={"kind": "runtime", "detector_id": code},
        status=status,
    )


def _paint_finding(element: DesignElement) -> Finding | None:
    if element.measurements.get("paintedText") is not True:
        return None
    paint = element.measurements.get("paint")
    if not isinstance(paint, Mapping):
        return None
    unresolved = paint.get("unresolved", ())
    if isinstance(unresolved, (list, tuple)) and unresolved:
        return _finding(
            code="runtime-color-unresolved",
            category="color",
            severity="warning",
            confidence=1.0,
            message=(
                "Rendered contrast is unresolved because the captured paint stack "
                "contains an image, gradient, blend, filter, or unresolved color."
            ),
            metrics=_metrics(
                {"coverage": "unresolved", "causes": list(unresolved)},
                constraints=(
                    "Retain unresolved coverage until the same capture proves an opaque backdrop.",
                    "Do not substitute token names or guessed palette pairings.",
                ),
            ),
        )

    foreground_value = paint.get("foreground")
    foreground = (
        _rgba(foreground_value.get("rgba"))
        if isinstance(foreground_value, Mapping)
        else None
    )
    raw_layers = paint.get("background_layers")
    if foreground is None or not isinstance(raw_layers, (list, tuple)):
        return _finding(
            code="runtime-color-unresolved",
            category="color",
            severity="warning",
            confidence=1.0,
            message="Rendered contrast is unresolved because normalized paint evidence is incomplete.",
            metrics=_metrics(
                {"coverage": "unresolved", "causes": ["missing-normalized-color"]},
                constraints=(
                    "Capture computed colors and their actual painted ancestors.",
                ),
            ),
        )
    layers: list[tuple[str, RenderedColor]] = []
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, Mapping):
            continue
        color = _rgba(raw_layer.get("rgba"))
        if color is None:
            return _finding(
                code="runtime-color-unresolved",
                category="color",
                severity="warning",
                confidence=1.0,
                message="Rendered contrast is unresolved because a painted ancestor color could not be normalized.",
                metrics=_metrics(
                    {
                        "coverage": "unresolved",
                        "causes": [
                            {
                                "selector": str(raw_layer.get("selector", "")),
                                "value": str(raw_layer.get("raw", "")),
                            }
                        ],
                    },
                    constraints=(
                        "Preserve the raw computed value for a fresh browser capture.",
                    ),
                ),
            )
        layers.append((str(raw_layer.get("selector", "")), color))
    if not layers:
        return _finding(
            code="runtime-color-unresolved",
            category="color",
            severity="warning",
            confidence=1.0,
            message="Rendered contrast is unresolved because no painted backdrop was captured.",
            metrics=_metrics(
                {"coverage": "unresolved", "causes": ["missing-backdrop"]},
                constraints=(
                    "Capture ancestor layers through a proven opaque canvas.",
                ),
            ),
        )

    backdrop: RenderedColor = (0.0, 0.0, 0.0, 0.0)
    for _selector, layer in reversed(layers):
        backdrop = composite_rendered_color(layer, backdrop)
    if backdrop[3] < 0.999:
        return _finding(
            code="runtime-color-unresolved",
            category="color",
            severity="warning",
            confidence=1.0,
            message="Rendered contrast is unresolved because the captured backdrop remains translucent.",
            metrics=_metrics(
                {"coverage": "unresolved", "backdrop_alpha": round(backdrop[3], 6)},
                peers=tuple(selector for selector, _color in layers if selector),
                constraints=(
                    "Extend the captured ancestor stack to a proven opaque layer.",
                ),
            ),
        )
    if element.states.get("disabled") is True:
        return None
    rendered_foreground = composite_rendered_color(foreground, backdrop)
    ratio = contrast_ratio_rgba(rendered_foreground, backdrop)
    font_size = _number(
        element.styles.get("fontSize"),
        _number(element.measurements.get("fontSize"), 16),
    )
    font_weight = _number(element.styles.get("fontWeight"), 400)
    large = is_large_text(font_size, font_weight)
    required = WCAG_AA_LARGE if large else WCAG_AA_NORMAL
    if ratio + 1e-9 >= required:
        return None
    return _finding(
        code="runtime-contrast",
        category="color",
        severity="error",
        confidence=0.99,
        message=(
            f"Rendered text contrast is {ratio:.2f}:1; WCAG 2.2 AA requires "
            f"{required:.1f}:1 for {'large' if large else 'normal'} text."
        ),
        metrics=_metrics(
            {
                "ratio": round(ratio, 4),
                "required": required,
                "large_text": large,
                "font_size_px": font_size,
                "font_weight": font_weight,
                "foreground": list(rendered_foreground),
                "background": list(backdrop),
                "layers": [
                    {"selector": selector, "rgba": list(color)}
                    for selector, color in layers
                ],
                "theme": dict(element.measurements.get("theme", {}))
                if isinstance(element.measurements.get("theme"), Mapping)
                else {},
                "states": dict(element.states),
            },
            peers=tuple(selector for selector, _color in layers if selector),
            constraints=(
                "Preserve the captured semantic color role and interaction state.",
                "Change only a rendered foreground or painted backdrop in this source-owned region.",
            ),
        ),
    )


def _healthy_paint_signature(element: DesignElement) -> tuple[object, ...] | None:
    """Return the inputs that fully determine a no-finding paint result."""

    if element.measurements.get("paintedText") is not True:
        return None
    paint = element.measurements.get("paint")
    if not isinstance(paint, Mapping) or paint.get("unresolved"):
        return None
    foreground_value = paint.get("foreground")
    foreground = (
        _rgba(foreground_value.get("rgba"))
        if isinstance(foreground_value, Mapping)
        else None
    )
    raw_layers = paint.get("background_layers")
    if foreground is None or not isinstance(raw_layers, (list, tuple)):
        return None
    layers: list[RenderedColor] = []
    for raw_layer in raw_layers:
        if not isinstance(raw_layer, Mapping):
            return None
        color = _rgba(raw_layer.get("rgba"))
        if color is None:
            return None
        layers.append(color)
    if not layers:
        return None
    return (
        foreground,
        tuple(layers),
        _number(
            element.styles.get("fontSize"),
            _number(element.measurements.get("fontSize"), 16),
        ),
        _number(element.styles.get("fontWeight"), 400),
        element.states.get("disabled") is True,
    )


def _style_signature(element: DesignElement) -> tuple[object, ...]:
    return (
        element.styles.get("color", ""),
        element.styles.get("backgroundColor", ""),
        element.styles.get("fontSize", ""),
        element.styles.get("fontWeight", ""),
        element.styles.get("borderRadius", ""),
        round(_number(element.bounds.get("height")), 2),
    )


def _outlier_indexes(
    indexes: Sequence[int],
    signatures: Sequence[tuple[object, ...]],
) -> tuple[int, ...]:
    counts = Counter(signatures)
    if len(indexes) < 3 or not counts:
        return ()
    majority, count = counts.most_common(1)[0]
    if count < 2 or list(counts.values()).count(count) > 1:
        return ()
    return tuple(
        index
        for index, signature in zip(indexes, signatures, strict=True)
        if signature != majority
    )


def _component_and_palette_findings(
    elements: Sequence[DesignElement],
) -> dict[int, list[Finding]]:
    findings: dict[int, list[Finding]] = defaultdict(list)
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, element in enumerate(elements):
        group = str(element.measurements.get("equivalenceGroup", "")).strip()
        evidence = str(element.measurements.get("equivalenceEvidence", "")).strip()
        ownership_key = str(element.measurements.get("sourceOwnershipKey", "")).strip()
        if group and evidence == "source-ownership" and ownership_key:
            groups[(ownership_key, group)].append(index)
    for (ownership_key, group), indexes in groups.items():
        if len(indexes) >= 3:
            signatures = [_style_signature(elements[index]) for index in indexes]
            for index in _outlier_indexes(indexes, signatures):
                peers = [
                    elements[peer].selector
                    for peer in indexes
                    if peer != index and elements[peer].selector
                ]
                findings[index].append(
                    _finding(
                        code="runtime-component-drift",
                        category="consistency",
                        severity="warning",
                        confidence=0.92,
                        message="A source-evidenced repeated component drifts from its equivalent peers.",
                        metrics=_metrics(
                            {
                                "equivalence_group": group,
                                "equivalence_evidence": str(
                                    elements[index].measurements.get(
                                        "equivalenceEvidence", ""
                                    )
                                ),
                                "source_ownership": ownership_key,
                                "signature": list(_style_signature(elements[index])),
                            },
                            peers=peers,
                            constraints=(
                                "Preserve component identity and behavior.",
                                "Align only the outlier properties evidenced by the repeated source-owned group.",
                            ),
                        ),
                    )
                )

        palette_indexes = [
            index
            for index in indexes
            if str(elements[index].measurements.get("paletteRole", "")).strip()
        ]
        palette_signatures = [
            (
                elements[index].styles.get("color", ""),
                elements[index].styles.get("backgroundColor", ""),
            )
            for index in palette_indexes
        ]
        for index in _outlier_indexes(palette_indexes, palette_signatures):
            peers = [
                elements[peer].selector
                for peer in palette_indexes
                if peer != index and elements[peer].selector
            ]
            findings[index].append(
                _finding(
                    code="runtime-palette-role-drift",
                    category="color",
                    severity="warning",
                    confidence=0.9,
                    message="An evidenced semantic palette role differs from its repeated peers.",
                    metrics=_metrics(
                        {
                            "equivalence_group": group,
                            "source_ownership": ownership_key,
                            "palette_role": str(
                                elements[index].measurements.get("paletteRole", "")
                            ),
                            "foreground": elements[index].styles.get("color", ""),
                            "background": elements[index].styles.get(
                                "backgroundColor", ""
                            ),
                        },
                        peers=peers,
                        constraints=(
                            "Keep the existing semantic role; reconcile the outlier with its evidenced peer group.",
                        ),
                    ),
                )
            )
    return findings


def _heading_findings(elements: Sequence[DesignElement]) -> dict[int, list[Finding]]:
    findings: dict[int, list[Finding]] = defaultdict(list)
    hierarchies: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for index, element in enumerate(elements):
        if (
            len(element.tag) != 2
            or not element.tag.startswith("h")
            or not element.tag[1].isdigit()
            or not 1 <= int(element.tag[1]) <= 6
        ):
            continue
        hierarchy = str(
            element.measurements.get("readingHierarchySelector")
            or element.measurements.get("layoutParentSelector")
            or ""
        ).strip()
        if hierarchy:
            hierarchies[hierarchy].append((index, int(element.tag[1])))
    for hierarchy, headings in hierarchies.items():
        for position, (index, level) in enumerate(headings):
            higher = [
                candidate for candidate in headings[:position] if candidate[1] < level
            ]
            if not higher:
                continue
            peer_index, _peer_level = higher[-1]
            element, peer = elements[index], elements[peer_index]
            size = _number(element.styles.get("fontSize"))
            peer_size = _number(peer.styles.get("fontSize"))
            weight = _number(element.styles.get("fontWeight"))
            peer_weight = _number(peer.styles.get("fontWeight"))
            if size < peer_size or (size == peer_size and weight < peer_weight):
                continue
            findings[index].append(
                _finding(
                    code="runtime-type-hierarchy",
                    category="typography",
                    severity="warning",
                    confidence=0.94,
                    message="A lower-level heading is not visually subordinate to its preceding higher-level heading.",
                    metrics=_metrics(
                        {
                            "heading": element.tag,
                            "hierarchy": hierarchy,
                            "font_size_px": size,
                            "font_weight": weight,
                            "parent_heading": peer.tag,
                            "parent_font_size_px": peer_size,
                            "parent_font_weight": peer_weight,
                        },
                        peers=(peer.selector,),
                        constraints=(
                            "Preserve semantic heading levels and reading order.",
                            "Create measurable type-scale or weight separation without changing content hierarchy.",
                        ),
                    ),
                )
            )
    return findings


def _rhythm_findings(elements: Sequence[DesignElement]) -> dict[int, list[Finding]]:
    findings: dict[int, list[Finding]] = defaultdict(list)
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, element in enumerate(elements):
        parent = str(element.measurements.get("layoutParentSelector", "")).strip()
        group = str(element.measurements.get("equivalenceGroup", "")).strip()
        evidence = str(element.measurements.get("equivalenceEvidence", "")).strip()
        axis = str(element.measurements.get("equivalenceAxis", "")).strip()
        if parent and group and evidence and axis != "horizontal":
            groups[(parent, group)].append(index)
    for (parent, group), indexes in groups.items():
        if len(indexes) < 4:
            continue
        ordered = sorted(
            indexes,
            key=lambda index: (
                _number(elements[index].bounds.get("y")),
                _number(elements[index].bounds.get("x")),
                elements[index].order,
            ),
        )
        gaps = [
            _number(elements[current].bounds.get("y"))
            - (
                _number(elements[previous].bounds.get("y"))
                + _number(elements[previous].bounds.get("height"))
            )
            for previous, current in pairwise(ordered)
        ]
        median = statistics.median(gaps)
        tolerance = max(4.0, abs(median) * 0.25)
        for gap_index, gap in enumerate(gaps):
            if abs(gap - median) <= tolerance:
                continue
            index = ordered[gap_index + 1]
            peer_selectors = [
                elements[peer].selector
                for peer in ordered
                if peer != index and elements[peer].selector
            ][:20]
            findings[index].append(
                _finding(
                    code="runtime-spatial-rhythm",
                    category="spacing",
                    severity="warning",
                    confidence=0.9,
                    message="A repeated layout gap breaks the evidenced spatial rhythm.",
                    metrics=_metrics(
                        {
                            "layout_parent": parent,
                            "equivalence_group": group,
                            "gap_px": round(gap, 2),
                            "median_gap_px": round(median, 2),
                            "tolerance_px": round(tolerance, 2),
                        },
                        peers=peer_selectors,
                        constraints=(
                            "Preserve grouping and reading order.",
                            "Reconcile the causal gap rather than globally rewriting spacing.",
                        ),
                    ),
                )
            )
    return findings


def _geometry_findings(
    page: DesignPage,
) -> dict[int, list[Finding]]:
    findings: dict[int, list[Finding]] = defaultdict(list)
    by_selector = {
        element.selector: element for element in page.elements if element.selector
    }
    for index, element in enumerate(page.elements):
        bounds = element.bounds
        left = _number(bounds.get("x"))
        top = _number(bounds.get("y"))
        width = _number(bounds.get("width"))
        height = _number(bounds.get("height"))
        right = left + width
        covering_selector = str(element.measurements.get("occludedBy", "")).strip()
        occluded_fraction = _number(element.measurements.get("occludedFraction"))
        if covering_selector and occluded_fraction > 0.1:
            covering = by_selector.get(covering_selector)
            covering_position = (
                covering.styles.get("position", "") if covering is not None else ""
            )
            sticky = covering_position in {"sticky", "fixed"}
            findings[index].append(
                _finding(
                    code=(
                        "runtime-sticky-occlusion"
                        if sticky
                        else "runtime-element-occluded"
                    ),
                    category="layout",
                    severity="error",
                    confidence=0.96,
                    message=(
                        "A sticky or fixed element occludes this rendered target."
                        if sticky
                        else "Another rendered element occludes this target."
                    ),
                    metrics=_metrics(
                        {
                            "occluded_fraction": round(occluded_fraction, 3),
                            "covering_selector": covering_selector,
                            "covering_position": covering_position,
                        },
                        peers=(covering_selector,),
                        constraints=(
                            "Preserve intentional stacking contexts.",
                            "Remove only the proven overlap at this viewport and state.",
                        ),
                    ),
                )
            )
        position = element.styles.get("position", "")
        offscreen = (
            left < -1
            or right > page.viewport.width + 1
            or (
                position in {"fixed", "sticky"}
                and (top < -1 or top + height > page.viewport.height + 1)
            )
        )
        if offscreen and not element.measurements.get("isScrollRegion"):
            findings[index].append(
                _finding(
                    code="runtime-offscreen",
                    category="responsive",
                    severity="error",
                    confidence=0.95,
                    message="The rendered element extends outside the usable viewport.",
                    metrics=_metrics(
                        {
                            "bounds": dict(bounds),
                            "viewport": {
                                "width": page.viewport.width,
                                "height": page.viewport.height,
                            },
                        },
                        constraints=(
                            "Preserve intentional scroll regions.",
                            "Keep the full target reachable at the captured viewport.",
                        ),
                    ),
                )
            )
    return findings


_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "menuitem",
        "option",
        "slider",
        "spinbutton",
        "switch",
        "tab",
    }
)
_TARGET_EXCEPTIONS = frozenset({"inline", "user-agent", "essential", "spacing"})


def _interaction_findings(
    elements: Sequence[DesignElement],
) -> dict[int, list[Finding]]:
    findings: dict[int, list[Finding]] = defaultdict(list)
    for index, element in enumerate(elements):
        interactive = element.kind == "action" or element.role in _INTERACTIVE_ROLES
        if not interactive or element.states.get("disabled") is True:
            continue
        width = _number(element.bounds.get("width"))
        height = _number(element.bounds.get("height"))
        target_exception = str(element.measurements.get("targetException", "")).strip()
        target_spacing = element.measurements.get("targetSpacing")
        spacing_status = (
            str(target_spacing.get("status", "")).strip()
            if isinstance(target_spacing, Mapping)
            else ""
        )
        undersized = width < 24 or height < 24
        if (
            undersized
            and target_exception not in _TARGET_EXCEPTIONS
            and spacing_status == "unresolved"
        ):
            findings[index].append(
                _finding(
                    code="runtime-target-spacing-unresolved",
                    category="interaction",
                    severity="warning",
                    confidence=1.0,
                    message="Target spacing is unresolved because the visible interactive-target index was truncated.",
                    metrics=_metrics(
                        {
                            "width_px": width,
                            "height_px": height,
                            "required_px": 24,
                            "target_spacing": dict(target_spacing)
                            if isinstance(target_spacing, Mapping)
                            else {},
                        },
                        constraints=(
                            "Capture every visible interactive target in the same DOM pass before granting a spacing exception.",
                        ),
                    ),
                )
            )
        if (
            target_exception not in _TARGET_EXCEPTIONS
            and spacing_status not in {"clear", "unresolved"}
            and undersized
        ):
            findings[index].append(
                _finding(
                    code="runtime-target-size",
                    category="interaction",
                    severity="error",
                    confidence=0.97,
                    message="The rendered pointer target does not meet the WCAG 2.2 24×24 CSS pixel minimum.",
                    metrics=_metrics(
                        {
                            "width_px": width,
                            "height_px": height,
                            "required_px": 24,
                            "target_spacing": dict(target_spacing)
                            if isinstance(target_spacing, Mapping)
                            else {},
                        },
                        constraints=(
                            "Preserve inline, user-agent, essential, and spacing exceptions when evidenced.",
                            "Increase the target or its separation without changing its accessible role.",
                        ),
                    ),
                )
            )
        if element.states.get("focused") is not True:
            continue
        indicator = element.measurements.get("focusIndicator")
        if (
            not isinstance(indicator, Mapping)
            or indicator.get("visible") is not True
            or indicator.get("changed") is not True
            or indicator.get("distinguishable") is not True
        ):
            findings[index].append(
                _finding(
                    code="runtime-focus-visible",
                    category="interaction",
                    severity="error",
                    confidence=0.98,
                    message="The actually focused control has no visible focus indicator.",
                    metrics=_metrics(
                        {
                            "wcag": "2.4.7",
                            "captured_state": "focused",
                            "indicator": dict(indicator)
                            if isinstance(indicator, Mapping)
                            else {},
                        },
                        constraints=(
                            "Preserve keyboard focus order and control semantics.",
                            "Add a distinguishable computed visual delta specific to the captured focus state.",
                        ),
                    ),
                )
            )
            continue
        area = _number(indicator.get("area"))
        minimum_area = _number(indicator.get("minimum_area"))
        if minimum_area > 0 and area < minimum_area:
            findings[index].append(
                _finding(
                    code="runtime-focus-appearance-guidance",
                    category="interaction",
                    severity="info",
                    confidence=0.85,
                    message="Focus appearance geometry is below the recorded guidance threshold.",
                    metrics=_metrics(
                        {
                            "area_px2": area,
                            "minimum_area_px2": minimum_area,
                            "classification": "guidance-not-aa",
                        },
                        constraints=(
                            "Do not label focus appearance geometry as a WCAG AA failure.",
                        ),
                    ),
                    status="informational",
                )
            )
    return findings


def detect_design_findings(
    page: DesignPage,
) -> tuple[tuple[Finding, ...], ...]:
    """Return causal semantic findings aligned to ``page.elements`` order."""

    elements = page.elements
    buckets: dict[int, list[Finding]] = defaultdict(list)
    healthy_paint_signatures: set[tuple[object, ...]] = set()
    for index, element in enumerate(elements):
        paint_signature = _healthy_paint_signature(element)
        if paint_signature is not None and paint_signature in healthy_paint_signatures:
            continue
        if paint_finding := _paint_finding(element):
            buckets[index].append(paint_finding)
        elif paint_signature is not None:
            healthy_paint_signatures.add(paint_signature)
    for family in (
        _component_and_palette_findings(elements),
        _heading_findings(elements),
        _rhythm_findings(elements),
        _geometry_findings(page),
        _interaction_findings(elements),
    ):
        for index, findings in family.items():
            buckets[index].extend(findings)
    return tuple(
        tuple(
            sorted(
                buckets.get(index, ()),
                key=lambda finding: (finding.detector_id, finding.fingerprint),
            )
        )
        for index in range(len(elements))
    )
