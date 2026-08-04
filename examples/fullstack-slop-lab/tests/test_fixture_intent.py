from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_intent_records_reproducible_provenance() -> None:
    manifest = json.loads((FIXTURE_ROOT / "fixture-intent.json").read_text())

    assert manifest["product_goal"].startswith(
        "Provide a runnable B2B operations stress fixture"
    )
    assert manifest["remediation_evidence"]["baseline_static_issues"] == 212
    assert set(
        manifest["remediation_evidence"]["target_operation_parity"].values()
    ) == {0}
    assert manifest["provenance"]["origin"] == "synthetic test fixture"
    assert manifest["provenance"]["contains_production_data"] is False
    assert manifest["provenance"]["sources_of_truth"] == [
        "fixture-intent.json",
        "beta-expectations.json",
        "intentional-slop.json",
        "openapi.yaml",
    ]
    assert {
        "/customers",
        "/data-hub",
        "/approvals",
        "/journeys",
        "/pipeline",
        "/pipeline/:opportunityId",
        "/forecast",
        "/support",
        "/support/:caseId",
        "/service-levels",
        "/catalog",
        "/orders",
        "/orders/:orderId",
        "/inventory",
        "/shipments",
        "/campaigns",
        "/segments",
        "/content-library",
        "/surveys",
        "/audit-log",
        "/feature-flags",
        "/service-health",
        "/marketplace",
        "/work-queue",
        "/fixture-provenance",
    } <= set(manifest["expected_frontend_routes"])
    assert len(manifest["expected_frontend_routes"]) >= 34
    assert manifest["provenance"]["expanded_on"] == "2026-07-31"


def test_intentional_slop_manifest_is_bounded_and_multilayer() -> None:
    manifest = json.loads((FIXTURE_ROOT / "intentional-slop.json").read_text())

    assert manifest["purpose"] == "Historical UIdetox capability stress-fixture record"
    assert manifest["contains_security_vulnerabilities"] is False
    assert manifest["contains_external_side_effects"] is False
    assert set(manifest["layers"]) == {
        "static_css",
        "runtime_layout",
        "semantic_accessibility",
        "component_architecture",
        "frontend_api",
        "backend_openapi",
        "database_lineage",
    }
    assert len(manifest["canaries"]) >= 12
    assert all(item["expected_detector"] for item in manifest["canaries"])


def test_post_detox_expectations_separate_history_from_current_findings() -> None:
    manifest = json.loads((FIXTURE_ROOT / "intentional-slop.json").read_text())
    expectations = json.loads((FIXTURE_ROOT / "beta-expectations.json").read_text())

    assert manifest["canary_records_are_historical"] is True
    historical_ids = {item["id"] for item in manifest["canaries"]}
    remediated_ids = set(manifest["remediation"]["remediated_canaries"])
    retained_ids = set(manifest["remediation"]["retained_observations"])
    assert historical_ids == remediated_ids | retained_ids
    assert remediated_ids.isdisjoint(retained_ids)
    assert all(
        not findings
        for findings in expectations["deliberate_operation_findings"].values()
    )
    assert expectations["expected_contract_counts"]["contract_mismatch"] == 0


def test_prepare_script_passes_canonical_intent_to_uidetox(tmp_path: Path) -> None:
    manifest = json.loads((FIXTURE_ROOT / "fixture-intent.json").read_text())
    capture_path = tmp_path / "uidetox-arguments.json"
    stub_path = tmp_path / "uidetox"
    stub_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['UIDETOX_ARGUMENT_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\n"
    )
    stub_path.chmod(0o755)

    environment = {
        **os.environ,
        "UIDETOX_BIN": str(stub_path),
        "UIDETOX_ARGUMENT_CAPTURE": str(capture_path),
    }
    subprocess.run(
        [str(FIXTURE_ROOT / "scripts" / "prepare_uidetox.sh")],
        cwd=FIXTURE_ROOT,
        env=environment,
        check=True,
    )
    arguments = json.loads(capture_path.read_text())

    def option(name: str) -> str:
        return arguments[arguments.index(name) + 1]

    for option_name, field_name in (
        ("--product-goal", "product_goal"),
        ("--audience", "audience"),
        ("--primary-job", "primary_job"),
        ("--tone", "tone"),
        ("--genre", "genre"),
        ("--page-kind", "page_kind"),
        ("--brand", "brand"),
    ):
        assert option(option_name) == manifest[field_name]
