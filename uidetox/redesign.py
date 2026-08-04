"""Generate structurally divergent redesign plans from a :class:`FrontendMap`."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from uidetox.color_utils import normalize_rendered_color
from uidetox.design_context import DesignDials, DesignIntent
from uidetox.experience_states import (
    EXPERIENCE_STATE_BEHAVIOR,
    EXPERIENCE_STATE_ORDER,
    normalize_experience_states,
    required_experience_states,
)
from uidetox.findings import coerce_finding
from uidetox.frontend_map import (
    FrontendMap,
    frontend_map_is_fresh,
    preservation_contract,
)
from uidetox.project_map import ProjectMap
from uidetox.state import _load_json_object, ensure_uidetox_dir, get_uidetox_dir
from uidetox.utils import now_iso

REDESIGN_SET_FILE = "redesigns.json"
_DISTANCE_KEYS = (
    "topology",
    "navigation",
    "component_partition",
    "primary_action",
    "interaction",
    "responsive",
    "density",
)
_CREATIVE_CHANGE_PREFIXES = (
    "Visual language:",
    "Typography:",
    "Material:",
    "Composition:",
)
_OPERATION_OBLIGATION_STATES = {
    "affected-reads": ("success",),
    "cancellation": ("loading", "error"),
    "conflict": ("error",),
    "duplicate-submit": ("disabled",),
    "idempotency": ("loading", "error"),
    "optimistic-rollback": ("loading", "success", "error"),
    "partial-success": ("success", "error"),
    "retry": ("loading", "error"),
}
_OPERATION_OBLIGATION_ACTIONS = {
    "affected-reads": "refresh only the contract-listed reads after success; do not invent a cache",
    "cancellation": "offer cancellation only through the documented transport and preserve usable content",
    "conflict": "retain user input and expose a recoverable contract conflict",
    "duplicate-submit": "disable an identical mutation while it is in flight and restore it on completion",
    "idempotency": "apply only the server-defined idempotency scope, retention, and replay semantics",
    "optimistic-rollback": "reconcile the optimistic result against the response and restore the prior value on failure",
    "partial-success": "separate succeeded items from operation-scoped failures",
    "retry": "retry only under the documented condition while retaining usable success content",
}


@dataclass(frozen=True)
class RedesignBrief:
    """Constraints controlling proposal generation."""

    target: str = "."
    variants: int = 3
    design_variance: int = 8
    motion_intensity: int = 6
    visual_density: int = 4
    preserve: tuple[str, ...] = ()
    intent: DesignIntent = field(default_factory=DesignIntent)

    def __post_init__(self) -> None:
        dials = DesignDials(
            self.design_variance,
            self.motion_intensity,
            self.visual_density,
        )
        object.__setattr__(self, "design_variance", dials.design_variance)
        object.__setattr__(self, "motion_intensity", dials.motion_intensity)
        object.__setattr__(self, "visual_density", dials.visual_density)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RedesignBrief:
        return cls(
            target=str(value.get("target", ".")),
            variants=int(value.get("variants", 3)),
            design_variance=int(value.get("design_variance", 8)),
            motion_intensity=int(value.get("motion_intensity", 6)),
            visual_density=int(value.get("visual_density", 4)),
            preserve=tuple(str(item) for item in value.get("preserve", [])),
            intent=DesignIntent.from_dict(value.get("intent")),
        )


@dataclass(frozen=True)
class RedesignProposal:
    """One topology-first redesign plan."""

    id: str
    name: str
    strategy: str
    rationale: str
    layout_tree: tuple[str, ...]
    component_architecture: tuple[str, ...]
    interaction_model: str
    responsive_rules: tuple[str, ...]
    changes: tuple[str, ...]
    preserved_contracts: tuple[str, ...]
    migration_steps: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    source_targets: tuple[str, ...]
    fingerprint: dict[str, str]
    novelty_score: int
    source_evidence: tuple[dict[str, Any], ...] = ()
    migration_plan: tuple[dict[str, Any], ...] = ()
    preserved_contract_evidence: tuple[dict[str, Any], ...] = ()
    feasibility_blockers: tuple[str, ...] = ()
    evidence_freshness: dict[str, Any] = field(default_factory=dict)
    observable_checks: tuple[str, ...] = ()

    @property
    def creative_direction(self) -> tuple[str, ...]:
        """Return creative guidance stored in the schema-compatible change list."""

        return tuple(
            change
            for change in self.changes
            if change.startswith(_CREATIVE_CHANGE_PREFIXES)
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RedesignProposal:
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            strategy=str(value["strategy"]),
            rationale=str(value.get("rationale", "")),
            layout_tree=tuple(str(item) for item in value.get("layout_tree", [])),
            component_architecture=tuple(
                str(item) for item in value.get("component_architecture", [])
            ),
            interaction_model=str(value.get("interaction_model", "")),
            responsive_rules=tuple(
                str(item) for item in value.get("responsive_rules", [])
            ),
            changes=tuple(str(item) for item in value.get("changes", [])),
            preserved_contracts=tuple(
                str(item) for item in value.get("preserved_contracts", [])
            ),
            migration_steps=tuple(
                str(item) for item in value.get("migration_steps", [])
            ),
            acceptance_checks=tuple(
                str(item) for item in value.get("acceptance_checks", [])
            ),
            source_targets=tuple(str(item) for item in value.get("source_targets", [])),
            fingerprint={
                str(key): str(item)
                for key, item in dict(value.get("fingerprint", {})).items()
            },
            novelty_score=int(value.get("novelty_score", 0)),
            source_evidence=tuple(
                dict(item) for item in value.get("source_evidence", [])
            ),
            migration_plan=tuple(
                dict(item) for item in value.get("migration_plan", [])
            ),
            preserved_contract_evidence=tuple(
                dict(item) for item in value.get("preserved_contract_evidence", [])
            ),
            feasibility_blockers=tuple(
                str(item) for item in value.get("feasibility_blockers", [])
            ),
            evidence_freshness=dict(value.get("evidence_freshness", {})),
            observable_checks=tuple(
                str(item) for item in value.get("observable_checks", [])
            ),
        )


@dataclass(frozen=True)
class ProposalDistance:
    """Pairwise structural distance between two proposals."""

    left: str
    right: str
    score: int
    changed_dimensions: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProposalDistance:
        return cls(
            left=str(value["left"]),
            right=str(value["right"]),
            score=int(value.get("score", 0)),
            changed_dimensions=tuple(
                str(item) for item in value.get("changed_dimensions", [])
            ),
        )


@dataclass(frozen=True)
class RedesignSet:
    """Ranked redesign proposals plus divergence evidence."""

    schema_version: int
    generated_at: str
    frontend_map_generated_at: str
    target: str
    baseline_fingerprint: dict[str, Any]
    brief: RedesignBrief
    proposals: tuple[RedesignProposal, ...]
    pairwise_distances: tuple[ProposalDistance, ...]
    unknowns: tuple[str, ...]
    contract_lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RedesignSet:
        version = int(value.get("schema_version", 0))
        if version != 2:
            raise ValueError(f"Unsupported redesign schema {version}; expected 2.")
        return cls(
            schema_version=2,
            generated_at=str(value.get("generated_at", "")),
            frontend_map_generated_at=str(value.get("frontend_map_generated_at", "")),
            target=str(value.get("target", ".")),
            baseline_fingerprint=dict(value.get("baseline_fingerprint", {})),
            brief=RedesignBrief.from_dict(dict(value.get("brief", {}))),
            proposals=tuple(
                RedesignProposal.from_dict(dict(item))
                for item in value.get("proposals", [])
            ),
            pairwise_distances=tuple(
                ProposalDistance.from_dict(dict(item))
                for item in value.get("pairwise_distances", [])
            ),
            unknowns=tuple(str(item) for item in value.get("unknowns", [])),
            contract_lineage=dict(value.get("contract_lineage", {})),
        )


@dataclass(frozen=True)
class _Strategy:
    id: str
    name: str
    fingerprint: dict[str, str]
    layout_tree: tuple[str, ...]
    component_architecture: tuple[str, ...]
    interaction_model: str
    responsive_rules: tuple[str, ...]
    migration_steps: tuple[str, ...]
    creative_direction: tuple[str, ...]
    relevance: dict[str, int] = field(default_factory=dict)


_STRATEGIES = (
    _Strategy(
        id="task-flow",
        name="Guided Task Flow",
        fingerprint={
            "topology": "linear-staged",
            "navigation": "progress-rail",
            "component_partition": "step-modules",
            "primary_action": "single-next-action",
            "interaction": "guided-completion",
            "responsive": "stacked-stages",
            "density": "focused",
        },
        layout_tree=(
            "ProgressRail",
            "CurrentTask",
            "ContextPanel",
            "PersistentActionBar",
        ),
        component_architecture=(
            "TaskShell owns progression and cross-step state.",
            "Step modules expose one user outcome each.",
            "ContextPanel contains evidence and help without blocking the primary task.",
        ),
        interaction_model="One explicit decision per stage; completion unlocks the next stage.",
        responsive_rules=(
            "Collapse ProgressRail into a compact step header below tablet width.",
            "Move ContextPanel behind an in-flow disclosure on narrow screens.",
            "Keep PersistentActionBar reachable without covering form errors.",
        ),
        migration_steps=(
            "Extract current actions and validation into task outcomes.",
            "Introduce TaskShell while rendering existing behavior inside step modules.",
            "Move state ownership only after contract-lineage checks pass per step.",
        ),
        creative_direction=(
            "Visual language: Calm procedural clarity with strong step numerals, restrained chrome, and one dominant completion path.",
            "Typography: Use existing type tokens as a functional hierarchy: compact labels, readable task copy, and tabular progress metadata.",
            "Material: Use borders and tonal shifts, not floating card shadows, to distinguish active, complete, and blocked stages.",
            "Composition: Counter the strict progress rail with a generous task canvas; keep help visibly subordinate.",
        ),
        relevance={"form-flow": 8, "generic-page": 2},
    ),
    _Strategy(
        id="object-workspace",
        name="Object-Centered Workspace",
        fingerprint={
            "topology": "master-detail",
            "navigation": "object-index",
            "component_partition": "domain-panels",
            "primary_action": "context-toolbar",
            "interaction": "selection-inspection",
            "responsive": "drill-in",
            "density": "dense",
        },
        layout_tree=(
            "ObjectIndex",
            "PrimaryWorkspace",
            "InspectorPanel",
            "ContextToolbar",
        ),
        component_architecture=(
            "WorkspaceShell owns selection, filtering, and navigation state.",
            "Domain panels render object-specific capabilities.",
            "InspectorPanel exposes secondary metadata and actions.",
        ),
        interaction_model="Select an object, inspect its state, then act through contextual controls.",
        responsive_rules=(
            "Convert master-detail columns into list-to-detail navigation on mobile.",
            "Preserve selected object in the URL or navigation state.",
            "Collapse InspectorPanel after primary content, never before it.",
        ),
        migration_steps=(
            "Define the domain object represented by each current route or region.",
            "Build WorkspaceShell around existing object views.",
            "Consolidate distributed actions into the contextual toolbar.",
        ),
        creative_direction=(
            "Visual language: Analytical workshop with a stable object index, dominant work surface, and precise state cues.",
            "Typography: Pair compact operational labels with readable object titles and tabular numeric data using existing type tokens.",
            "Material: Connect panels through shared baselines and dividers; reserve elevation for transient overlays.",
            "Composition: Hold a deliberate three-part asymmetry: narrow index, expansive workspace, concise inspector.",
        ),
        relevance={"data-workspace": 10, "generic-page": 3},
    ),
    _Strategy(
        id="editorial-narrative",
        name="Editorial Narrative",
        fingerprint={
            "topology": "chaptered-scroll",
            "navigation": "section-index",
            "component_partition": "story-sections",
            "primary_action": "inline-decision",
            "interaction": "progressive-disclosure",
            "responsive": "reading-flow",
            "density": "spacious",
        },
        layout_tree=(
            "OpeningThesis",
            "EvidenceChapters",
            "InlineDecisions",
            "ClosingAction",
        ),
        component_architecture=(
            "NarrativeShell controls rhythm, anchors, and reading progress.",
            "Story sections combine content, evidence, and one local action.",
            "Disclosure modules defer secondary detail until requested.",
        ),
        interaction_model="Reveal evidence in narrative order; place decisions beside their context.",
        responsive_rules=(
            "Preserve reading order across every viewport.",
            "Turn the section index into a compact sticky progress control.",
            "Keep media and evidence full-bleed only when labels remain adjacent.",
        ),
        migration_steps=(
            "Rank current regions by user question and evidence value.",
            "Recompose existing content into chapters without changing contracts.",
            "Move global calls to action beside the evidence that motivates them.",
        ),
        creative_direction=(
            "Visual language: Authored editorial rhythm with an explicit thesis, evidence-led chapters, and decisions placed beside context.",
            "Typography: Build contrast from the existing type system through scale, measure, and cadence, not decorative font proliferation.",
            "Material: Prefer rules, captions, and selective media fields over repeated cards or ornamental containers.",
            "Composition: Alternate contained reading widths with evidence moments; vary chapter length while preserving a clear narrative spine.",
        ),
        relevance={"sectioned-landing": 10, "editorial": 9, "generic-page": 4},
    ),
    _Strategy(
        id="spatial-canvas",
        name="Spatial Canvas",
        fingerprint={
            "topology": "spatial-canvas",
            "navigation": "zoom-pan-minimap",
            "component_partition": "movable-objects",
            "primary_action": "direct-manipulation",
            "interaction": "canvas-direct",
            "responsive": "mode-switch",
            "density": "adaptive",
        },
        layout_tree=("Canvas", "ObjectClusters", "SelectionLens", "CommandDock"),
        component_architecture=(
            "CanvasShell owns viewport, selection, and spatial persistence.",
            "Object modules expose position-independent content and actions.",
            "SelectionLens supplies details without permanent panel chrome.",
        ),
        interaction_model="Navigate spatial relationships; act directly on selected objects.",
        responsive_rules=(
            "Switch to ordered cluster navigation when precision pointing is unavailable.",
            "Expose every canvas action through keyboard and linear alternatives.",
            "Persist viewport state only when it helps users resume work.",
        ),
        migration_steps=(
            "Identify content whose relationships carry meaning beyond sequence.",
            "Wrap existing views as position-independent object modules.",
            "Add linear and keyboard modes before enabling free spatial navigation.",
        ),
        creative_direction=(
            "Visual language: Diagrammatic workspace where proximity and grouping communicate relationships before decoration.",
            "Typography: Use compact object labels and zoom-stable annotations; keep detailed prose in the selection lens.",
            "Material: Establish one quiet canvas plane, using connectors and selection halos only when they encode state or relationship.",
            "Composition: Arrange asymmetric clusters with meaningful negative space and preserve a complete linear fallback.",
        ),
        relevance={"data-workspace": 5, "generic-page": 1},
    ),
    _Strategy(
        id="command-console",
        name="Command-Centered Console",
        fingerprint={
            "topology": "command-centric",
            "navigation": "search-command",
            "component_partition": "capability-modules",
            "primary_action": "command-palette",
            "interaction": "keyboard-first",
            "responsive": "priority-collapse",
            "density": "compact",
        },
        layout_tree=(
            "CommandSurface",
            "RecentContext",
            "ResultWorkspace",
            "ActivityLedger",
        ),
        component_architecture=(
            "CommandRegistry owns discoverable capabilities and permissions.",
            "Capability modules declare inputs, results, and reversible actions.",
            "ActivityLedger records outcomes and supports recovery.",
        ),
        interaction_model="Search or invoke a capability, supply minimal context, inspect the result.",
        responsive_rules=(
            "Keep command discovery first at every width.",
            "Collapse secondary result panels by task priority, not source order.",
            "Provide touch-sized command alternatives without removing keyboard paths.",
        ),
        migration_steps=(
            "Inventory current actions as named capabilities with permission rules.",
            "Introduce CommandRegistry beside existing navigation.",
            "Replace duplicate action surfaces after telemetry and contract checks.",
        ),
        creative_direction=(
            "Visual language: Operational console with immediate command discovery, terse feedback, and an auditable result trail.",
            "Typography: Use concise command labels, readable result text, and the project's data or code face only where it improves scanning.",
            "Material: Keep command, result, and ledger layers flat and explicit; avoid glass effects and decorative terminal chrome.",
            "Composition: Lead with the command surface, let results expand toward evidence, and anchor history as a stable ledger.",
        ),
        relevance={"data-workspace": 6, "generic-page": 4, "form-flow": 2},
    ),
)


def propose_redesigns(
    frontend_map: FrontendMap, brief: RedesignBrief | None = None
) -> RedesignSet:
    """Return 1–5 topology-first redesigns with measured divergence."""

    active_brief = brief or RedesignBrief(target=frontend_map.target)
    if not 1 <= active_brief.variants <= len(_STRATEGIES):
        raise ValueError(f"variants must be between 1 and {len(_STRATEGIES)}")

    ranked = sorted(
        enumerate(_STRATEGIES),
        key=lambda pair: (
            -_strategy_relevance(pair[1], frontend_map, active_brief),
            pair[0],
        ),
    )
    selected = [strategy for _, strategy in ranked[: active_brief.variants]]
    proposals = tuple(
        _build_proposal(frontend_map, active_brief, strategy, index)
        for index, strategy in enumerate(selected, start=1)
    )

    pairwise: list[ProposalDistance] = []
    for left_index, left in enumerate(proposals):
        for right in proposals[left_index + 1 :]:
            score, changed = _fingerprint_distance(left.fingerprint, right.fingerprint)
            pairwise.append(
                ProposalDistance(
                    left=left.id,
                    right=right.id,
                    score=score,
                    changed_dimensions=changed,
                )
            )

    project_map = ProjectMap.from_dict(frontend_map.project_map)
    serialized_project_map = project_map.to_dict()
    contract_lineage = {
        "counts": project_map.counts,
        "findings": serialized_project_map["findings"],
        "evidence": dict(project_map.evidence),
    }
    return RedesignSet(
        schema_version=2,
        generated_at=now_iso(),
        frontend_map_generated_at=frontend_map.generated_at,
        target=active_brief.target,
        baseline_fingerprint=dict(frontend_map.fingerprint),
        brief=active_brief,
        proposals=proposals,
        pairwise_distances=tuple(pairwise),
        unknowns=frontend_map.contracts.unknown,
        contract_lineage=contract_lineage,
    )


def save_redesign_set(
    redesign_set: RedesignSet, path: str | Path | None = None
) -> Path:
    """Atomically persist a redesign set and return its path."""

    if path is None:
        ensure_uidetox_dir()
        output_path = get_uidetox_dir() / REDESIGN_SET_FILE
    else:
        output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f"{output_path.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(redesign_set.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise
    return output_path


def load_redesign_set(path: str | Path | None = None) -> RedesignSet:
    """Load a persisted redesign set, validating its schema."""

    input_path = (
        get_uidetox_dir() / REDESIGN_SET_FILE
        if path is None
        else Path(path).expanduser().resolve()
    )
    return RedesignSet.from_dict(_load_json_object(input_path, "Redesign artifact"))


_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


def _ground_creative_direction(
    frontend_map: FrontendMap,
    strategy: _Strategy,
) -> tuple[str, ...]:
    palette: list[str] = []

    def validated_color(value: object) -> str:
        text = str(value or "").strip().lower()
        color = normalize_rendered_color(text) if len(text) <= 80 else None
        return text if color is not None and color[3] > 0.05 else ""

    token_colors: list[tuple[tuple[str, ...], str]] = []
    for node in frontend_map.nodes:
        if node.kind == "token":
            color = validated_color(node.metadata.get("value"))
            if color:
                token_colors.append(
                    (tuple(node.name.lower().strip("-").split("-")), color)
                )
    for role in (
        ("paper", "background", "canvas", "surface"),
        ("ink", "foreground", "text"),
        ("accent", "brand", "primary"),
    ):
        color = next(
            (
                value
                for keyword in role
                for parts, value in token_colors
                if keyword in parts and value not in palette
            ),
            "",
        )
        if color:
            palette.append(color)
    for _, color in token_colors:
        if len(palette) >= 3:
            break
        if color not in palette:
            palette.append(color)

    font_models: set[str] = set()
    radii: list[float] = []
    for node in frontend_map.nodes:
        if not node.kind.startswith("runtime_") or node.kind == "runtime_page":
            continue
        styles = node.metadata.get("styles", {})
        if not isinstance(styles, dict):
            continue
        family = str(styles.get("fontFamily", "")).lower()
        if "monospace" in family:
            font_models.add("monospace")
        if "sans-serif" in family:
            font_models.add("sans-serif")
        elif "serif" in family:
            font_models.add("serif")
        radius = str(styles.get("borderRadius", "")).strip().lower()
        if radius.endswith("px"):
            try:
                radii.append(max(0.0, float(radius.removesuffix("px"))))
            except ValueError:
                pass
        if len(palette) < 3:
            for style_name in ("color", "backgroundColor"):
                color = validated_color(styles.get(style_name))
                if color and color not in palette:
                    palette.append(color)

    palette_evidence = (
        f"Mapped palette anchors: {', '.join(palette[:3])}."
        if palette
        else "No validated palette anchors mapped; preserve existing color relationships until capture."
    )
    if {"sans-serif", "monospace"} <= font_models:
        typography_evidence = (
            "Mapped type split: sans-serif interface + monospace data."
        )
    elif {"serif", "monospace"} <= font_models:
        typography_evidence = "Mapped type split: serif narrative + monospace data."
    elif font_models:
        typography_evidence = f"Mapped type model: {next(iter(sorted(font_models)))}."
    else:
        typography_evidence = "No reliable runtime type evidence; retain existing type tokens until capture."
    if radii and sum(radius <= 4 for radius in radii) / len(radii) >= 0.7:
        material_evidence = "Mapped geometry: square or low-radius surfaces dominate."
    elif radii:
        material_evidence = "Mapped geometry: rounded surfaces dominate; keep radius hierarchy intentional."
    else:
        material_evidence = "No reliable runtime surface geometry; preserve existing material cues until capture."

    base = {
        item.partition(":")[0]: item.partition(":")[2].strip()
        for item in strategy.creative_direction
    }
    density = str(frontend_map.fingerprint.get("density", "unknown"))
    return (
        f"Visual language: {base['Visual language']} {palette_evidence}",
        f"Typography: {base['Typography']} {typography_evidence}",
        f"Material: {base['Material']} {material_evidence}",
        f"Composition: {base['Composition']} Baseline density is {density}; target {strategy.fingerprint['density']} through grouping and whitespace, not smaller type.",
    )


def _experience_state_plan(
    frontend_map: FrontendMap,
    start_order: int,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    unreliable_owners: dict[tuple[str, str], str] = {}
    problem_priority = {"unknown": 0, "invalid": 1, "contradictory": 2}

    def mark_unreliable(owner_key: tuple[str, str], status: str) -> None:
        current = unreliable_owners.get(owner_key)
        if current is None or problem_priority[status] > problem_priority[current]:
            unreliable_owners[owner_key] = status

    for node in frontend_map.nodes:
        metadata = node.metadata
        if (
            node.kind != "data"
            or not node.file
            or not isinstance(metadata, dict)
            or not metadata.get("ui_required")
        ):
            continue
        owner = str(metadata.get("ui_owner") or metadata.get("owner") or node.name)
        owner_key = (node.file, owner)
        lifecycle = metadata.get("ui_lifecycle_evidence")
        if lifecycle in {"unknown", "contradictory"}:
            mark_unreliable(owner_key, lifecycle)
            continue
        if lifecycle not in {"present", "absent"}:
            mark_unreliable(owner_key, "invalid")
            continue
        observed_states = normalize_experience_states(metadata.get("ui_states", ()))
        if observed_states is None:
            mark_unreliable(owner_key, "invalid")
            continue
        if (lifecycle == "present") != bool(observed_states):
            unreliable_owners[owner_key] = "contradictory"
            continue
        method = str(metadata.get("method") or "GET").strip().upper() or "GET"
        inferred_mutation = method not in {"GET", "HEAD", "OPTIONS"}
        mutation_evidence = metadata.get("mutation")
        if mutation_evidence is None:
            mutation = inferred_mutation
        elif not isinstance(mutation_evidence, bool):
            mark_unreliable(owner_key, "invalid")
            continue
        elif mutation_evidence != inferred_mutation:
            unreliable_owners[owner_key] = "contradictory"
            continue
        else:
            mutation = mutation_evidence
        group = groups.setdefault(
            owner_key,
            {"observed": set(), "required": set(), "operations": set()},
        )
        group["observed"].update(observed_states)
        group["required"].update(required_experience_states(mutation=mutation))
        group["operations"].add((method, str(node.name)))

    plan: list[dict[str, Any]] = []
    for (source_module, owner), group in sorted(groups.items()):
        if (source_module, owner) in unreliable_owners:
            continue
        observed_states = [
            state for state in EXPERIENCE_STATE_ORDER if state in group["observed"]
        ]
        required_states = [
            state for state in EXPERIENCE_STATE_ORDER if state in group["required"]
        ]
        missing_states = [
            state for state in required_states if state not in group["observed"]
        ]
        if not missing_states:
            continue
        state_label = _experience_state_label(missing_states)
        behavior = "; ".join(
            f"{state}: {EXPERIENCE_STATE_BEHAVIOR[state]}" for state in missing_states
        )
        plan.append(
            {
                "order": start_order + len(plan),
                "kind": "experience-state",
                "modules": [source_module],
                "owner": owner,
                "operations": [
                    {"method": method, "path": path}
                    for method, path in sorted(group["operations"])
                ],
                "observed_states": observed_states,
                "required_states": required_states,
                "missing_states": missing_states,
                "instruction": (
                    f"Implement explicit {state_label} states at the mapped UI owner "
                    f"without changing its data contract: {behavior}."
                ),
                "evidence": "proven frontend-map UI lifecycle gap",
            }
        )
    blockers = tuple(
        f"Experience-state evidence is {status} for {owner} in {source_module}; "
        "inspect that owner before declaring states missing."
        for (source_module, owner), status in sorted(unreliable_owners.items())
    )
    return tuple(plan), blockers


def _experience_state_label(states: list[str]) -> str:
    return (
        states[0] if len(states) == 1 else f"{', '.join(states[:-1])} and {states[-1]}"
    )


def _operation_obligation_plan(
    frontend_map: FrontendMap,
    start_order: int,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Project measured operation findings onto existing lifecycle states."""

    project_map = ProjectMap.from_dict(frontend_map.project_map)
    owners: dict[tuple[str, str, str], tuple[str, str]] = {}
    for node in frontend_map.nodes:
        metadata = node.metadata
        if node.kind != "data" or not node.file or not isinstance(metadata, dict):
            continue
        method = str(metadata.get("method") or "GET").strip().upper() or "GET"
        owner = str(metadata.get("ui_owner") or metadata.get("owner") or node.name)
        owners[(node.file, method, str(node.name))] = (node.file, owner)

    plan: list[dict[str, Any]] = []
    blockers: list[str] = []
    findings = sorted(
        project_map.findings,
        key=lambda finding: (
            finding.normalized_path,
            str(finding.contract_anchor.get("method", "")),
            str(finding.contract_anchor.get("field", "")),
            finding.detector_id,
        ),
    )
    for finding in findings:
        if finding.detector_id not in {
            "contract-operation-obligation-missing",
            "contract-operation-obligation-mismatch",
        }:
            continue
        applicability = finding.evidence.get("applicability", {})
        if (
            finding.status != "pending"
            or finding.evidence.get("basis") != "measured"
            or not isinstance(applicability, Mapping)
            or applicability.get("status") != "applicable"
        ):
            continue
        obligation = str(finding.contract_anchor.get("field", ""))
        states = _OPERATION_OBLIGATION_STATES.get(obligation)
        if not states:
            blockers.append(
                f"Applicable operation obligation {obligation or 'unknown'} has no "
                "truthful canonical lifecycle projection."
            )
            continue
        method = str(finding.contract_anchor.get("method", "")).upper()
        path = finding.normalized_path
        source_path = str(finding.source_anchor.get("path", ""))
        source_owner = owners.get((source_path, method, path))
        if source_owner is None:
            blockers.append(
                f"Applicable {obligation} obligation for {method} {path} has no exact "
                "mapped UI owner."
            )
            continue
        source_module, owner = source_owner
        expected = finding.evidence.get("expected")
        plan.append(
            {
                "order": start_order + len(plan),
                "kind": "operation-obligation",
                "modules": [source_module],
                "owner": owner,
                "operations": [{"method": method, "path": path}],
                "obligation": obligation,
                "states": list(states),
                "contract_anchor": dict(finding.contract_anchor),
                "evidence_basis": "measured",
                "applicability": "applicable",
                "constraints": [str(expected)] if expected is not None else [],
                "instruction": (
                    f"For {method} {path} at {owner}, express {obligation} through "
                    f"existing {'/'.join(states)} state behavior: "
                    f"{_OPERATION_OBLIGATION_ACTIONS[obligation]}."
                ),
                "evidence": finding.detector_id,
            }
        )
    return tuple(plan), tuple(dict.fromkeys(blockers))


