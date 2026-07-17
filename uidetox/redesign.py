"""Generate structurally divergent redesign plans from a :class:`FrontendMap`."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from uidetox.design_context import DesignDials, DesignIntent
from uidetox.frontend_map import FrontendMap, frontend_map_is_fresh
from uidetox.project_map import ProjectMap
from uidetox.state import ensure_uidetox_dir, get_uidetox_dir
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
    def from_dict(cls, value: dict[str, Any]) -> "RedesignBrief":
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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RedesignProposal":
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
                dict(item)
                for item in value.get("preserved_contract_evidence", [])
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
    def from_dict(cls, value: dict[str, Any]) -> "ProposalDistance":
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
    parity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RedesignSet":
        version = int(value.get("schema_version", 0))
        if version != 1:
            raise ValueError(f"Unsupported redesign schema {version}; expected 1.")
        return cls(
            schema_version=version,
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
            parity=dict(value.get("parity", {})),
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
            "Move state ownership only after parity checks pass per step.",
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
            "Replace duplicate action surfaces after telemetry and parity checks.",
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
    parity = {
        "counts": project_map.counts,
        "findings": serialized_project_map["findings"],
        "evidence": dict(project_map.evidence),
    }
    return RedesignSet(
        schema_version=1,
        generated_at=now_iso(),
        frontend_map_generated_at=frontend_map.generated_at,
        target=active_brief.target,
        baseline_fingerprint=dict(frontend_map.fingerprint),
        brief=active_brief,
        proposals=proposals,
        pairwise_distances=tuple(pairwise),
        unknowns=frontend_map.contracts.unknown,
        parity=parity,
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
    try:
        value = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Redesign artifact not found: {input_path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Redesign artifact is unreadable: {input_path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Redesign artifact must contain a JSON object: {input_path}")
    return RedesignSet.from_dict(value)


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
    parity_blockers = _parity_blockers(frontend_map)
    preserved = tuple(
        dict.fromkeys(
            frontend_map.contracts.must_preserve
            + brief.preserve
            + brief.intent.preserve
        )
    )
    preserved_contract_evidence = tuple(
        {
            "contract": contract,
            "source_modules": list(source_targets),
            "runtime_status": evidence_freshness["runtime"]["status"],
        }
        for contract in preserved
    )
    feasibility_blockers = tuple(
        dict.fromkeys(
            dependency_blockers
            + parity_blockers
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
    observable_checks = _observable_acceptance_checks(
        preserved,
        source_targets,
        evidence_freshness,
        parity_blockers,
        brief,
    )
    acceptance_checks = observable_checks
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

    return RedesignProposal(
        id=f"REDESIGN-{index:02d}-{strategy.id}",
        name=strategy.name,
        strategy=strategy.id,
        rationale=(
            f"Replace baseline {baseline} topology with {strategy.fingerprint['topology']}. "
            f"Map contains {component_count} components, {route_count} routes, "
            f"{action_count} actions, and {data_count} data sources. "
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
        ),
        preserved_contracts=preserved,
        migration_steps=tuple(
            str(item["instruction"]) for item in migration_plan
        ),
        acceptance_checks=acceptance_checks,
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
    pending = list(sorted(owned))
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
            "screenshots": list(evidence.get("runtime_screenshots", [])),
            "stale_reason": stale_reason,
        },
    }


def _parity_blockers(frontend_map: FrontendMap) -> tuple[str, ...]:
    project_map = ProjectMap.from_dict(frontend_map.project_map)
    blockers: list[str] = []
    labels = {
        "frontend_only": "Add or remap the missing backend operation",
        "backend_only": "Decide whether the backend-only operation needs UI coverage",
        "method_mismatch": "Align the frontend and backend HTTP methods",
        "unresolved": "Resolve dynamic or incomplete operation evidence",
    }
    for finding in project_map.findings:
        blockers.append(
            f"{labels.get(finding.kind, 'Resolve operation parity')}: "
            f"{finding.normalized_path or 'unknown path'}."
        )
    return tuple(blockers)


def _observable_acceptance_checks(
    preserved: tuple[str, ...],
    source_targets: tuple[str, ...],
    freshness: dict[str, Any],
    parity_blockers: tuple[str, ...],
    brief: RedesignBrief,
) -> tuple[str, ...]:
    modules = ", ".join(source_targets) or "the mapped source modules"
    checks = [
        f"Source check: {contract} remains represented in {modules}."
        for contract in preserved
    ]
    checks.append(
        "Source check: rerun `uidetox map` and confirm the source manifest is current."
    )
    if freshness["runtime"]["status"] == "current":
        urls = ", ".join(freshness["runtime"]["urls"]) or "the mapped runtime URLs"
        checks.append(
            f"Runtime check: recapture {urls} at the recorded viewports and compare behavior."
        )
    for blocker in parity_blockers:
        checks.append(
            "Operation parity check: rerun `uidetox map` and confirm resolved finding — "
            + blocker
        )
    checks.extend(
        f"Constraint check in source or runtime evidence: {constraint}"
        for constraint in brief.intent.constraints
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
    intent_text = " ".join(
        (
            brief.intent.primary_job,
            brief.intent.genre,
            brief.intent.audience,
        )
    ).lower()
    if strategy.id == "task-flow" and any(
        token in intent_text for token in ("complete", "submit", "workflow", "task")
    ):
        score += 4
    if strategy.id == "editorial-narrative" and any(
        token in intent_text for token in ("editorial", "story", "read", "narrative")
    ):
        score += 4
    if strategy.id == "object-workspace" and any(
        token in intent_text for token in ("inspect", "compare", "manage", "workspace")
    ):
        score += 4
    if strategy.id == "command-console" and any(
        token in intent_text for token in ("expert", "operator", "power user")
    ):
        score += 4
    return score


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
