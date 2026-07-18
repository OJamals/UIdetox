"""Typed design settings and preflight intent shared by agent-facing commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from uidetox.frontend_map import FrontendMap


_INTENT_DEFAULTS: dict[str, Any] = {
    "scope": ".",
    "product_goal": "support the mapped product outcome",
    "audience": "product users",
    "primary_job": "complete the mapped product task",
    "tone": "purposeful and brand-specific",
    "genre": "product interface",
    "page_kind": "page",
    "brand": "preserve existing brand signals",
    "preserve": (),
    "constraints": (),
}
_INTENT_FIELDS = tuple(_INTENT_DEFAULTS)
_MAPPED_INTENT_FIELDS = (
    "scope",
    "product_goal",
    "primary_job",
    "genre",
    "page_kind",
    "preserve",
    "constraints",
)
_PROVENANCE_VALUES = frozenset({"explicit", "mapped", "fallback"})
_SOURCE_CONFIDENCE = {
    "explicit": 1.0,
    "mapped": 0.75,
    "fallback": 0.25,
}
_CONFIRMATION_FIELDS = ("product_goal", "audience", "primary_job")


def _dial(name: str, value: Any, default: int) -> int:
    try:
        parsed = int(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer from 1 to 10") from exc
    if not 1 <= parsed <= 10:
        raise ValueError(f"{name} must be between 1 and 10; got {parsed}")
    return parsed


@dataclass(frozen=True)
class DesignDials:
    design_variance: int = 8
    motion_intensity: int = 6
    visual_density: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "design_variance", _dial("DESIGN_VARIANCE", self.design_variance, 8)
        )
        object.__setattr__(
            self,
            "motion_intensity",
            _dial("MOTION_INTENSITY", self.motion_intensity, 6),
        )
        object.__setattr__(
            self, "visual_density", _dial("VISUAL_DENSITY", self.visual_density, 4)
        )

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "DesignDials":
        return cls(
            design_variance=config.get("DESIGN_VARIANCE", 8),
            motion_intensity=config.get("MOTION_INTENSITY", 6),
            visual_density=config.get("VISUAL_DENSITY", 4),
        )

    def to_config(self) -> dict[str, int]:
        return {
            "DESIGN_VARIANCE": self.design_variance,
            "MOTION_INTENSITY": self.motion_intensity,
            "VISUAL_DENSITY": self.visual_density,
        }


@dataclass(frozen=True)
class DesignIntent:
    scope: str = "."
    product_goal: str = "support the mapped product outcome"
    audience: str = "product users"
    primary_job: str = "complete the mapped product task"
    tone: str = "purposeful and brand-specific"
    genre: str = "product interface"
    page_kind: str = "page"
    brand: str = "preserve existing brand signals"
    preserve: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    source: str = "inferred"
    provenance: dict[str, str] = field(
        default_factory=lambda: {
            field_name: "fallback" for field_name in _INTENT_FIELDS
        }
    )
    evidence: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            field_name: (f"fallback:{field_name}",)
            for field_name in _INTENT_FIELDS
        }
    )
    confidence: dict[str, float] = field(
        default_factory=lambda: {
            field_name: _SOURCE_CONFIDENCE["fallback"]
            for field_name in _INTENT_FIELDS
        }
    )
    confirmation_status: str = "inferred"
    confirmed_at: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "DesignIntent":
        data = value or {}
        provenance = _provenance(data.get("provenance"))
        evidence = _intent_evidence(data.get("evidence"))
        confidence = _intent_confidence(data.get("confidence"))
        for field_name in _INTENT_FIELDS:
            source = provenance.get(field_name, "fallback")
            provenance.setdefault(field_name, source)
            evidence.setdefault(field_name, (f"{source}:{field_name}",))
            confidence.setdefault(field_name, _SOURCE_CONFIDENCE[source])
        return cls(
            scope=_text(data.get("scope"), "."),
            product_goal=_text(
                data.get("product_goal"), "support the mapped product outcome"
            ),
            audience=_text(data.get("audience"), "product users"),
            primary_job=_text(
                data.get("primary_job"), "complete the mapped product task"
            ),
            tone=_text(data.get("tone"), "purposeful and brand-specific"),
            genre=_text(data.get("genre"), "product interface"),
            page_kind=_text(data.get("page_kind"), "page"),
            brand=_text(data.get("brand"), "preserve existing brand signals"),
            preserve=_strings(data.get("preserve")),
            constraints=_strings(data.get("constraints")),
            source=_text(data.get("source"), "configured"),
            provenance=provenance,
            evidence=evidence,
            confidence=confidence,
            confirmation_status=_confirmation_status(provenance),
            confirmed_at=_text(data.get("confirmed_at"), ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def unconfirmed_fields(self) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in _CONFIRMATION_FIELDS
            if self.provenance.get(field_name) != "explicit"
        )


@dataclass(frozen=True)
class DesignSettings:
    dials: DesignDials
    intent: DesignIntent

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        frontend_map: "FrontendMap | None" = None,
        target: str = ".",
    ) -> "DesignSettings":
        inferred = infer_design_intent(frontend_map, target)
        configured = config.get("design_intent")
        if not isinstance(configured, Mapping) or not configured:
            intent = inferred
        else:
            explicit_fields = _explicit_fields(configured)
            configured_intent = DesignIntent.from_dict(configured)
            configured_evidence = _intent_evidence(configured.get("evidence"))
            merged = inferred.to_dict()
            provenance = dict(inferred.provenance)
            evidence = dict(inferred.evidence)
            confidence = dict(inferred.confidence)
            for field_name in explicit_fields:
                merged[field_name] = getattr(configured_intent, field_name)
                provenance[field_name] = "explicit"
                evidence[field_name] = configured_evidence.get(
                    field_name, ("config:design_intent",)
                )
                confidence[field_name] = 1.0
            has_mapped_fields = any(
                value == "mapped" for value in provenance.values()
            )
            merged["source"] = (
                "configured+inferred"
                if explicit_fields and has_mapped_fields
                else "configured"
                if explicit_fields
                else inferred.source
            )
            merged["provenance"] = provenance
            merged["evidence"] = evidence
            merged["confidence"] = confidence
            merged["confirmation_status"] = _confirmation_status(provenance)
            merged["confirmed_at"] = configured_intent.confirmed_at
            intent = DesignIntent.from_dict(merged)
        return cls(dials=DesignDials.from_config(config), intent=intent)


def infer_design_intent(
    frontend_map: "FrontendMap | None",
    target: str = ".",
) -> DesignIntent:
    """Infer a conservative preflight brief when PRODUCT/DESIGN context is absent."""
    if frontend_map is None:
        return DesignIntent(
            scope=target,
            provenance={field_name: "fallback" for field_name in _INTENT_FIELDS},
            evidence={
                field_name: (f"fallback:{field_name}",)
                for field_name in _INTENT_FIELDS
            },
            confidence={
                field_name: _SOURCE_CONFIDENCE["fallback"]
                for field_name in _INTENT_FIELDS
            },
        )
    fingerprint = frontend_map.fingerprint
    topology = str(fingerprint.get("topology", "generic-page"))
    counts = fingerprint.get("node_counts", {})
    route_count = int(counts.get("route", 0))
    component_count = int(counts.get("component", 0))
    if topology == "form-flow":
        product_goal = "help users complete the mapped workflow successfully"
        primary_job = "complete and submit the mapped workflow"
        genre = "task workflow"
    elif topology == "data-workspace":
        product_goal = "help users understand and act on mapped operational data"
        primary_job = "inspect, compare, and act on mapped data"
        genre = "operational workspace"
    else:
        product_goal = "help users navigate and use mapped product capabilities"
        primary_job = "navigate and use the mapped interface"
        genre = "product interface"
    page_kind = "component" if route_count == 0 and component_count <= 1 else "page"
    return DesignIntent(
        scope=frontend_map.target,
        product_goal=product_goal,
        primary_job=primary_job,
        genre=genre,
        page_kind=page_kind,
        preserve=frontend_map.contracts.must_preserve,
        constraints=frontend_map.contracts.unknown,
        provenance={
            field_name: (
                "mapped" if field_name in _MAPPED_INTENT_FIELDS else "fallback"
            )
            for field_name in _INTENT_FIELDS
        },
        evidence={
            field_name: _mapped_evidence(field_name, topology)
            for field_name in _INTENT_FIELDS
        },
        confidence={
            field_name: _SOURCE_CONFIDENCE[
                "mapped" if field_name in _MAPPED_INTENT_FIELDS else "fallback"
            ]
            for field_name in _INTENT_FIELDS
        },
    )


def merge_explicit_design_intent(
    configured: Mapping[str, Any] | None,
    updates: Mapping[str, Any],
    *,
    evidence_source: str,
    confirmed_at: str,
) -> dict[str, Any]:
    """Merge user-authored intent while preserving only prior explicit fields."""

    existing = configured if isinstance(configured, Mapping) else {}
    existing_intent = DesignIntent.from_dict(existing)
    existing_evidence = _intent_evidence(existing.get("evidence"))
    values: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    evidence: dict[str, tuple[str, ...]] = {}
    confidence: dict[str, float] = {}

    for field_name in _explicit_fields(existing):
        values[field_name] = getattr(existing_intent, field_name)
        provenance[field_name] = "explicit"
        evidence[field_name] = existing_evidence.get(
            field_name, ("config:design_intent",)
        )
        confidence[field_name] = 1.0

    changed = False
    for field_name, raw_value in updates.items():
        if field_name not in _INTENT_FIELDS:
            continue
        value = _normalized_intent_value(field_name, raw_value)
        if not _has_configured_value(field_name, raw_value):
            continue
        values[field_name] = value
        provenance[field_name] = "explicit"
        evidence[field_name] = (evidence_source,)
        confidence[field_name] = 1.0
        changed = True

    if not values:
        return {}
    values["source"] = "configured"
    values["provenance"] = provenance
    values["evidence"] = evidence
    values["confidence"] = confidence
    values["confirmation_status"] = _confirmation_status(provenance)
    values["confirmed_at"] = (
        confirmed_at if changed else existing_intent.confirmed_at
    )
    return DesignIntent.from_dict(values).to_dict()


def _text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _provenance(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        field_name: source
        for field_name, source in value.items()
        if field_name in _INTENT_FIELDS
        and isinstance(source, str)
        and source in _PROVENANCE_VALUES
    }


def _explicit_fields(configured: Mapping[str, Any]) -> tuple[str, ...]:
    provenance_value = configured.get("provenance")
    if isinstance(provenance_value, Mapping):
        provenance = _provenance(provenance_value)
        return tuple(
            field_name
            for field_name in _INTENT_FIELDS
            if provenance.get(field_name) == "explicit"
            and _has_configured_value(field_name, configured.get(field_name))
        )

    explicit_fields = []
    for field_name, default in _INTENT_DEFAULTS.items():
        if field_name not in configured:
            continue
        value = _normalized_intent_value(field_name, configured.get(field_name))
        if (
            _has_configured_value(field_name, configured.get(field_name))
            and value != default
        ):
            explicit_fields.append(field_name)
    return tuple(explicit_fields)


def _normalized_intent_value(field_name: str, value: Any) -> Any:
    default = _INTENT_DEFAULTS[field_name]
    if field_name in {"preserve", "constraints"}:
        return _strings(value)
    return _text(value, default)


def _has_configured_value(field_name: str, value: Any) -> bool:
    if field_name in {"preserve", "constraints"}:
        return bool(_strings(value))
    return isinstance(value, str) and bool(value.strip())


def _intent_evidence(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        field_name: evidence
        for field_name, raw_evidence in value.items()
        if field_name in _INTENT_FIELDS
        and (evidence := _strings(raw_evidence))
    }


def _intent_confidence(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    confidence: dict[str, float] = {}
    for field_name, raw_confidence in value.items():
        if field_name not in _INTENT_FIELDS or isinstance(raw_confidence, bool):
            continue
        try:
            parsed = float(raw_confidence)
        except (TypeError, ValueError):
            continue
        if 0.0 <= parsed <= 1.0:
            confidence[field_name] = parsed
    return confidence


def _confirmation_status(provenance: Mapping[str, str]) -> str:
    explicit_count = sum(
        provenance.get(field_name) == "explicit"
        for field_name in _CONFIRMATION_FIELDS
    )
    if explicit_count == len(_CONFIRMATION_FIELDS):
        return "confirmed"
    if explicit_count:
        return "partial"
    return "inferred"


def _mapped_evidence(field_name: str, topology: str) -> tuple[str, ...]:
    if field_name in {"product_goal", "primary_job", "genre"}:
        return (f"frontend-map:fingerprint.topology={topology}",)
    if field_name == "scope":
        return ("frontend-map:target",)
    if field_name == "page_kind":
        return ("frontend-map:fingerprint.node_counts",)
    if field_name == "preserve":
        return ("frontend-map:contracts.must_preserve",)
    if field_name == "constraints":
        return ("frontend-map:contracts.unknown",)
    return (f"fallback:{field_name}",)