def _runtime_remediation_plan(
    frontend_map: FrontendMap,
    start_order: int,
) -> tuple[dict[str, Any], ...]:
    if frontend_map.evidence.get("runtime_status") not in {
        "current",
        "partial",
        "degraded",
    }:
        return ()
    findings = frontend_map.evidence.get("runtime_findings", ())
    if not isinstance(findings, (list, tuple)):
        return ()

    source_targets: dict[tuple[str, str], set[str]] = {}
    for node in frontend_map.nodes:
        metadata = node.metadata
        if not isinstance(metadata, dict):
            continue
        capture_id = str(metadata.get("capture_id", ""))
        selector = str(metadata.get("selector", ""))
        targets = metadata.get("source_targets", ())
        if capture_id and selector and isinstance(targets, (list, tuple)):
            source_targets.setdefault((capture_id, selector), set()).update(
                str(target) for target in targets if target
            )

    grouped: dict[str, list[tuple[dict[str, Any], Any]]] = {}
    for row in findings:
        if not isinstance(row, dict):
            continue
        finding = coerce_finding(row)
        detector_id = finding.detector_id
        selector = str(row.get("selector", "")).strip()
        if detector_id and selector and not detector_id.startswith("browser-"):
            grouped.setdefault(detector_id, []).append((row, finding))

    plan: list[dict[str, Any]] = []
    for offset, detector_id in enumerate(sorted(grouped)):
        rows = grouped[detector_id]
        categories = tuple(
            sorted({finding.category for _, finding in rows if finding.category})
        )
        constraints: list[str] = []
        for _, finding in rows:
            raw_constraints = finding.evidence.get("remediation_constraints", ())
            if isinstance(raw_constraints, (list, tuple)):
                constraints.extend(
                    str(constraint).strip()
                    for constraint in raw_constraints
                    if str(constraint).strip()
                )
        remediation_constraints = tuple(dict.fromkeys(constraints))
        severity = max(
            (finding.severity for _, finding in rows),
            key=lambda value: _SEVERITY_ORDER.get(value, -1),
        )
        anchors_by_key: dict[tuple[str, ...], dict[str, str]] = {}
        modules: set[str] = set()
        for row, _ in rows:
            anchor = {
                key: str(row.get(key, ""))
                for key in (
                    "url",
                    "viewport",
                    "scenario",
                    "state",
                    "capture_id",
                    "selector",
                )
            }
            anchor_key = tuple(anchor.values())
            anchors_by_key[anchor_key] = anchor
            modules.update(
                source_targets.get((anchor["capture_id"], anchor["selector"]), ())
            )
        requires_review = not remediation_constraints
        plan.append(
            {
                "order": start_order + offset,
                "kind": "runtime-review" if requires_review else "runtime-finding",
                "modules": sorted(modules),
                "detector_id": detector_id,
                "category": ", ".join(categories) or "ui",
                "severity": severity,
                "finding_count": len(rows),
                "instruction": (
                    "Investigate the current detector evidence and define bounded "
                    "detector-owned remediation constraints before source changes."
                    if requires_review
                    else " ".join(remediation_constraints)
                ),
                "anchors": [anchors_by_key[key] for key in sorted(anchors_by_key)],
                "evidence": (
                    "current frontend-map runtime finding lacks remediation constraints"
                    if requires_review
                    else "current frontend-map runtime findings"
                ),
            }
        )
    return tuple(plan)


