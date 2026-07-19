"""Compare command: present structural differences among redesign proposals."""

import argparse
import json
from pathlib import Path
from typing import Any

from uidetox.redesign import RedesignSet, load_redesign_set


_DIMENSIONS = (
    "topology",
    "navigation",
    "component_partition",
    "primary_action",
    "interaction",
    "responsive",
    "density",
)


def run(args: argparse.Namespace) -> None:
    file_arg = getattr(args, "redesign_file", None)
    redesign_set = load_redesign_set(Path(file_arg) if file_arg else None)
    payload = _comparison_payload(redesign_set)

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print(f"Redesign comparison for: {redesign_set.target}")
    print(
        f"  Baseline topology: {redesign_set.baseline_fingerprint.get('topology', 'unknown')}"
    )
    print(f"  Proposals        : {len(redesign_set.proposals)}")

    for proposal in redesign_set.proposals:
        print(f"\n{proposal.id}: {proposal.name}")
        print(f"  Novelty: {proposal.novelty_score}/100")
        for dimension in _DIMENSIONS:
            label = dimension.replace("_", " ").title()
            print(f"  {label:<20} {proposal.fingerprint.get(dimension, 'unknown')}")

    if redesign_set.pairwise_distances:
        print("\nPairwise structural distance")
        for distance in redesign_set.pairwise_distances:
            dimensions = ", ".join(distance.changed_dimensions)
            print(
                f"  {distance.left} ↔ {distance.right}: {distance.score}/100 ({dimensions})"
            )

    recommendation = payload.get("recommended_proposal")
    if recommendation:
        print(f"\nHighest-relevance proposal: {recommendation}")
        print(f"Prototype next: uidetox prototype {recommendation}")
    if redesign_set.unknowns:
        print(f"Runtime/evidence gates: {len(redesign_set.unknowns)}")


def _comparison_payload(redesign_set: RedesignSet) -> dict[str, Any]:
    return {
        "target": redesign_set.target,
        "baseline": {
            dimension: redesign_set.baseline_fingerprint.get(dimension, "unknown")
            for dimension in _DIMENSIONS
        },
        "proposals": [
            {
                "id": proposal.id,
                "name": proposal.name,
                "novelty_score": proposal.novelty_score,
                "dimensions": {
                    dimension: proposal.fingerprint.get(dimension, "unknown")
                    for dimension in _DIMENSIONS
                },
            }
            for proposal in redesign_set.proposals
        ],
        "pairwise_distances": [
            {
                "left": distance.left,
                "right": distance.right,
                "score": distance.score,
                "changed_dimensions": list(distance.changed_dimensions),
            }
            for distance in redesign_set.pairwise_distances
        ],
        "recommended_proposal": (
            redesign_set.proposals[0].id if redesign_set.proposals else None
        ),
        "unknowns": list(redesign_set.unknowns),
    }
