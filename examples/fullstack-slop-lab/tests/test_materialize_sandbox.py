from pathlib import Path
import shutil
import subprocess


FIXTURE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = FIXTURE_ROOT / "scripts" / "materialize_sandbox.sh"


def test_materialize_sandbox_excludes_runtime_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    script = source / "scripts" / "materialize_sandbox.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(SOURCE_SCRIPT, script)
    (source / "README.md").write_text("fixture source\n", encoding="utf-8")

    runtime_paths = (
        ".hallmark",
        ".ruff_cache",
        ".uidetox",
        ".venv",
        "__pycache__",
        "data",
        "dist",
        "node_modules",
    )
    for relative_path in runtime_paths:
        runtime_dir = source / relative_path
        runtime_dir.mkdir()
        (runtime_dir / "marker.txt").write_text("runtime state\n", encoding="utf-8")

    destination = tmp_path / "materialized"
    result = subprocess.run(
        [script, destination],
        check=True,
        capture_output=True,
        text=True,
    )

    assert Path(result.stdout.strip()) == destination
    assert (destination / "README.md").read_text(encoding="utf-8") == "fixture source\n"
    for relative_path in runtime_paths:
        assert not (destination / relative_path).exists()
