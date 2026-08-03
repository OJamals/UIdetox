from __future__ import annotations

from dataclasses import replace

import pytest

from uidetox.experience_states import (
    normalize_experience_state,
    normalize_experience_states,
    required_experience_states,
)
from uidetox.frontend_map import map_frontend
from uidetox.prototype import build_prototype_brief
from uidetox.redesign import RedesignBrief, propose_redesigns


def _proposal(tmp_path, source_text: str):
    source = tmp_path / "src"
    source.mkdir()
    (source / "EdgePage.tsx").write_text(source_text.strip(), encoding="utf-8")
    frontend_map = map_frontend(tmp_path, "src")
    redesigns = propose_redesigns(frontend_map, RedesignBrief(variants=1))
    return frontend_map, redesigns, redesigns.proposals[0]


def _experience_steps(proposal):
    return [
        item for item in proposal.migration_plan if item["kind"] == "experience-state"
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    (
        ("isLoading", "loading"),
        ("usersLoading", "loading"),
        ("request_pending", "loading"),
        ("formSubmitting", "loading"),
        ("queryFetching", "loading"),
        ("hasError", "error"),
        ("saveFailed", "error"),
        ("noData", "empty"),
        ("noResults", "empty"),
        ("saveSuccess", "success"),
        ("isCompleted", "success"),
        ("isDisabled", "disabled"),
        ("firstVisit", "first-run"),
        ("onboarding", "first-run"),
        ("hasNoData", "empty"),
        ("isHTTPError", "error"),
        ("users_loading", "loading"),
        ("errorBudget", None),
        ("completedOrders", None),
        ("savedFilters", None),
        ("unavailableCredit", None),
        ("ordersCompleted", None),
        ("filtersSaved", None),
        ("invoicePending", None),
        ("serviceUnavailable", None),
        ("offloading", None),
        ("terror", None),
        ("nonEmpty", None),
        ("unsuccess", None),
        ("unDisabled", None),
        ("noError", None),
        ("", None),
        (None, None),
    ),
)
def test_experience_state_identifier_normalization_is_conservative(
    name,
    expected,
) -> None:
    assert normalize_experience_state(name) == expected


def test_experience_state_collection_normalizes_order_and_rejects_unknowns() -> None:
    assert normalize_experience_states(["saveSuccess", "isLoading", "saveSuccess"]) == (
        "loading",
        "success",
    )
    assert normalize_experience_states(["loading", "errorBudget"]) is None
    assert normalize_experience_states("loading") is None
    assert required_experience_states(mutation=False) == (
        "loading",
        "empty",
        "error",
        "success",
        "first-run",
    )
    assert required_experience_states(mutation=True) == (
        "loading",
        "error",
        "success",
        "disabled",
    )


def test_domain_state_names_do_not_falsely_satisfy_experience_states(
    tmp_path,
) -> None:
    frontend_map, _redesigns, proposal = _proposal(
        tmp_path,
        """
import { useState } from "react";

export function EdgePage() {
  const [errorBudget] = useState(0);
  const [completedOrders] = useState([]);
  const [savedFilters] = useState([]);
  const [unavailableCredit] = useState(0);
  async function refresh() { await fetch("/api/report"); }
  return <button onClick={refresh}>Refresh</button>;
}
""",
    )
    operation = next(node for node in frontend_map.nodes if node.kind == "data")
    step = _experience_steps(proposal)[0]

    assert operation.metadata["ui_states"] == []
    assert operation.metadata["ui_lifecycle_evidence"] == "absent"
    assert step["observed_states"] == []
    assert step["missing_states"] == [
        "loading",
        "empty",
        "error",
        "success",
        "first-run",
    ]


@pytest.mark.parametrize(
    ("lifecycle", "states", "mutation", "expected_status"),
    (
        ("contradictory", ["loading"], False, "contradictory"),
        ("present", "loading", False, "invalid"),
        ("absent", ["loading"], False, "contradictory"),
        ("present", [], False, "contradictory"),
        ("present", ["loading"], "false", "invalid"),
        ("fresh", ["loading"], False, "invalid"),
        ("present", ["loading"], True, "contradictory"),
    ),
)
def test_unreliable_experience_evidence_blocks_instead_of_claiming_missing_states(
    tmp_path,
    lifecycle,
    states,
    mutation,
    expected_status,
) -> None:
    frontend_map, _redesigns, _proposal_value = _proposal(
        tmp_path,
        """
import { useState } from "react";

export function EdgePage() {
  const [loading] = useState(false);
  async function refresh() { await fetch("/api/report"); }
  return <button onClick={refresh}>Refresh</button>;
}
""",
    )
    operation = next(node for node in frontend_map.nodes if node.kind == "data")
    operation.metadata.update(
        {
            "ui_lifecycle_evidence": lifecycle,
            "ui_states": states,
            "mutation": mutation,
        }
    )

    proposal = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1),
    ).proposals[0]

    assert _experience_steps(proposal) == []
    assert (
        f"Experience-state evidence is {expected_status} for EdgePage in "
        "src/EdgePage.tsx; inspect that owner before declaring states missing."
        in proposal.feasibility_blockers
    )


