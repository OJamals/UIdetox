from uidetox import cli
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
            "srgb",
            "--evidence-file",
            "evidence.json",
            "--reviewer-artifacts",
            "--crop-padding",
            "24",
            "--png-compress-level",
            "9",
            "--png-optimize",
            "--isolated",
            "--allowed-root",
            "/tmp/project",
            "--worker-timeout",
            "12.5",
            "--worker-max-memory-mb",
            "512",
        ]
    )

    assert args.threshold == 12
    assert args.max_pixels == 1000
    assert args.dimension_policy == "strict"
    assert args.color_policy == "srgb"
    assert args.evidence_file == "evidence.json"
    assert args.reviewer_artifacts is True
    assert args.crop_padding == 24
    assert args.png_compress_level == 9
    assert args.png_optimize is True
    assert args.isolated is True
    assert args.allowed_root == ["/tmp/project"]
    assert args.worker_timeout == 12.5
    assert args.worker_max_memory_mb == 512


def test_visual_evidence_command_accepts_local_comparison_controls() -> None:
    args = parse_args(
        [
            "visual-evidence",
            "--before",
            "before.png",
            "--after",
            "after.png",
            "--viewport",
            "1280x800",
            "--reviewer-artifacts",
            "--isolated",
            "--allowed-root",
            ".",
            "--json",
        ]
    )

    assert args.command == "visual-evidence"
    assert args.before == "before.png"
    assert args.after == "after.png"
    assert args.viewport == "1280x800"
    assert args.reviewer_artifacts is True
    assert args.isolated is True
    assert args.allowed_root == ["."]
    assert args.json is True


def test_visual_evidence_command_dispatches_to_cmd_module(
    monkeypatch,
) -> None:
    imported: list[str] = []

    class Module:
        @staticmethod
        def run(_args) -> None:
            return None

    def fake_import(name: str):
        imported.append(name)
        return Module

    monkeypatch.setattr(cli, "import_module", fake_import)

    monkeypatch.setattr(
        "sys.argv",
        [
            "uidetox",
            "visual-evidence",
            "--before",
            "before.png",
            "--after",
            "after.png",
        ],
    )
    cli.main()

    assert imported[-1] == "uidetox.commands.visual_evidence_cmd"


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
