"""Typed design settings and preflight intent shared by agent-facing commands."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from uidetox.frontend_map import FrontendMap


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
    audience: str = "product users"
    primary_job: str = "complete the mapped product task"
    tone: str = "purposeful and brand-specific"
    genre: str = "product interface"
    page_kind: str = "page"
    brand: str = "preserve existing brand signals"
    preserve: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    source: str = "inferred"

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "DesignIntent":
        data = value or {}
        return cls(
            scope=_text(data.get("scope"), "."),
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
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
            merged = {
                **inferred.to_dict(),
                **configured,
                "source": "configured+inferred",
            }
            intent = DesignIntent.from_dict(merged)
        return cls(dials=DesignDials.from_config(config), intent=intent)


def infer_design_intent(
    frontend_map: "FrontendMap | None",
    target: str = ".",
) -> DesignIntent:
    """Infer a conservative preflight brief when PRODUCT/DESIGN context is absent."""
    if frontend_map is None:
        return DesignIntent(scope=target)
    fingerprint = frontend_map.fingerprint
    topology = str(fingerprint.get("topology", "generic-page"))
    counts = fingerprint.get("node_counts", {})
    route_count = int(counts.get("route", 0))
    component_count = int(counts.get("component", 0))
    if topology == "form-flow":
        primary_job = "complete and submit the mapped workflow"
        genre = "task workflow"
    elif topology == "data-workspace":
        primary_job = "inspect, compare, and act on mapped data"
        genre = "operational workspace"
    else:
        primary_job = "navigate and use the mapped interface"
        genre = "product interface"
    page_kind = "component" if route_count == 0 and component_count <= 1 else "page"
    return DesignIntent(
        scope=frontend_map.target,
        primary_job=primary_job,
        genre=genre,
        page_kind=page_kind,
        preserve=frontend_map.contracts.must_preserve,
        constraints=frontend_map.contracts.unknown,
    )


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
