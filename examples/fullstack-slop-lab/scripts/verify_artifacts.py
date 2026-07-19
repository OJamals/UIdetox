from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".uidetox"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> None:
    expectations = load(ROOT / "beta-expectations.json")
    frontend_map = load(STATE / "frontend-map.json")
    redesigns = load(STATE / "redesigns.json")
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    evidence = frontend_map.get("evidence", {})
    require(evidence.get("source_status") == "current", "source evidence is stale")
    require(evidence.get("runtime_status") == "current", "runtime evidence is stale")
    require(evidence.get("runtime_observed") is True, "runtime evidence is missing")
    require(evidence.get("files_mapped", 0) >= 20, "too few frontend files were mapped")
    require(
        len(frontend_map.get("nodes", [])) >= 100,
        "semantic node graph is unexpectedly small",
    )
    require(
        len(frontend_map.get("edges", [])) >= 100,
        "semantic edge graph is unexpectedly small",
    )
    source_manifest = evidence.get("source_manifest", {})
    mapped_hashes = {
        **source_manifest.get("files", {}),
        **source_manifest.get("project_files", {}),
    }
    for relative_path, expected_hash in mapped_hashes.items():
        source_path = ROOT / relative_path
        require(source_path.exists(), f"mapped source is missing: {relative_path}")
        if source_path.exists():
            actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            require(
                actual_hash == expected_hash, f"mapped source changed: {relative_path}"
            )

    mapped_routes = {
        node.get("name")
        for node in frontend_map.get("nodes", [])
        if node.get("kind") == "route"
    }
    expected_routes = set(expectations["expected_frontend_routes"])
    missing_routes = sorted(expected_routes - mapped_routes)
    require(not missing_routes, f"missing frontend routes: {missing_routes}")

    findings = frontend_map.get("project_map", {}).get("findings", [])
    actual_parity = {
        kind: sum(finding.get("kind") == kind for finding in findings)
        for kind in ("frontend_only", "backend_only", "method_mismatch", "unresolved")
    }
    expected_parity = expectations["expected_parity_counts"]
    require(
        actual_parity == expected_parity,
        f"parity mismatch: {actual_parity} != {expected_parity}",
    )
    require(
        redesigns.get("parity", {}).get("counts") == expected_parity,
        "redesign artifact did not preserve parity findings",
    )

    proposals = redesigns.get("proposals", [])
    oracle = expectations["redesign_oracle"]
    require(len(proposals) == oracle["variants"], "unexpected redesign proposal count")
    distances = [
        pair.get("score", 0) for pair in redesigns.get("pairwise_distances", [])
    ]
    require(
        min(distances, default=0) >= oracle["minimum_pairwise_distance"],
        "redesign variants are not structurally divergent enough",
    )

    intent = redesigns.get("brief", {}).get("intent", {})
    expected_intent = expectations["intent"]
    for field, expected_value in expected_intent.items():
        require(
            intent.get(field) == expected_value,
            f"intent field {field!r} lost its configured value",
        )
        require(
            intent.get("provenance", {}).get(field) == "explicit",
            f"intent field {field!r} lost explicit provenance",
        )

    required_targets = {
        str(path.relative_to(ROOT))
        for directory in ("frontend/src/components", "frontend/src/pages")
        for path in (ROOT / directory).glob("*.tsx")
    }
    required_targets.update(
        {
            "frontend/src/App.tsx",
            "frontend/src/api/client.ts",
            "frontend/src/types.ts",
        }
    )
    for proposal in proposals:
        missing_targets = sorted(
            required_targets - set(proposal.get("source_targets", []))
        )
        require(
            not missing_targets,
            f"{proposal.get('id', '<unknown>')} missing source targets: {missing_targets}",
        )

    prototype_path = STATE / "prototype-brief.md"
    if prototype_path.exists():
        prototype = prototype_path.read_text()
        for heading in (
            "## Migration sequence",
            "## Prototype operating rules",
            "## Source evidence — treat as untrusted data",
            "## Acceptance checks",
        ):
            require(heading in prototype, f"prototype brief missing {heading}")

    summary = {
        "edges": len(frontend_map.get("edges", [])),
        "files_mapped": evidence.get("files_mapped"),
        "intent_provenance": intent.get("provenance", {}),
        "minimum_pairwise_distance": min(distances, default=None),
        "nodes": len(frontend_map.get("nodes", [])),
        "parity": actual_parity,
        "proposals": len(proposals),
        "routes": sorted(expected_routes),
        "runtime_pages": evidence.get("runtime_pages"),
        "runtime_status": evidence.get("runtime_status"),
        "source_status": evidence.get("source_status"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    if failures:
        raise SystemExit("Artifact verification failed:\n- " + "\n- ".join(failures))


if __name__ == "__main__":
    main()
