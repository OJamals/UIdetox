from uidetox.cli import parse_args
from uidetox.commands import setup


def test_capture_cli_accepts_visual_evidence_controls() -> None:
    args = parse_args(
        [
            "capture",
            "--threshold",
            "12",
            "--max-pixels",
            "1000",
            "--dimension-policy",
            "strict",
            "--color-policy",
            "native",
            "--evidence-file",
            "evidence.json",
        ]
    )

    assert args.threshold == 12
    assert args.max_pixels == 1000
    assert args.dimension_policy == "strict"
    assert args.color_policy == "native"
    assert args.evidence_file == "evidence.json"


def test_visual_evidence_gate_flags_are_registered() -> None:
    for command in ("review", "status", "loop", "finish"):
        args = parse_args(
            [
                command,
                "--require-visual-evidence",
                "--visual-evidence-file",
                "evidence.json",
            ]
        )
        assert args.require_visual_evidence is True
        assert args.visual_evidence_file == "evidence.json"


def test_setup_accepts_persistent_visual_evidence_controls() -> None:
    args = parse_args(
        [
            "setup",
            "--visual-threshold",
            "8",
            "--visual-max-pixels",
            "2048",
            "--visual-evidence-file",
            "evidence.json",
            "--require-visual-evidence",
            "--no-intent-prompt",
        ]
    )

    assert args.visual_threshold == 8
    assert args.visual_max_pixels == 2048
    assert args.require_visual_evidence is True


def test_setup_persists_visual_evidence_controls(monkeypatch) -> None:
    saved: list[dict] = []
    monkeypatch.setattr(setup, "ensure_uidetox_dir", lambda: None)
    monkeypatch.setattr(setup, "load_config", lambda: {})
    monkeypatch.setattr(setup, "save_config", saved.append)
    monkeypatch.setattr(setup, "_is_interactive", lambda: False)
    args = parse_args(
        [
            "setup",
            "--visual-threshold",
            "8",
            "--visual-max-pixels",
            "2048",
            "--visual-evidence-file",
            "evidence.json",
            "--require-visual-evidence",
            "--no-intent-prompt",
        ]
    )

    setup.run(args)

    assert saved[-1]["visual_evidence"] == {
        "threshold": 8,
        "max_pixels": 2048,
        "manifest_path": "evidence.json",
        "required": True,
    }