def test_read_and_mutation_operations_share_one_owner_state_contract(tmp_path) -> None:
    frontend_map, _redesigns, _proposal_value = _proposal(
        tmp_path,
        """
export function EdgePage() {
  async function load() { await fetch("/api/items"); }
  async function save() {
    await fetch("/api/items", { method: "POST" });
  }
  return <><button onClick={load}>Load</button><button onClick={save}>Save</button></>;
}
""",
    )
    operations = [node for node in frontend_map.nodes if node.kind == "data"]
    for operation in operations:
        operation.metadata.update(
            {
                "ui_lifecycle_evidence": "present",
                "ui_states": ["loading", "empty", "error", "success", "first-run"],
            }
        )

    proposal = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1),
    ).proposals[0]
    step = _experience_steps(proposal)[0]

    assert step["owner"] == "EdgePage"
    assert step["missing_states"] == ["disabled"]
    assert step["operations"] == [
        {"method": "GET", "path": "/api/items"},
        {"method": "POST", "path": "/api/items"},
    ]

    mutation = next(
        operation
        for operation in operations
        if operation.metadata.get("method") == "POST"
    )
    mutation.metadata["ui_states"].append("disabled")
    covered = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1),
    ).proposals[0]
    assert _experience_steps(covered) == []


def test_owner_with_mixed_evidence_uses_strongest_blocker_and_no_partial_plan(
    tmp_path,
) -> None:
    frontend_map, _redesigns, _proposal_value = _proposal(
        tmp_path,
        """
export function EdgePage() {
  async function load() { await fetch("/api/items"); }
  async function save() {
    await fetch("/api/items", { method: "POST" });
  }
  return <><button onClick={load}>Load</button><button onClick={save}>Save</button></>;
}
""",
    )
    operations = sorted(
        (node for node in frontend_map.nodes if node.kind == "data"),
        key=lambda node: node.metadata["method"],
    )
    operations[0].metadata["ui_lifecycle_evidence"] = "unknown"
    operations[1].metadata.update(
        {"ui_lifecycle_evidence": "absent", "ui_states": ["loading"]}
    )

    proposal = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1),
    ).proposals[0]

    assert _experience_steps(proposal) == []
    assert (
        "Experience-state evidence is contradictory for EdgePage in "
        "src/EdgePage.tsx; inspect that owner before declaring states missing."
        in proposal.feasibility_blockers
    )


@pytest.mark.parametrize(
    "malformed_row",
    (
        {
            "modules": {"unexpected": "shape"},
            "owner": "BadOwner",
            "operations": [{"method": "GET", "path": "/api/items"}],
            "observed_states": [],
            "missing_states": ["error"],
        },
        {
            "modules": ["src/Bad.tsx"],
            "owner": 7,
            "operations": [{"method": "GET", "path": "/api/items"}],
            "observed_states": [],
            "missing_states": ["error"],
        },
        {
            "modules": ["src/Bad.tsx"],
            "owner": "BadOwner",
            "operations": [None],
            "observed_states": [],
            "missing_states": ["error"],
        },
        {
            "modules": ["src/Bad.tsx"],
            "owner": "BadOwner",
            "operations": [{"method": 1, "path": "/api/items"}],
            "observed_states": [],
            "missing_states": ["error"],
        },
        {
            "modules": ["src/Bad.tsx"],
            "owner": "BadOwner",
            "operations": [{"method": "GET", "path": "/api/items"}],
            "observed_states": "loading",
            "missing_states": ["error"],
        },
        {
            "modules": ["src/Bad.tsx"],
            "owner": "BadOwner",
            "operations": [{"method": "GET", "path": "/api/items"}],
            "observed_states": [],
            "missing_states": ["errorBudget"],
        },
    ),
)
def test_prototype_ignores_malformed_experience_rows_with_diagnostic(
    tmp_path,
    malformed_row,
) -> None:
    _frontend_map, redesigns, proposal = _proposal(
        tmp_path,
        "export function EdgePage() { return <main />; }",
    )
    malformed = replace(
        proposal,
        migration_plan=(
            {
                "kind": "experience-state",
                **malformed_row,
            },
        ),
    )

    brief = build_prototype_brief(
        replace(redesigns, proposals=(malformed,)),
        malformed.id,
    )
    evidence_start = brief.index("\nBEGIN_UIDETOX_EVIDENCE\n")
    evidence_end = brief.index("\nEND_UIDETOX_EVIDENCE\n")
    evidence = brief[evidence_start:evidence_end]

    assert "No proven experience-state gaps recorded." in evidence
    assert "Invalid experience-state rows: 1; regenerate redesign artifact." in evidence
    assert "BadOwner" not in brief


