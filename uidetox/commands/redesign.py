"""Redesign command: generate divergent topology-first frontend plans."""

import argparse
import json
from pathlib import Path

from uidetox.design_context import DesignSettings
from uidetox.frontend_map import (
    FRONTEND_MAP_FILE,
    frontend_map_is_fresh,
    load_frontend_map,
    map_frontend,
    save_frontend_map,
)
from uidetox.redesign import RedesignBrief, propose_redesigns, save_redesign_set
from uidetox.state import get_project_root, get_uidetox_dir, load_config


def run(args: argparse.Namespace) -> None:
    root = get_project_root()
    target = getattr(args, "target", ".")
    map_arg = getattr(args, "map_file", None)
    map_path = (
        Path(map_arg).expanduser().resolve()
        if map_arg
        else get_uidetox_dir() / FRONTEND_MAP_FILE
    )
    refresh = getattr(args, "refresh_map", False)

    if refresh or not map_path.exists():
        frontend_map = map_frontend(root, target)
        save_frontend_map(frontend_map, map_path)
    else:
        frontend_map = load_frontend_map(map_path)
        requested_target = _target_label(root, target)
        if (
            frontend_map.root != str(root.resolve())
            or frontend_map.target != requested_target
            or not frontend_map_is_fresh(frontend_map, root, target)
        ):
            frontend_map = map_frontend(root, target)
            save_frontend_map(frontend_map, map_path)

    config = load_config()
    settings = DesignSettings.from_config(config, frontend_map, frontend_map.target)
    brief = RedesignBrief(
        target=frontend_map.target,
        variants=getattr(args, "variants", 3),
        design_variance=settings.dials.design_variance,
        motion_intensity=settings.dials.motion_intensity,
        visual_density=settings.dials.visual_density,
        intent=settings.intent,
    )
    redesign_set = propose_redesigns(frontend_map, brief)
    output_arg = getattr(args, "output", None)
    output_path = save_redesign_set(
        redesign_set,
        Path(output_arg) if output_arg else None,
    )

    if getattr(args, "json", False):
        print(json.dumps(redesign_set.to_dict(), indent=2, sort_keys=True))
        return

    print(f"Generated {len(redesign_set.proposals)} divergent redesign proposal(s).")
    print(f"  Baseline: {frontend_map.fingerprint.get('topology', 'unknown')}")
    for proposal in redesign_set.proposals:
        topology = proposal.fingerprint["topology"]
        print(f"\n  {proposal.id}: {proposal.name}")
        print(f"    Topology: {topology}")
        print(f"    Novelty : {proposal.novelty_score}/100")
        print(f"    Model   : {proposal.interaction_model}")
    if redesign_set.pairwise_distances:
        minimum_distance = min(item.score for item in redesign_set.pairwise_distances)
        print(f"\n  Minimum pairwise distance: {minimum_distance}/100")
    print(f"  Artifact: {output_path}")
    if redesign_set.unknowns:
        print(
            f"  Gate    : {len(redesign_set.unknowns)} runtime unknown(s) require verification"
        )


def _target_label(root: Path, target: str | Path) -> str:
    if str(target).strip() in {"", "."}:
        return "."
    candidate = Path(target).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    return resolved.relative_to(root.resolve()).as_posix()
