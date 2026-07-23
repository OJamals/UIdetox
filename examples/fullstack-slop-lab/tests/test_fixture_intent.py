from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


FIXTURE_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_intent_records_reproducible_provenance() -> None:
    manifest = json.loads((FIXTURE_ROOT / "fixture-intent.json").read_text())

    assert manifest["product_goal"].startswith("Provide a runnable B2B operations fixture")
    assert manifest["remediation_evidence"]["baseline_static_issues"] == 212
    assert set(manifest["remediation_evidence"]["target_operation_parity"].values()) == {0}
    assert manifest["provenance"]["origin"] == "synthetic test fixture"
    assert manifest["provenance"]["contains_production_data"] is False
    assert manifest["provenance"]["sources_of_truth"] == [
        "fixture-intent.json",
        "beta-expectations.json",
        "openapi.yaml",
    ]
    assert {
        "/customers",
        "/data-hub",
        "/approvals",
        "/journeys",
        "/fixture-provenance",
    } <= set(
        manifest["expected_frontend_routes"]
    )


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