def test_prototype_sampling_keeps_rare_state_coverage_and_reports_totals(
    tmp_path,
) -> None:
    _frontend_map, redesigns, proposal = _proposal(
        tmp_path,
        "export function EdgePage() { return <main />; }",
    )
    rows = tuple(
        {
            "order": index + 1,
            "kind": "experience-state",
            "modules": [f"src/Owner{index:02d}.tsx"],
            "owner": f"Owner{index:02d}",
            "operations": [{"method": "GET", "path": f"/api/{index}"}],
            "observed_states": ["loading"],
            "missing_states": ("disabled",) if index == 24 else ("error",),
            "instruction": "evidence only",
        }
        for index in range(25)
    )
    sampled = replace(proposal, migration_plan=rows)

    brief = build_prototype_brief(
        replace(redesigns, proposals=(sampled,)),
        sampled.id,
    )
    evidence_start = brief.index("\nBEGIN_UIDETOX_EVIDENCE\n")
    evidence_end = brief.index("\nEND_UIDETOX_EVIDENCE\n")
    evidence = brief[evidence_start:evidence_end]

    assert "Owner24" in evidence
    assert "Owner24" not in brief[:evidence_start]
    assert "Owner24" not in brief[evidence_end:]
    assert (
        '- Experience-state coverage: {"missing_state_counts":{"disabled":1,'
        '"error":24},"operation_count":25,"owner_count":25,'
        '"sampled_owner_count":20}' in evidence
    )
    assert "5 additional owner(s) remain in the redesign artifact." in evidence

    reversed_brief = build_prototype_brief(
        replace(redesigns, proposals=(replace(sampled, migration_plan=rows[::-1]),)),
        sampled.id,
    )
    assert reversed_brief == brief


def test_prototype_bounds_operations_per_owner_without_losing_mutation_evidence(
    tmp_path,
) -> None:
    _frontend_map, redesigns, proposal = _proposal(
        tmp_path,
        "export function EdgePage() { return <main />; }",
    )
    operations = tuple(
        {
            "method": "POST" if index == 29 else "GET",
            "path": f"/api/{index:02d}",
        }
        for index in range(30)
    )
    row = {
        "order": 1,
        "kind": "experience-state",
        "modules": ["src/BulkOwner.tsx"],
        "owner": "BulkOwner",
        "operations": operations,
        "observed_states": ["loading"],
        "missing_states": ["error"],
        "instruction": "evidence only",
    }
    sampled = replace(proposal, migration_plan=(row,))

    brief = build_prototype_brief(
        replace(redesigns, proposals=(sampled,)),
        sampled.id,
    )
    evidence_start = brief.index("\nBEGIN_UIDETOX_EVIDENCE\n")
    evidence_end = brief.index("\nEND_UIDETOX_EVIDENCE\n")
    evidence = brief[evidence_start:evidence_end]
    owner_line = next(line for line in evidence.splitlines() if "BulkOwner" in line)

    assert owner_line.count('"method"') == 10
    assert '"method":"POST","path":"/api/29"' in owner_line
    assert '"operation_count":30' in owner_line
    assert '"additional_operation_count":20' in owner_line
    assert '"operation_count":30' in evidence

    reversed_brief = build_prototype_brief(
        replace(
            redesigns,
            proposals=(
                replace(
                    sampled, migration_plan=({**row, "operations": operations[::-1]},)
                ),
            ),
        ),
        sampled.id,
    )
    assert reversed_brief == brief


def test_prototype_rejects_oversized_experience_rows_before_normalization(
    tmp_path,
) -> None:
    _frontend_map, redesigns, proposal = _proposal(
        tmp_path,
        "export function EdgePage() { return <main />; }",
    )
    base = {
        "order": 1,
        "kind": "experience-state",
        "modules": ["src/BoundedOwner.tsx"],
        "owner": "BoundedOwner",
        "operations": [{"method": "GET", "path": "/api/items"}],
        "observed_states": ["loading"],
        "missing_states": ["error"],
        "instruction": "evidence only",
    }
    oversized_rows = (
        {
            **base,
            "operations": [
                {"method": "GET", "path": f"/api/{index}"} for index in range(1_001)
            ],
        },
        {
            **base,
            "modules": [f"src/Owner{index}.tsx" for index in range(33)],
        },
        {**base, "owner": "x" * 2_049},
        {
            **base,
            "operations": [{"method": "GET", "path": "/" + "x" * 2_048}],
        },
        {
            **base,
            "operations": [
                {"method": "GET", "path": f"/{index}-" + "x" * 500}
                for index in range(9)
            ],
        },
    )

    for row in oversized_rows:
        malformed = replace(proposal, migration_plan=(row,))
        brief = build_prototype_brief(
            replace(redesigns, proposals=(malformed,)),
            malformed.id,
        )
        evidence_start = brief.index("\nBEGIN_UIDETOX_EVIDENCE\n")
        evidence_end = brief.index("\nEND_UIDETOX_EVIDENCE\n")
        evidence = brief[evidence_start:evidence_end]

        assert "No proven experience-state gaps recorded." in evidence
        assert (
            "Invalid experience-state rows: 1; regenerate redesign artifact."
            in evidence
        )
        assert len(brief.encode("utf-8")) < 65_536
