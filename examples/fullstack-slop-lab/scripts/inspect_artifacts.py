from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> None:
    frontend_map_path = ROOT / ".uidetox" / "frontend-map.json"
    redesign_path = ROOT / ".uidetox" / "redesigns.json"
    if not frontend_map_path.exists():
        raise SystemExit(
            "Run `uidetox map frontend --runtime --url http://127.0.0.1:4173` first."
        )

    frontend_map = load(frontend_map_path)
    evidence = frontend_map.get("evidence", {})
    project_map = frontend_map.get("project_map", {})
    findings = project_map.get("findings", [])
    counts = {
        kind: sum(finding.get("kind") == kind for finding in findings)
        for kind in ("frontend_only", "backend_only", "method_mismatch", "unresolved")
    }
    summary: dict[str, Any] = {
        "target": frontend_map.get("target"),
        "nodes": len(frontend_map.get("nodes", [])),
        "edges": len(frontend_map.get("edges", [])),
        "runtime_observed": evidence.get("runtime_observed"),
        "runtime_status": evidence.get("runtime_status"),
        "frontend_operations": len(project_map.get("frontend_operations", [])),
        "backend_operations": len(project_map.get("backend_operations", [])),
        "parity": counts,
        "source_status": evidence.get("source_status"),
    }
    if redesign_path.exists():
        redesigns = load(redesign_path)
        proposals = redesigns.get("proposals", [])
        distances = [
            item.get("score", 0) for item in redesigns.get("pairwise_distances", [])
        ]
        intent = redesigns.get("brief", {}).get("intent", {})
        summary["intent_provenance"] = intent.get("provenance", {})
        summary["pairwise_minimum_distance"] = min(distances, default=None)
        summary["proposal_count"] = len(proposals)
        summary["proposal_topologies"] = [
            proposal.get("fingerprint", {}).get("topology") for proposal in proposals
        ]
        summary["proposal_targets"] = sorted(
            {
                target
                for proposal in proposals
                for target in proposal.get("source_targets", [])
            }
        )
        summary["redesign_parity"] = redesigns.get("parity", {}).get("counts", {})
        summary["runtime_unknowns"] = redesigns.get("unknowns", [])
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
