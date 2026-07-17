"""Typed design intent and structurally active redesign dials."""

import pytest
from pathlib import Path

from uidetox.cli import parse_args
from uidetox.commands import setup as setup_command
from uidetox.design_context import DesignDials, DesignIntent, DesignSettings
from uidetox.frontend_map import map_frontend
from uidetox.redesign import RedesignBrief, propose_redesigns


def _write_frontend(project: Path) -> None:
    src = project / "src"
    src.mkdir()
    (src / "App.tsx").write_text(
        """
import { useState } from "react";
export function App() {
  const [ready, setReady] = useState(false);
  return <form onSubmit={() => setReady(true)}><button>Continue</button></form>;
}
""".strip(),
        encoding="utf-8",
    )


def test_design_dials_reject_out_of_range_values():
    with pytest.raises(ValueError, match="DESIGN_VARIANCE must be between 1 and 10"):
        DesignDials(design_variance=0)
    with pytest.raises(ValueError, match="MOTION_INTENSITY must be between 1 and 10"):
        DesignDials(motion_intensity=11)


def test_design_settings_merge_configured_preflight_with_map_inference(tmp_path):
    _write_frontend(tmp_path)
    frontend_map = map_frontend(tmp_path)

    settings = DesignSettings.from_config(
        {
            "DESIGN_VARIANCE": 7,
            "design_intent": {
                "audience": "warehouse operators",
                "tone": "calm and industrial",
            },
        },
        frontend_map,
    )

    assert settings.intent.audience == "warehouse operators"
    assert settings.intent.tone == "calm and industrial"
    assert settings.intent.primary_job == "complete and submit the mapped workflow"
    assert settings.intent.genre == "task workflow"
    assert settings.intent.source == "configured+inferred"
    assert settings.intent.provenance["audience"] == "explicit"
    assert settings.intent.provenance["primary_job"] == "mapped"


def test_dials_change_proposal_structure_and_fingerprint(tmp_path):
    _write_frontend(tmp_path)
    frontend_map = map_frontend(tmp_path)
    intent = DesignIntent(
        audience="clinical operators",
        primary_job="complete the review workflow",
        tone="quiet and exact",
        genre="task workflow",
    )
    low = propose_redesigns(
        frontend_map,
        RedesignBrief(
            variants=1,
            design_variance=2,
            motion_intensity=2,
            visual_density=2,
            intent=intent,
        ),
    ).proposals[0]
    high = propose_redesigns(
        frontend_map,
        RedesignBrief(
            variants=1,
            design_variance=9,
            motion_intensity=9,
            visual_density=9,
            intent=intent,
        ),
    ).proposals[0]

    assert low.fingerprint["composition"] == "aligned-grid"
    assert high.fingerprint["composition"] == "asymmetric-zones"
    assert low.fingerprint["motion_model"] == "state-only"
    assert high.fingerprint["motion_model"] == "spatial-choreography"
    assert low.fingerprint["density_model"] == "progressive-disclosure"
    assert high.fingerprint["density_model"] == "simultaneous-overview"
    assert low.layout_tree != high.layout_tree
    assert low.interaction_model != high.interaction_model


def test_setup_persists_typed_design_intent(monkeypatch):
    saved = {}
    monkeypatch.setattr(setup_command, "ensure_uidetox_dir", lambda: None)
    monkeypatch.setattr(setup_command, "load_config", lambda: {})
    monkeypatch.setattr(
        setup_command, "save_config", lambda config: saved.update(config)
    )
    args = parse_args(
        [
            "setup",
            "--audience",
            "field technicians",
            "--primary-job",
            "repair an asset",
            "--tone",
            "direct and rugged",
            "--genre",
            "field service tool",
            "--page-kind",
            "flow",
            "--brand",
            "retain orange safety cues",
            "--preserve",
            "offline operation",
            "--constraint",
            "glove-friendly targets",
            "--no-auto-commit",
        ]
    )

    setup_command.run(args)

    assert saved["design_intent"]["audience"] == "field technicians"
    assert saved["design_intent"]["primary_job"] == "repair an asset"
    assert saved["design_intent"]["preserve"] == ("offline operation",)
    assert saved["design_intent"]["constraints"] == ("glove-friendly targets",)
    assert saved["design_intent"]["provenance"]["primary_job"] == "explicit"


def test_default_setup_preserves_mapped_intent_through_redesign(
    monkeypatch, tmp_path
):
    saved = {}
    monkeypatch.setattr(setup_command, "ensure_uidetox_dir", lambda: None)
    monkeypatch.setattr(setup_command, "load_config", lambda: {})
    monkeypatch.setattr(
        setup_command, "save_config", lambda config: saved.update(config)
    )

    setup_command.run(parse_args(["setup", "--no-auto-commit"]))

    assert "design_intent" not in saved

    _write_frontend(tmp_path)
    frontend_map = map_frontend(tmp_path)
    settings = DesignSettings.from_config(saved, frontend_map)
    redesign_set = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1, intent=settings.intent),
    )

    assert settings.intent.primary_job == "complete and submit the mapped workflow"
    assert settings.intent.genre == "task workflow"
    assert settings.intent.preserve == frontend_map.contracts.must_preserve
    assert settings.intent.constraints == frontend_map.contracts.unknown
    assert settings.intent.provenance["primary_job"] == "mapped"
    assert redesign_set.brief.intent == settings.intent


def test_legacy_defaults_do_not_mask_mapping_but_non_defaults_remain_explicit(
    tmp_path,
):
    _write_frontend(tmp_path)
    frontend_map = map_frontend(tmp_path)
    settings = DesignSettings.from_config(
        {
            "design_intent": {
                "audience": "warehouse operators",
                "primary_job": "complete the mapped product task",
                "genre": "product interface",
                "preserve": [],
                "constraints": [],
                "source": "configured",
            }
        },
        frontend_map,
    )

    assert settings.intent.audience == "warehouse operators"
    assert settings.intent.primary_job == "complete and submit the mapped workflow"
    assert settings.intent.genre == "task workflow"
    assert settings.intent.preserve == frontend_map.contracts.must_preserve
    assert settings.intent.constraints == frontend_map.contracts.unknown
    assert settings.intent.provenance["audience"] == "explicit"
    assert settings.intent.provenance["genre"] == "mapped"


def test_empty_explicit_values_and_metadata_cannot_mask_mapping(tmp_path):
    _write_frontend(tmp_path)
    frontend_map = map_frontend(tmp_path)
    settings = DesignSettings.from_config(
        {
            "design_intent": {
                "primary_job": " ",
                "preserve": [],
                "source": "explicit",
                "provenance": {
                    "primary_job": "explicit",
                    "preserve": "explicit",
                    "source": "explicit",
                },
            }
        },
        frontend_map,
    )

    assert settings.intent.primary_job == "complete and submit the mapped workflow"
    assert settings.intent.preserve == frontend_map.contracts.must_preserve
    assert settings.intent.provenance["primary_job"] == "mapped"
