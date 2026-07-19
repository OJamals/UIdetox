"""Bridge runtime DOM evidence to source, intent, and preserve contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from uidetox.design_context import DesignIntent, DesignSettings
from uidetox.frontend_map import (
    FRONTEND_MAP_FILE,
    FrontendMap,
    FrontendNode,
    load_frontend_map,
)
from uidetox.runtime_observer import RuntimeElement, RuntimePage
from uidetox.state import get_uidetox_dir
from uidetox.visual_evidence import (
    DEFAULT_MAX_PIXELS,
    DEFAULT_PIXEL_THRESHOLD,
    VisualEvidenceStatus,
    VisualRegion,
    inspect_visual_evidence,
)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _runtime_node(
    page: RuntimePage,
    element: RuntimeElement,
    frontend_map: FrontendMap | None,
) -> FrontendNode | None:
    if frontend_map is None:
        return None
    for node in frontend_map.nodes:
        if node.kind not in {"runtime_region", "runtime_action"}:
            continue
        metadata = node.metadata
        if (
            str(metadata.get("runtime_url", "")) == page.url
            and str(metadata.get("viewport", "")) == page.viewport.name
            and (
                (
                    element.selector
                    and str(metadata.get("selector", "")) == element.selector
                )
                or (
                    not element.selector
                    and int(metadata.get("order", -1)) == element.order
                )
            )
        ):
            return node
    return None


def _source_targets(
    node: FrontendNode | None,
    frontend_map: FrontendMap | None,
) -> tuple[str, ...]:
    if node is None or frontend_map is None:
        return ()
    targets = {
        str(value)
        for value in node.metadata.get("source_targets", [])
        if isinstance(value, str) and value
    }
    node_by_id = {candidate.id: candidate for candidate in frontend_map.nodes}
    for edge in frontend_map.edges:
        other_id = None
        if edge.source == node.id:
            other_id = edge.target
        elif edge.target == node.id:
            other_id = edge.source
        if other_id is None:
            continue
        other = node_by_id.get(other_id)
        if other is not None and other.file:
            targets.add(other.file)
    return tuple(sorted(targets))


def _intent_fields(intent: DesignIntent | None) -> tuple[str, ...]:
    if intent is None:
        return ()
    return tuple(
        sorted(
            field_name
            for field_name, source in intent.provenance.items()
            if source in {"explicit", "mapped"}
        )
    )


def _relevant_contracts(
    element: RuntimeElement,
    frontend_map: FrontendMap | None,
    intent: DesignIntent | None,
) -> tuple[str, ...]:
    contracts = list(intent.preserve if intent is not None else ())
    if frontend_map is None:
        return tuple(dict.fromkeys(contracts))
    tag = element.tag.lower()
    role = element.role.lower()
    name = element.name.lower()
    for contract in frontend_map.contracts.must_preserve:
        lowered = contract.lower()
        if (
            (tag == "nav" or role == "navigation")
            and ("route" in lowered or "navigation" in lowered)
        ):
            contracts.append(contract)
        elif element.kind == "action" and (
            "interaction" in lowered
            or "accessible runtime action" in lowered
            or (name and name in lowered)
        ):
            contracts.append(contract)
        elif tag == "form" and "form" in lowered:
            contracts.append(contract)
    return tuple(dict.fromkeys(contracts))


def _region_id(page: RuntimePage, element: RuntimeElement) -> str:
    identity = (
        f"{page.url}|{page.viewport.name}|"
        f"{element.selector or element.tag}|{element.order}"
    )
    return f"runtime-{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


def semantic_regions_from_runtime(
    page: RuntimePage,
    *,
    frontend_map: FrontendMap | None = None,
    intent: DesignIntent | None = None,
) -> tuple[VisualRegion, ...]:
    """Create source-aware regions from explicit runtime element bounds."""

    regions: list[VisualRegion] = []
    for element in page.elements:
        bounds = element.bounds
        required = ("x", "y", "width", "height")
        if not all(key in bounds for key in required):
            continue
        node = _runtime_node(page, element, frontend_map)
        node_marker = f";map:{node.id}" if node is not None else ";map:unresolved"
        regions.append(
            VisualRegion(
                region_id=_region_id(page, element),
                bounds=tuple(float(bounds[key]) for key in required),  # type: ignore[arg-type]
                kind="semantic",
                provenance=(
                    f"runtime:{element.selector or element.tag}:{element.order}"
                    f"{node_marker}"
                ),
                source_targets=_source_targets(node, frontend_map),
                intent_fields=_intent_fields(intent),
                preserve_contracts=_relevant_contracts(
                    element,
                    frontend_map,
                    intent,
                ),
            )
        )
    return tuple(regions)


def build_visual_context(
    frontend_map: FrontendMap | None,
    intent: DesignIntent | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Return content hashes and reviewable provenance context."""

    hashes: dict[str, str] = {}
    context: dict[str, Any] = {}
    if frontend_map is not None:
        map_payload = frontend_map.to_dict()
        hashes["frontend_map"] = _canonical_hash(map_payload)
        context["frontend_map"] = {
            "generated_at": frontend_map.generated_at,
            "target": frontend_map.target,
            "source_manifest": frontend_map.evidence.get("source_manifest", {}),
            "contracts": {
                "must_preserve": list(frontend_map.contracts.must_preserve),
                "may_change": list(frontend_map.contracts.may_change),
                "unknown": list(frontend_map.contracts.unknown),
            },
        }
    if intent is not None:
        intent_payload = intent.to_dict()
        hashes["design_intent"] = _canonical_hash(intent_payload)
        context["design_intent"] = intent_payload
    return hashes, context


