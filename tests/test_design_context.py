"""Typed design intent and structurally active redesign dials."""

import pytest
from pathlib import Path
from types import SimpleNamespace

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
    monkeypatch.setattr(
        setup_command,
        "record_intent_artifacts",
        lambda *_args, **_kwargs: SimpleNamespace(
            event={"event_id": "intent-test"},
            handoff_path=Path(".uidetox/agent-handoff.md"),
            prompt="test prompt",
        ),
    )
    monkeypatch.setattr(setup_command, "ensure_uidetox_dir", lambda: None)
    monkeypatch.setattr(setup_command, "load_config", lambda: {})
    monkeypatch.setattr(
        setup_command, "save_config", lambda config: saved.update(config)
    )
    args = parse_args(
        [
            "setup",
            "--product-goal",
            "keep field equipment operational",
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

    assert saved["design_intent"]["product_goal"] == (
        "keep field equipment operational"
    )
    assert saved["design_intent"]["audience"] == "field technicians"
    assert saved["design_intent"]["primary_job"] == "repair an asset"
    assert saved["design_intent"]["preserve"] == ("offline operation",)
    assert saved["design_intent"]["constraints"] == ("glove-friendly targets",)
    assert saved["design_intent"]["provenance"]["primary_job"] == "explicit"
    assert saved["design_intent"]["evidence"]["product_goal"] == ("user:cli-setup",)
    assert saved["design_intent"]["confirmation_status"] == "confirmed"


def test_setup_interactively_captures_and_confirms_product_intent(monkeypatch):
    saved = {}
    prompts = []
    monkeypatch.setattr(
        setup_command,
        "record_intent_artifacts",
        lambda *_args, **_kwargs: SimpleNamespace(
            event={"event_id": "intent-test"},
            handoff_path=Path(".uidetox/agent-handoff.md"),
            prompt="test prompt",
        ),
    )
    answers = iter(
        [
            "help independent clinics reduce missed appointments",
            "clinic coordinators",
            "find and resolve scheduling conflicts",
            "calm, precise, and humane",
            "retain the existing green identity",
            "appointment creation, patient privacy",
            "WCAG AA, works on tablets",
        ]
    )

    class _InteractiveStdin:
        @staticmethod
        def isatty():
            return True

    def _answer(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(setup_command, "ensure_uidetox_dir", lambda: None)
    monkeypatch.setattr(setup_command, "load_config", lambda: {})
    monkeypatch.setattr(
        setup_command, "save_config", lambda config: saved.update(config)
    )
    monkeypatch.setattr(setup_command.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr("builtins.input", _answer)

    setup_command.run(parse_args(["setup", "--no-auto-commit"]))

    intent = saved["design_intent"]
    assert any("website/app" in prompt.lower() for prompt in prompts)
    assert intent["product_goal"] == (
        "help independent clinics reduce missed appointments"
    )
    assert intent["audience"] == "clinic coordinators"
    assert intent["primary_job"] == "find and resolve scheduling conflicts"
    assert intent["preserve"] == (
        "appointment creation",
        "patient privacy",
    )
    assert intent["constraints"] == ("WCAG AA", "works on tablets")
    assert intent["provenance"]["product_goal"] == "explicit"
    assert intent["evidence"]["product_goal"] == ("user:interactive-setup",)
    assert intent["confidence"]["product_goal"] == 1.0
    assert intent["confirmation_status"] == "confirmed"
    assert intent["confirmed_at"]


def test_setup_can_skip_interactive_intent_interview(monkeypatch):
    saved = {}

    class _InteractiveStdin:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setattr(setup_command, "ensure_uidetox_dir", lambda: None)
    monkeypatch.setattr(setup_command, "load_config", lambda: {})
    monkeypatch.setattr(
        setup_command, "save_config", lambda config: saved.update(config)
    )
    monkeypatch.setattr(setup_command.sys, "stdin", _InteractiveStdin())
    monkeypatch.setattr(
        "builtins.input",
        lambda *_args, **_kwargs: pytest.fail("intent prompt should be skipped"),
    )

    setup_command.run(parse_args(["setup", "--no-intent-prompt", "--no-auto-commit"]))

    assert "design_intent" not in saved


def test_intent_provenance_tracks_mapped_evidence_and_confidence(tmp_path):
    _write_frontend(tmp_path)
    frontend_map = map_frontend(tmp_path)

    intent = DesignSettings.from_config({}, frontend_map).intent

    assert intent.provenance["primary_job"] == "mapped"
    assert intent.confidence["primary_job"] > intent.confidence["audience"]
    assert (
        "frontend-map:fingerprint.topology=form-flow" in intent.evidence["primary_job"]
    )
    assert intent.evidence["audience"] == ("fallback:audience",)
    assert intent.confirmation_status == "inferred"
    assert intent.confirmed_at == ""


def test_redesign_ranking_weights_user_intent_above_fallback_text(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.tsx").write_text(
        "export function App() { return <main><h1>Records</h1></main>; }",
        encoding="utf-8",
    )
    frontend_map = map_frontend(tmp_path)

    fallback = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1, intent=DesignIntent()),
    )
    explicit = DesignIntent.from_dict(
        {
            "product_goal": "help staff inspect and compare records",
            "provenance": {"product_goal": "explicit"},
            "evidence": {"product_goal": ["user:interactive-setup"]},
            "confidence": {"product_goal": 1.0},
        }
    )
    source_aware = propose_redesigns(
        frontend_map,
        RedesignBrief(variants=1, intent=explicit),
    )

    assert fallback.proposals[0].strategy == "editorial-narrative"
    assert source_aware.proposals[0].strategy == "object-workspace"
    assert explicit.product_goal in source_aware.proposals[0].rationale
    assert "explicit, 1.00 confidence" in source_aware.proposals[0].rationale
    assert any(
        "user-confirmed product goal" in check.lower()
        for check in source_aware.proposals[0].acceptance_checks
    )


def test_default_setup_preserves_mapped_intent_through_redesign(monkeypatch, tmp_path):
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
                "provenance": {"audience": "explicit"},
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
    assert settings.intent.evidence["audience"] == ("config:design_intent",)
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
