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
        "contract_mismatch": sum(
            finding.get("status") != "investigate" for finding in findings
        ),
        "coverage_gap": sum(
            finding.get("status") == "investigate" for finding in findings
        ),
    }
    contract_nodes = project_map.get("nodes", [])
    summary: dict[str, Any] = {
        "target": frontend_map.get("target"),
        "nodes": len(frontend_map.get("nodes", [])),
        "edges": len(frontend_map.get("edges", [])),
        "runtime_observed": evidence.get("runtime_observed"),
        "runtime_status": evidence.get("runtime_status"),
        "client_operations": sum(
            node.get("kind") == "client_operation" for node in contract_nodes
        ),
        "backend_routes": sum(node.get("kind") == "route" for node in contract_nodes),
        "contract_lineage": counts,
        "contract_nodes": len(contract_nodes),
        "contract_edges": len(project_map.get("edges", [])),
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
        summary["redesign_contract_lineage"] = redesigns.get(
            "contract_lineage", {}
        ).get("counts", {})
        summary["runtime_unknowns"] = redesigns.get("unknowns", [])
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