def load_project_visual_context(
    config: Mapping[str, Any],
    frontend_map_path: Path,
) -> tuple[
    FrontendMap | None,
    DesignIntent,
    dict[str, str],
    dict[str, Any],
]:
    """Load current map/intent once for capture and freshness consumers."""

    frontend_map = None
    if frontend_map_path.is_file():
        try:
            frontend_map = load_frontend_map(frontend_map_path)
        except (OSError, ValueError, KeyError, TypeError):
            frontend_map = None
    intent = DesignSettings.from_config(config, frontend_map).intent
    hashes, context = build_visual_context(frontend_map, intent)
    return frontend_map, intent, hashes, context


def project_visual_evidence_status(
    config: Mapping[str, Any],
    *,
    required: bool | None = None,
    manifest_path: str | Path | None = None,
) -> VisualEvidenceStatus:
    """Inspect current visual evidence against project config and context."""

    visual_config = config.get("visual_evidence", {})
    if not isinstance(visual_config, Mapping):
        visual_config = {}
    is_required = (
        bool(visual_config.get("required", False))
        if required is None
        else required
    )
    configured_path = manifest_path or visual_config.get("manifest_path")
    resolved_manifest = (
        Path(str(configured_path)).expanduser().resolve()
        if configured_path
        else (get_uidetox_dir() / "snapshots" / "visual-evidence.json")
    )
    try:
        expected_parameters = {
            "threshold": int(
                visual_config.get("threshold", DEFAULT_PIXEL_THRESHOLD)
            ),
            "max_pixels": int(
                visual_config.get("max_pixels", DEFAULT_MAX_PIXELS)
            ),
            "dimension_policy": str(
                visual_config.get("dimension_policy", "strict")
            ),
            "color_policy": str(visual_config.get("color_policy", "native")),
        }
    except (TypeError, ValueError) as error:
        return VisualEvidenceStatus(
            state="blocked",
            ready=False,
            required=is_required,
            manifest_path=resolved_manifest,
            reasons=(f"visual evidence configuration is invalid: {error}",),
        )

    frontend_map_path = get_uidetox_dir() / FRONTEND_MAP_FILE
    _, _, context_hashes, _ = load_project_visual_context(
        config,
        frontend_map_path,
    )
    return inspect_visual_evidence(
        resolved_manifest,
        required=is_required,
        expected_parameters=expected_parameters,
        expected_context_sha256s=context_hashes,
    )


def explicit_ignore_regions(
    config: Mapping[str, Any],
    page: RuntimePage,
) -> tuple[VisualRegion, ...]:
    """Load only user-declared, reasoned ignore rectangles for this page."""

    visual_config = config.get("visual_evidence", {})
    if not isinstance(visual_config, Mapping):
        return ()
    configured = visual_config.get("ignore_regions", [])
    if not isinstance(configured, list):
        raise ValueError("visual_evidence.ignore_regions must be a list")
    page_path = urlsplit(page.url).path or "/"
    regions: list[VisualRegion] = []
    for index, value in enumerate(configured):
        if not isinstance(value, Mapping):
            raise ValueError(f"ignore region {index} must be an object")
        viewport = str(value.get("viewport", ""))
        url_scope = str(value.get("url", ""))
        if viewport and viewport != page.viewport.name:
            continue
        if url_scope and url_scope not in {page.url, page_path}:
            continue
        bounds = value.get("bounds")
        reason = str(value.get("reason", "")).strip()
        if (
            not isinstance(bounds, (list, tuple))
            or len(bounds) != 4
            or not reason
        ):
            raise ValueError(
                f"ignore region {index} requires bounds and a reason"
            )
        regions.append(
            VisualRegion(
                region_id=str(value.get("id", f"ignore-{index}")),
                bounds=tuple(float(item) for item in bounds),  # type: ignore[arg-type]
                kind="ignore",
                reason=reason,
                provenance=f"config:visual_evidence.ignore_regions[{index}]",
            )
        )
    return tuple(regions)