def _build_proposal(
    frontend_map: FrontendMap,
    brief: RedesignBrief,
    strategy: _Strategy,
    index: int,
) -> RedesignProposal:
    fingerprint = _proposal_fingerprint(strategy, brief)
    novelty, _ = _fingerprint_distance(frontend_map.fingerprint, fingerprint)
    counts = frontend_map.fingerprint.get("node_counts", {})
    component_count = int(counts.get("component", 0))
    route_count = int(counts.get("route", 0))
    action_count = int(counts.get("action", 0))
    data_count = int(counts.get("data", 0))
    baseline = frontend_map.fingerprint.get("topology", "unknown")
    source_evidence = _source_module_evidence(frontend_map)
    source_targets = tuple(item["file"] for item in source_evidence)
    migration_plan, dependency_blockers = _dependency_migration_plan(
        frontend_map,
        source_targets,
        strategy.migration_steps,
    )
    evidence_freshness = _proposal_evidence_freshness(frontend_map)
    experience_state_plan, experience_state_blockers = _experience_state_plan(
        frontend_map,
        len(migration_plan) + 1,
    )
    operation_plan, operation_blockers = _operation_obligation_plan(
        frontend_map,
        len(migration_plan) + len(experience_state_plan) + 1,
    )
    runtime_remediation = _runtime_remediation_plan(
        frontend_map,
        len(migration_plan) + len(experience_state_plan) + len(operation_plan) + 1,
    )
    migration_plan += experience_state_plan + operation_plan + runtime_remediation
    contract_blockers = _contract_blockers(frontend_map)
    preserved = tuple(
        dict.fromkeys(
            frontend_map.contracts.must_preserve
            + brief.preserve
            + brief.intent.preserve
        )
    )
    preserved_contract_evidence = _preserved_contract_evidence(
        frontend_map,
        preserved,
        brief,
        evidence_freshness["runtime"]["status"],
    )
    feasibility_blockers = tuple(
        dict.fromkeys(
            dependency_blockers
            + contract_blockers
            + experience_state_blockers
            + operation_blockers
            + (
                (
                    "Runtime evidence is stale and cannot validate this proposal."
                    if evidence_freshness["runtime"]["status"] == "stale"
                    else ""
                ),
            )
        )
    )
    feasibility_blockers = tuple(item for item in feasibility_blockers if item)
    observable_checks = (
        _observable_acceptance_checks(
            preserved_contract_evidence,
            evidence_freshness,
            contract_blockers,
            brief,
        )
        + tuple(
            f"Experience-state check: {_experience_state_label(item['missing_states'])} "
            f"{'is' if len(item['missing_states']) == 1 else 'are'} represented for "
            f"mapped UI owner {item['owner']} without contract drift."
            for item in experience_state_plan
        )
        + tuple(
            f"Operation contract check: {item['obligation']} behavior for "
            f"{item['operations'][0]['method']} {item['operations'][0]['path']} is "
            f"observable through existing {'/'.join(item['states'])} states at "
            f"{item['owner']}."
            for item in operation_plan
        )
        + tuple(
            (
                f"Runtime remediation review: {item['detector_id']} lacks "
                "detector-owned remediation constraints; investigate before source "
                "changes."
                if item["kind"] == "runtime-review"
                else f"Runtime remediation check: {item['detector_id']} is absent from "
                f"fresh captures across {item['finding_count']} mapped occurrence(s)."
            )
            for item in runtime_remediation
        )
    )
    density_instruction = _density_instruction(brief.visual_density)
    motion_instruction = _motion_instruction(brief.motion_intensity)
    layout_tree = _dialed_layout_tree(strategy.layout_tree, brief)
    component_architecture = strategy.component_architecture + (
        f"DesignIntentBoundary owns the {brief.intent.genre} contract for {brief.intent.audience}.",
    )
    responsive_rules = strategy.responsive_rules + (
        _responsive_density_rule(brief.visual_density),
    )
    interaction_model = (
        f"{strategy.interaction_model} {_motion_model(brief.motion_intensity)}"
    )
    goal_source = brief.intent.provenance.get("product_goal", "fallback")
    goal_confidence = brief.intent.confidence.get("product_goal", 0.0)
    remediation_summary = ()
    if runtime_remediation:
        finding_count = sum(int(item["finding_count"]) for item in runtime_remediation)
        family_count = len(runtime_remediation)
        family_label = "family" if family_count == 1 else "families"
        remediation_summary = (
            (
                f"Resolve {finding_count} current runtime findings across "
                f"{family_count} detector {family_label}."
            ),
        )
    experience_summary = ()
    if experience_state_plan:
        missing_state_count = sum(
            len(item["missing_states"]) for item in experience_state_plan
        )
        owner_count = len(experience_state_plan)
        owner_label = "owner" if owner_count == 1 else "owners"
        experience_summary = (
            (
                f"Complete {missing_state_count} missing experience states across "
                f"{owner_count} mapped UI {owner_label}."
            ),
        )
    creative_direction = _ground_creative_direction(frontend_map, strategy)

    return RedesignProposal(
        id=f"REDESIGN-{index:02d}-{strategy.id}",
        name=strategy.name,
        strategy=strategy.id,
        rationale=(
            f"Replace baseline {baseline} topology with {strategy.fingerprint['topology']}. "
            f"Map contains {component_count} components, {route_count} routes, "
            f"{action_count} actions, and {data_count} data sources. "
            f"Product goal ({goal_source}, {goal_confidence:.2f} confidence): "
            f"{brief.intent.product_goal}. "
            f"Preflight: {brief.intent.page_kind} for {brief.intent.audience}; "
            f"primary job is to {brief.intent.primary_job}."
        ),
        layout_tree=layout_tree,
        component_architecture=component_architecture,
        interaction_model=interaction_model,
        responsive_rules=responsive_rules,
        changes=(
            f"Recompose {component_count} mapped components around {strategy.fingerprint['component_partition']} ownership.",
            f"Replace {frontend_map.fingerprint.get('navigation', 'unknown')} navigation with {strategy.fingerprint['navigation']}.",
            f"Move primary actions from {frontend_map.fingerprint.get('primary_action', 'unknown')} placement to {strategy.fingerprint['primary_action']}.",
            density_instruction,
            motion_instruction,
        )
        + experience_summary
        + remediation_summary
        + creative_direction,
        preserved_contracts=preserved,
        migration_steps=tuple(str(item["instruction"]) for item in migration_plan),
        acceptance_checks=observable_checks,
        source_targets=source_targets,
        fingerprint=fingerprint,
        novelty_score=novelty,
        source_evidence=source_evidence,
        migration_plan=migration_plan,
        preserved_contract_evidence=preserved_contract_evidence,
        feasibility_blockers=feasibility_blockers,
        evidence_freshness=evidence_freshness,
        observable_checks=observable_checks,
    )


