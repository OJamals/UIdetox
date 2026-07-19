"""CLI command tests for local visual-evidence comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from uidetox.cli import parse_args
from uidetox.commands import visual_evidence_cmd


def _images(tmp_path: Path) -> tuple[Path, Path]:
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    Image.new("RGB", (4, 3), (0, 0, 0)).save(before)
    changed = Image.new("RGB", (4, 3), (0, 0, 0))
    changed.putpixel((2, 1), (31, 0, 0))
    changed.save(after)
    return before, after


@pytest.mark.parametrize("isolated", [False, True])
def test_visual_evidence_command_builds_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    isolated: bool,
) -> None:
    before, after = _images(tmp_path)
    output = tmp_path / ("isolated" if isolated else "in-process")
    arguments = [
        "visual-evidence",
        "--before",
        str(before),
        "--after",
        str(after),
        "--output-dir",
        str(output),
        "--viewport",
        "4x3",
        "--json",
    ]
    if isolated:
        arguments.extend(["--isolated", "--allowed-root", str(tmp_path)])

    visual_evidence_cmd.run(parse_args(arguments))

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "complete"
    assert payload["comparisons"][0]["metrics"]["pixels_changed"] == 1
    assert (output / "manifest.json").is_file()


def test_visual_evidence_command_reports_invalid_viewport(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before, after = _images(tmp_path)
    args = parse_args(
        [
            "visual-evidence",
            "--before",
            str(before),
            "--after",
            str(after),
            "--viewport",
            "desktop",
        ]
    )

    with pytest.raises(SystemExit) as captured:
        visual_evidence_cmd.run(args)

    assert captured.value.code == 1
    assert "WIDTHxHEIGHT" in capsys.readouterr().err


def test_visual_evidence_command_rejects_url_before_path_resolution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, after = _images(tmp_path)
    args = parse_args(
        [
            "visual-evidence",
            "--before",
            "https://example.com/before.png",
            "--after",
            str(after),
        ]
    )

    with pytest.raises(SystemExit) as captured:
        visual_evidence_cmd.run(args)

    assert captured.value.code == 1
    error = capsys.readouterr().err
    assert "invalid_request" in error
    assert "URL fetching is unsupported" in error


def test_visual_evidence_command_does_not_replace_zero_worker_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before, after = _images(tmp_path)
    args = parse_args(
        [
            "visual-evidence",
            "--before",
            str(before),
            "--after",
            str(after),
            "--output-dir",
            str(tmp_path / "evidence"),
            "--isolated",
            "--allowed-root",
            str(tmp_path),
            "--worker-cpu-seconds",
            "0",
        ]
    )

    with pytest.raises(SystemExit) as captured:
        visual_evidence_cmd.run(args)

    assert captured.value.code == 1
    assert "worker_policy" in capsys.readouterr().err