def _source_module_evidence(
    frontend_map: FrontendMap,
) -> tuple[dict[str, Any], ...]:
    file_by_id = {
        node.id: node.file
        for node in frontend_map.nodes
        if node.kind == "file" and node.file
    }
    dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = {}
    for edge in frontend_map.edges:
        if edge.kind != "imports":
            continue
        source = file_by_id.get(edge.source)
        target = file_by_id.get(edge.target)
        if not source or not target:
            continue
        dependencies.setdefault(source, set()).add(target)
        dependents.setdefault(target, set()).add(source)

    owned = {
        node.file
        for node in frontend_map.nodes
        if node.file and node.kind == "component"
    }
    if not owned:
        owned = {
            node.file
            for node in frontend_map.nodes
            if node.file and node.kind in {"action", "data", "region", "route", "state"}
        }
    selected = set(owned)
    pending = sorted(owned)
    while pending:
        current = pending.pop()
        for dependency in sorted(dependencies.get(current, ())):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)

    evidence: list[dict[str, Any]] = []
    for file in sorted(selected):
        concepts = sorted(
            {
                f"{node.kind}:{node.name}"
                for node in frontend_map.nodes
                if node.file == file and node.kind != "file"
            }
        )
        reasons: list[str] = []
        if file in owned:
            reasons.append("owns mapped UI behavior or components")
        if dependencies.get(file):
            reasons.append("depends on mapped source modules")
        if dependents.get(file):
            reasons.append("is consumed by mapped source modules")
        evidence.append(
            {
                "file": file,
                "reasons": reasons or ["anchors mapped source evidence"],
                "concepts": concepts,
                "dependencies": sorted(dependencies.get(file, ())),
                "dependents": sorted(dependents.get(file, ())),
            }
        )
    return tuple(evidence)


def _dependency_migration_plan(
    frontend_map: FrontendMap,
    source_targets: tuple[str, ...],
    strategy_steps: tuple[str, ...],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    file_by_id = {
        node.id: node.file
        for node in frontend_map.nodes
        if node.kind == "file" and node.file in source_targets
    }
    dependencies = {file: set() for file in source_targets}
    for edge in frontend_map.edges:
        if edge.kind != "imports":
            continue
        source = file_by_id.get(edge.source)
        target = file_by_id.get(edge.target)
        if source and target:
            dependencies[source].add(target)

    remaining = set(source_targets)
    plan: list[dict[str, Any]] = []
    blockers: list[str] = []
    order = 1
    while remaining:
        ready = sorted(
            file
            for file in remaining
            if not (dependencies.get(file, set()) & remaining)
        )
        if ready:
            for file in ready:
                plan.append(
                    {
                        "order": order,
                        "kind": "module",
                        "modules": [file],
                        "instruction": (
                            f"Update {file} after its mapped dependencies are stable."
                        ),
                        "evidence": "frontend-map imports edges",
                    }
                )
                order += 1
                remaining.remove(file)
            continue

        components = _strongly_connected_components(
            remaining,
            dependencies,
        )
        cycle = next(
            (
                component
                for component in components
                if len(component) > 1
                or component[0] in dependencies.get(component[0], set())
            ),
            tuple(sorted(remaining)),
        )
        modules = list(cycle)
        plan.append(
            {
                "order": order,
                "kind": "cycle",
                "modules": modules,
                "instruction": (
                    "Migrate this dependency cycle as one coordinated step: "
                    + ", ".join(modules)
                    + "."
                ),
                "evidence": "cyclic frontend-map imports edges",
            }
        )
        blockers.append(
            "Dependency cycle requires coordinated migration: "
            + ", ".join(modules)
            + "."
        )
        order += 1
        remaining.difference_update(cycle)

    for instruction in strategy_steps:
        plan.append(
            {
                "order": order,
                "kind": "strategy",
                "modules": list(source_targets),
                "instruction": instruction,
                "evidence": "selected topology strategy",
            }
        )
        order += 1
    return tuple(plan), tuple(blockers)


def _strongly_connected_components(
    modules: set[str],
    dependencies: dict[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(module: str) -> None:
        nonlocal index
        indexes[module] = index
        lowlinks[module] = index
        index += 1
        stack.append(module)
        on_stack.add(module)
        for dependency in sorted(dependencies.get(module, ()) & modules):
            if dependency not in indexes:
                visit(dependency)
                lowlinks[module] = min(lowlinks[module], lowlinks[dependency])
            elif dependency in on_stack:
                lowlinks[module] = min(lowlinks[module], indexes[dependency])
        if lowlinks[module] != indexes[module]:
            return
        component: list[str] = []
        while stack:
            candidate = stack.pop()
            on_stack.remove(candidate)
            component.append(candidate)
            if candidate == module:
                break
        components.append(tuple(sorted(component)))

    for module in sorted(modules):
        if module not in indexes:
            visit(module)
    return tuple(sorted(components))


def _proposal_evidence_freshness(frontend_map: FrontendMap) -> dict[str, Any]:
    evidence = frontend_map.evidence
    source_status = str(evidence.get("source_status", "current"))
    if source_status == "current" and not frontend_map_is_fresh(frontend_map):
        source_status = "stale"
    runtime_status = str(
        evidence.get(
            "runtime_status",
            "current" if evidence.get("runtime_observed") else "absent",
        )
    )
    stale_reason = evidence.get("runtime_stale_reason")
    if source_status == "stale" and runtime_status == "current":
        runtime_status = "stale"
        stale_reason = "Mapped source changed after the runtime observation."
    runtime_handoff_evidence = json.loads(
        json.dumps(
            {
                "runtime_capture_matrix": evidence.get("runtime_capture_matrix", []),
                "runtime_diagnostics": evidence.get("runtime_diagnostics", []),
                "runtime_coverage": evidence.get("runtime_coverage", {}),
                "runtime_semantic_coverage": evidence.get(
                    "runtime_semantic_coverage", {}
                ),
            },
            sort_keys=True,
        )
    )
    return {
        "source": {
            "status": source_status,
            "extractor_version": evidence.get("extractor_version"),
            "manifest": dict(evidence.get("source_manifest", {})),
        },
        "runtime": {
            "status": runtime_status,
            "generated_at": evidence.get("runtime_generated_at"),
            "urls": list(evidence.get("runtime_urls", [])),
            "viewports": list(evidence.get("runtime_viewports", [])),
            "viewport_discovery": dict(
                evidence.get("runtime_viewport_discovery") or {}
            ),
            "screenshots": list(evidence.get("runtime_screenshots", [])),
            "stale_reason": stale_reason,
            **runtime_handoff_evidence,
        },
    }


def _contract_blockers(frontend_map: FrontendMap) -> tuple[str, ...]:
    project_map = ProjectMap.from_dict(frontend_map.project_map)
    blockers: list[str] = []
    labels = {
        "frontend_only": "Add or remap the missing backend operation",
        "backend_only": "Decide whether the backend-only operation needs UI coverage",
        "method_mismatch": "Align the frontend and backend HTTP methods",
        "unresolved": "Resolve dynamic or incomplete operation evidence",
    }
    for finding in project_map.findings:
        if finding.detector_id in {
            "contract-operation-obligation-missing",
            "contract-operation-obligation-mismatch",
        }:
            continue
        blockers.append(
            f"{labels.get(finding.kind, 'Resolve contract lineage')}: "
            f"{finding.normalized_path or 'unknown path'}."
        )
    return tuple(blockers)


def _preserved_contract_evidence(
    frontend_map: FrontendMap,
    preserved: tuple[str, ...],
    brief: RedesignBrief,
    runtime_status: str,
) -> tuple[dict[str, Any], ...]:
    project_map = ProjectMap.from_dict(frontend_map.project_map)
    intent_preserve = set(brief.intent.preserve)
    brief_preserve = set(brief.preserve)
    source_index: dict[str, tuple[set[str], set[str]]] = {}

    def add(contract: str, file: str, provenance: str) -> None:
        if not file:
            return
        modules, evidence = source_index.setdefault(contract, (set(), set()))
        modules.add(file)
        evidence.add(provenance)

    for node in frontend_map.nodes:
        contract = preservation_contract(node)
        if contract:
            add(contract, node.file, f"frontend-map:{node.kind}:{node.id}")

    for node in project_map.nodes:
        if node.side != "frontend" or node.kind != "client_operation":
            continue
        path = str(node.attributes.get("path", ""))
        contract = f"Data contract remains functional: {path}"
        add(contract, node.source.file, f"project-map:{node.kind}:{node.id}")

    records: list[dict[str, Any]] = []
    for contract in preserved:
        modules, provenance = source_index.get(contract, (set(), set()))
        if modules:
            source_status = "mapped"
        elif contract in intent_preserve:
            source_status = "intent"
            provenance = tuple(brief.intent.evidence.get("preserve", ()))
        elif contract in brief_preserve:
            source_status = "intent"
            provenance = ("redesign-brief:preserve",)
        else:
            source_status = "unresolved"
        records.append(
            {
                "contract": contract,
                "source_modules": sorted(modules),
                "source_status": source_status,
                "provenance": sorted(provenance),
                "runtime_status": runtime_status,
            }
        )
    return tuple(records)


def _observable_acceptance_checks(
    preserved_contract_evidence: tuple[dict[str, Any], ...],
    freshness: dict[str, Any],
    contract_blockers: tuple[str, ...],
    brief: RedesignBrief,
) -> tuple[str, ...]:
    checks: list[str] = []
    for evidence in preserved_contract_evidence:
        contract = str(evidence["contract"])
        modules = ", ".join(evidence["source_modules"])
        provenance = ", ".join(evidence["provenance"])
        if modules:
            checks.append(f"Source check: {contract} remains represented in {modules}.")
        elif evidence["source_status"] == "intent":
            checks.append(
                f"Intent check: {contract} remains preserved per "
                f"{provenance or 'explicit intent'}."
            )
        else:
            checks.append(
                f"Evidence gap: resolve a source anchor for {contract} "
                "before implementation."
            )
    checks.append(
        "Source check: rerun `uidetox map` and confirm the source manifest is current."
    )
    if freshness["runtime"]["status"] == "current":
        urls = ", ".join(freshness["runtime"]["urls"]) or "the mapped runtime URLs"
        checks.append(
            f"Runtime check: recapture {urls} at the recorded viewports and compare behavior."
        )
    for blocker in contract_blockers:
        checks.append(
            "Contract lineage check: rerun `uidetox map` and confirm resolved finding — "
            + blocker
        )
    checks.extend(
        f"Constraint check in source or runtime evidence: {constraint}"
        for constraint in brief.intent.constraints
    )
    goal_source = brief.intent.provenance.get("product_goal", "fallback")
    if goal_source == "explicit":
        checks.append(
            "Intent check: validate the proposal against the user-confirmed "
            f"product goal — {brief.intent.product_goal}"
        )
    else:
        checks.append(
            f"Intent gate: confirm the {goal_source} product goal before "
            f"implementation — {brief.intent.product_goal}"
        )
    return tuple(dict.fromkeys(checks))


def _strategy_relevance(
    strategy: _Strategy, frontend_map: FrontendMap, brief: RedesignBrief
) -> int:
    baseline = str(frontend_map.fingerprint.get("topology", "generic-page"))
    score = strategy.relevance.get(baseline, 0)
    signals = frontend_map.fingerprint.get("signals", {})
    if strategy.id == "task-flow" and signals.get("form", 0):
        score += 5
    if strategy.id == "object-workspace" and (
        signals.get("table", 0) or signals.get("chart", 0)
    ):
        score += 5
    if strategy.id == "editorial-narrative" and signals.get("section", 0) >= 3:
        score += 5
    if strategy.id == "spatial-canvas":
        score += max(0, brief.design_variance - 7)
    if strategy.id == "command-console":
        action_count = frontend_map.fingerprint.get("node_counts", {}).get("action", 0)
        score += min(5, int(action_count))
    if strategy.id == "task-flow":
        score += _intent_signal_score(
            brief.intent, ("complete", "submit", "workflow", "task")
        )
    if strategy.id == "editorial-narrative":
        score += _intent_signal_score(
            brief.intent, ("editorial", "story", "read", "narrative")
        )
    if strategy.id == "object-workspace":
        score += _intent_signal_score(
            brief.intent, ("inspect", "compare", "manage", "workspace")
        )
    if strategy.id == "command-console":
        score += _intent_signal_score(
            brief.intent, ("expert", "operator", "power user")
        )
    return score


def _intent_signal_score(intent: DesignIntent, tokens: tuple[str, ...]) -> int:
    """Weight topology signals by field-level provenance confidence."""

    best_confidence = 0.0
    for field_name in ("product_goal", "primary_job", "genre", "audience"):
        value = str(getattr(intent, field_name, "")).lower()
        if any(token in value for token in tokens):
            best_confidence = max(
                best_confidence,
                intent.confidence.get(field_name, 0.0),
            )
    return round(4 * best_confidence)


def _fingerprint_distance(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[int, tuple[str, ...]]:
    changed = tuple(key for key in _DISTANCE_KEYS if left.get(key) != right.get(key))
    return round(len(changed) / len(_DISTANCE_KEYS) * 100), changed


def _proposal_fingerprint(strategy: _Strategy, brief: RedesignBrief) -> dict[str, str]:
    fingerprint = dict(strategy.fingerprint)
    fingerprint.update(
        {
            "composition": (
                "aligned-grid"
                if brief.design_variance <= 3
                else "asymmetric-zones"
                if brief.design_variance >= 8
                else "offset-grid"
            ),
            "motion_model": (
                "state-only"
                if brief.motion_intensity <= 3
                else "spatial-choreography"
                if brief.motion_intensity >= 8
                else "transition-choreography"
            ),
            "density_model": (
                "progressive-disclosure"
                if brief.visual_density <= 3
                else "simultaneous-overview"
                if brief.visual_density >= 8
                else "layered-overview"
            ),
            "intent_genre": _dimension(brief.intent.genre),
            "page_kind": _dimension(brief.intent.page_kind),
        }
    )
    return fingerprint


def _dialed_layout_tree(
    layout_tree: tuple[str, ...], brief: RedesignBrief
) -> tuple[str, ...]:
    if brief.design_variance <= 3:
        composition = ("AlignedFrame",)
    elif brief.design_variance >= 8:
        composition = ("AsymmetricField", "ContextSatellite")
    else:
        composition = ("OffsetFrame",)
    if brief.visual_density <= 3:
        density = ("ProgressiveDisclosure",)
    elif brief.visual_density >= 8:
        density = ("PersistentUtilityRail", "CompactContextLayer")
    else:
        density = ("ContextLayer",)
    return composition[:1] + layout_tree + composition[1:] + density


def _motion_model(value: int) -> str:
    if value <= 3:
        return "Structure is static; motion only confirms direct state change."
    if value >= 8:
        return "Spatial transitions explain hierarchy changes and preserve object continuity."
    return "Short transitions preserve context between meaningful states."


def _responsive_density_rule(value: int) -> str:
    if value <= 3:
        return "Keep progressive disclosures in document order; never hide the primary job."
    if value >= 8:
        return "Collapse utility rails into ordered drawers while preserving dense desktop context."
    return (
        "Reflow context layers below the primary region without duplicating controls."
    )


def _dimension(value: str) -> str:
    normalized = "-".join(value.lower().split())
    return normalized or "unspecified"


def _density_instruction(value: int) -> str:
    if value <= 3:
        return "Use gallery-like spacing with one dominant idea per viewport."
    if value >= 8:
        return (
            "Use compact spacing and persistent context without card-grid repetition."
        )
    return "Use moderate density with clear hierarchy and intentional compression."


def _motion_instruction(value: int) -> str:
    if value <= 3:
        return "Limit motion to state transitions and direct hover/focus feedback."
    if value >= 8:
        return "Use high-intensity motion only to explain topology, causality, and spatial change."
    return "Use restrained transitions to preserve context across layout and state changes."
