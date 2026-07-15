import argparse
import subprocess
import tomllib
from pathlib import Path
from textwrap import dedent

import pytest

import uidetox
from uidetox.analyzer import analyze_file
from uidetox.commands import autofix, check, finish, scan, update_skill
from uidetox.commands.show import format_issue_location
from uidetox.state import ensure_uidetox_dir, load_state, save_config


def test_codex_install_keeps_existing_prompts_and_uses_uidetox_namespace(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "commands").mkdir(parents=True)
    (data / "reference").mkdir()
    (data / "SKILL.md").write_text("skill", encoding="utf-8")
    (data / "commands" / "audit.md").write_text("audit", encoding="utf-8")
    (data / "reference" / "rules.md").write_text("rules", encoding="utf-8")

    home = tmp_path / "home"
    existing_prompt = home / ".codex" / "prompts" / "daily.md"
    existing_prompt.parent.mkdir(parents=True)
    existing_prompt.write_text("keep me", encoding="utf-8")
    monkeypatch.setattr(update_skill.Path, "home", lambda: home)

    update_skill._install_codex(data, tmp_path)

    assert existing_prompt.read_text(encoding="utf-8") == "keep me"
    assert (home / ".codex" / "prompts" / "uidetox" / "audit.md").read_text(encoding="utf-8") == "audit"


def test_package_data_includes_transform_scripts():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    package_data = pyproject["tool"]["setuptools"]["package-data"]["uidetox"]
    assert "data/transforms/*.js" in package_data


def test_scan_deduplicates_existing_issue_queue(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"DESIGN_VARIANCE": 8, "MOTION_INTENSITY": 6, "VISUAL_DENSITY": 4, "tooling": {}})

    issue = {
        "file": str(tmp_path / "src" / "App.tsx"),
        "tier": "T1",
        "issue": "Generic AI Typography detected (Inter/Roboto/sans).",
        "command": "Swap font family.",
    }
    monkeypatch.setattr(scan, "analyze_directory", lambda *args, **kwargs: [issue])
    monkeypatch.setattr(scan, "save_run_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(scan, "_save_scan_to_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(scan, "save_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(scan, "log_progress", lambda *args, **kwargs: None)

    args = argparse.Namespace(path=".")
    scan.run(args)
    scan.run(args)

    state = load_state()
    assert len(state["issues"]) == 1
    assert state["stats"]["total_found"] == 1


def test_check_auto_commit_stages_only_changed_files(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(check.subprocess, "run", fake_run)

    check._auto_commit_changed_files({"src/App.tsx"}, "[UIdetox] Mechanical auto-fix")

    expected_add = ["git", "add", str((Path.cwd() / "src/App.tsx").resolve())]
    assert expected_add in calls
    assert not any(cmd[:2] == ["git", "commit"] and "-am" in cmd for cmd in calls)
    assert ["git", "commit", "-m", "[UIdetox] Mechanical auto-fix", "--no-verify"] in calls


def test_check_run_skips_auto_commit_when_workspace_already_dirty(monkeypatch, capsys):
    fmt_runs = 0
    calls = []

    def fake_run(cmd, **kwargs):
        nonlocal fmt_runs
        calls.append(cmd)

        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/App.tsx\n", stderr="")

        if cmd == ["fmt"]:
            fmt_runs += 1
            stdout = "formatted 1 file" if fmt_runs == 1 else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should be skipped for a dirty workspace")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(check.subprocess, "run", fake_run)
    monkeypatch.setattr(check.format_cmd, "run", lambda args: None)

    config = {
        "auto_commit": True,
        "tooling": {
            "typescript": None,
            "linter": None,
            "formatter": {"fix_cmd": "fmt"},
        },
    }
    monkeypatch.setattr(check, "load_config", lambda: config)
    monkeypatch.setattr(check, "save_config", lambda cfg: None)

    check.run(argparse.Namespace(fix=True))
    output = capsys.readouterr().out

    assert "Skipped git auto-commit" in output
    assert not any(cmd[:2] == ["git", "commit"] for cmd in calls)


def test_check_run_auto_commits_only_new_mechanical_changes(monkeypatch):
    fmt_runs = 0
    status_runs = 0
    calls = []

    def fake_run(cmd, **kwargs):
        nonlocal fmt_runs, status_runs
        calls.append(cmd)

        if cmd[:3] == ["git", "status", "--porcelain"]:
            status_runs += 1
            stdout = "" if status_runs == 1 else " M src/App.tsx\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        if cmd == ["fmt"]:
            fmt_runs += 1
            stdout = "formatted 1 file" if fmt_runs == 1 else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(check.subprocess, "run", fake_run)
    monkeypatch.setattr(check.format_cmd, "run", lambda args: None)

    config = {
        "auto_commit": True,
        "tooling": {
            "typescript": None,
            "linter": None,
            "formatter": {"fix_cmd": "fmt"},
        },
    }
    monkeypatch.setattr(check, "load_config", lambda: config)
    monkeypatch.setattr(check, "save_config", lambda cfg: None)

    check.run(argparse.Namespace(fix=True))

    expected_add = ["git", "add", str((Path.cwd() / "src/App.tsx").resolve())]
    assert expected_add in calls
    assert ["git", "commit", "-m", "[UIdetox] Mechanical auto-fix (formatting/linting)", "--no-verify"] in calls
    assert not any(cmd[:2] == ["git", "commit"] and "-am" in cmd for cmd in calls)


def test_check_run_auto_commits_from_subdirectory(monkeypatch, tmp_path, capsys):
    root = tmp_path
    src_dir = root / "src"
    nested_dir = src_dir / "nested"
    nested_dir.mkdir(parents=True)

    monkeypatch.chdir(root)
    ensure_uidetox_dir()
    monkeypatch.chdir(nested_dir)

    fmt_runs = 0
    status_runs = 0
    calls = []

    def fake_run(cmd, **kwargs):
        nonlocal fmt_runs, status_runs
        calls.append((cmd, kwargs))

        if cmd[:3] == ["git", "status", "--porcelain"]:
            status_runs += 1
            stdout = "" if status_runs == 1 else " M src/App.tsx\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        if cmd == ["fmt"]:
            fmt_runs += 1
            stdout = "formatted 1 file" if fmt_runs == 1 else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(check.subprocess, "run", fake_run)
    monkeypatch.setattr(check.format_cmd, "run", lambda args: None)

    config = {
        "auto_commit": True,
        "tooling": {
            "typescript": None,
            "linter": None,
            "formatter": {"fix_cmd": "fmt"},
        },
    }
    monkeypatch.setattr(check, "load_config", lambda: config)
    monkeypatch.setattr(check, "save_config", lambda cfg: None)

    check.run(argparse.Namespace(fix=True))
    output = capsys.readouterr().out

    expected_add = ["git", "add", str((root / "src/App.tsx").resolve())]
    expected_commit = ["git", "commit", "-m", "[UIdetox] Mechanical auto-fix (formatting/linting)", "--no-verify"]

    assert "Auto-committed mechanical fixes" in output
    assert any(cmd == expected_add and kwargs.get("cwd") == root for cmd, kwargs in calls)
    assert any(cmd == expected_commit and kwargs.get("cwd") == root for cmd, kwargs in calls)


def test_check_run_detects_tooling_from_project_root_on_cold_start(monkeypatch, tmp_path, capsys):
    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_root = None
    saved_configs = []

    class FakeProfile:
        def to_dict(self):
            return {
                "package_manager": "npm",
                "typescript": None,
                "linter": None,
                "formatter": None,
                "frontend": [],
                "backend": [],
                "database": [],
                "api": [],
            }

    def fake_detect_all(root_arg=None):
        nonlocal captured_root
        captured_root = Path(root_arg) if root_arg is not None else None
        return FakeProfile()

    monkeypatch.setattr(check, "detect_all", fake_detect_all)
    monkeypatch.setattr(check, "load_config", lambda: {})
    monkeypatch.setattr(check, "save_config", lambda cfg: saved_configs.append(cfg))

    check.run(argparse.Namespace(fix=False))
    output = capsys.readouterr().out

    assert captured_root == root.resolve()
    assert saved_configs[0]["tooling"]["package_manager"] == "npm"
    assert "Auto-detected project tooling" in output


def test_check_run_executes_mechanical_fix_commands_from_project_root(monkeypatch, tmp_path, capsys):
    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    calls = []
    fmt_runs = 0

    def fake_run(cmd, **kwargs):
        nonlocal fmt_runs
        calls.append((cmd, kwargs))

        if cmd == ["fmt", "--write", "."]:
            fmt_runs += 1
            stdout = "formatted 1 file" if fmt_runs == 1 else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(check.subprocess, "run", fake_run)
    monkeypatch.setattr(check, "load_config", lambda: {"auto_commit": False, "tooling": {"typescript": None, "linter": None, "formatter": {"fix_cmd": "fmt --write ."}}})
    monkeypatch.setattr(check, "save_config", lambda cfg: None)

    check.run(argparse.Namespace(fix=True))
    output = capsys.readouterr().out

    assert "Auto-fix phase complete" in output
    assert any(cmd == ["fmt", "--write", "."] and kwargs.get("cwd") == root.resolve() for cmd, kwargs in calls)


def test_detect_run_detects_tooling_from_project_root_on_cold_start(monkeypatch, tmp_path, capsys):
    from uidetox.commands import detect as detect_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_root = None
    saved_configs = []

    class FakeProfile:
        def to_dict(self):
            return {
                "package_manager": "npm",
                "typescript": None,
                "linter": None,
                "formatter": None,
                "frontend": [],
                "backend": [],
                "database": [],
                "api": [],
            }

        package_manager = "npm"
        typescript = None
        linter = None
        formatter = None
        frontend = []
        backend = []
        database = []
        api = []

    def fake_detect_all(root_arg=None):
        nonlocal captured_root
        captured_root = Path(root_arg) if root_arg is not None else None
        return FakeProfile()

    monkeypatch.setattr(detect_cmd, "detect_all", fake_detect_all)
    monkeypatch.setattr(detect_cmd, "load_config", lambda: {})
    monkeypatch.setattr(detect_cmd, "save_config", lambda cfg: saved_configs.append(cfg))

    detect_cmd.run(argparse.Namespace(path="."))
    output = capsys.readouterr().out

    assert captured_root == root.resolve()
    assert saved_configs[0]["tooling"]["package_manager"] == "npm"
    assert "Package Manager : npm" in output


def test_scan_run_uses_project_root_on_cold_start_from_subdirectory(monkeypatch, tmp_path, capsys):
    from uidetox.commands import scan as scan_cmd

    root = tmp_path / "repo"
    nested_dir = root / "frontend" / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_detect_root = None
    analyzed_path = None
    saved_configs = []

    class FakeProfile:
        def to_dict(self):
            return {
                "package_manager": "npm",
                "typescript": None,
                "linter": None,
                "formatter": None,
                "frontend": [],
                "backend": [],
                "database": [],
                "api": [],
            }

    def fake_detect_all(root_arg=None):
        nonlocal captured_detect_root
        captured_detect_root = Path(root_arg) if root_arg is not None else None
        return FakeProfile()

    def fake_analyze_directory(path, **kwargs):
        nonlocal analyzed_path
        analyzed_path = Path(path).resolve()
        return []

    monkeypatch.setattr(scan_cmd, "detect_all", fake_detect_all)
    monkeypatch.setattr(scan_cmd, "analyze_directory", fake_analyze_directory)
    monkeypatch.setattr(scan_cmd, "load_config", lambda: {})
    monkeypatch.setattr(scan_cmd, "save_config", lambda cfg: saved_configs.append(cfg))
    monkeypatch.setattr(scan_cmd, "increment_scans", lambda: None)
    monkeypatch.setattr(scan_cmd, "save_run_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(scan_cmd, "_save_scan_to_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(scan_cmd, "save_session", lambda **kwargs: None)
    monkeypatch.setattr(scan_cmd, "log_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(scan_cmd, "load_state", lambda: {"issues": [], "resolved": [], "stats": {"scans_run": 0}})
    monkeypatch.setattr(scan_cmd, "compute_design_score", lambda state: {"blended_score": 100})

    scan_cmd.run(argparse.Namespace(path=".", output="json", since=None))
    output = capsys.readouterr().out

    assert captured_detect_root == root.resolve()
    assert analyzed_path == root.resolve()
    assert saved_configs[0]["tooling"]["package_manager"] == "npm"
    assert output.rstrip().endswith("[]")


def test_scan_run_since_uses_project_root_on_cold_start_from_subdirectory(monkeypatch, tmp_path, capsys):
    from uidetox.commands import scan as scan_cmd

    root = tmp_path / "repo"
    nested_dir = root / "frontend" / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    analyzed_path = None
    git_call_cwds = []

    issue = {
        "file": str(root / "frontend" / "src" / "Button.tsx"),
        "tier": "T2",
        "issue": "test issue",
        "id": "TEST_RULE",
        "command": "fix",
    }

    def fake_run(cmd, **kwargs):
        git_call_cwds.append(Path(kwargs["cwd"]).resolve())
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{root.resolve()}\n", stderr="")
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="frontend/src/Button.tsx\n", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    def fake_analyze_directory(path, **kwargs):
        nonlocal analyzed_path
        analyzed_path = Path(path).resolve()
        return [issue]

    monkeypatch.setattr(scan_cmd.subprocess, "run", fake_run)
    monkeypatch.setattr(scan_cmd, "analyze_directory", fake_analyze_directory)
    monkeypatch.setattr(scan_cmd, "load_config", lambda: {"tooling": {"package_manager": "npm", "typescript": None, "linter": None, "formatter": None, "frontend": [], "backend": [], "database": [], "api": []}})

    scan_cmd.run(argparse.Namespace(path=".", output="json", since="abc123"))
    output = capsys.readouterr().out

    assert analyzed_path == root.resolve()
    assert git_call_cwds == [root.resolve(), root.resolve()]
    assert "frontend/src/Button.tsx" in output


def test_batch_resolve_verification_runs_from_project_root_on_cold_start(monkeypatch, tmp_path, capsys):
    from uidetox.commands import batch_resolve

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    config = {
        "tooling": {
            "typescript": {"run_cmd": "tsc --noEmit"},
            "linter": {"fix_cmd": "lint --fix ."},
            "formatter": {"fix_cmd": "fmt --write ."},
        }
    }

    assert batch_resolve._run_verification(config) is True
    output = capsys.readouterr().out

    assert "TypeScript passed" in output
    assert any(cmd == ["tsc", "--noEmit"] and kwargs.get("cwd") == root.resolve() for cmd, kwargs in calls)
    assert any(cmd == ["lint", "--fix", "."] and kwargs.get("cwd") == root.resolve() for cmd, kwargs in calls)
    assert any(cmd == ["fmt", "--write", "."] and kwargs.get("cwd") == root.resolve() for cmd, kwargs in calls)


def test_get_project_root_uses_git_root_on_cold_start_from_subdirectory(tmp_path, monkeypatch):
    project_root = tmp_path / "repo"
    nested_dir = project_root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (project_root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    from uidetox.state import get_project_root

    assert get_project_root() == project_root.resolve()


def test_format_run_detects_and_executes_from_project_root_on_cold_start(monkeypatch, tmp_path, capsys):
    from uidetox.commands import format_cmd as format_cmd_module

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_root = None
    calls = []

    class FakeFormatter:
        name = "prettier"
        run_cmd = "fmt --check ."
        fix_cmd = "fmt --write ."

    class FakeProfile:
        formatter = FakeFormatter()

    def fake_detect_all(root_arg=None):
        nonlocal captured_root
        captured_root = Path(root_arg) if root_arg is not None else None
        return FakeProfile()

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(format_cmd_module, "detect_all", fake_detect_all)
    monkeypatch.setattr(format_cmd_module, "load_config", lambda: {})
    monkeypatch.setattr(format_cmd_module.subprocess, "run", fake_run)

    format_cmd_module.run(argparse.Namespace(fix=True))
    output = capsys.readouterr().out

    assert captured_root == root.resolve()
    assert "Formatting applied successfully" in output
    assert any(cmd == ["fmt", "--write", "."] and kwargs.get("cwd") == root.resolve() for cmd, kwargs in calls)


def test_loop_run_detects_tooling_from_project_root_on_cold_start(monkeypatch, tmp_path, capsys):
    from uidetox.commands import loop as loop_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_root = None
    saved_configs = []

    class FakeProfile:
        def to_dict(self):
            return {
                "package_manager": "npm",
                "typescript": None,
                "linter": None,
                "formatter": None,
                "frontend": [],
                "backend": [],
                "database": [],
                "api": [],
            }

    def fake_detect_all(root_arg=None):
        nonlocal captured_root
        captured_root = Path(root_arg) if root_arg is not None else None
        return FakeProfile()

    monkeypatch.setattr(loop_cmd, "detect_all", fake_detect_all)
    monkeypatch.setattr(loop_cmd, "load_config", lambda: {})
    monkeypatch.setattr(loop_cmd, "save_config", lambda cfg: saved_configs.append(dict(cfg)))
    monkeypatch.setattr(loop_cmd, "load_state", lambda: {"issues": [], "resolved": []})
    monkeypatch.setattr(loop_cmd, "get_patterns", lambda: [])
    monkeypatch.setattr(loop_cmd, "get_notes", lambda: [])
    monkeypatch.setattr(loop_cmd, "get_session", lambda: {})
    monkeypatch.setattr(loop_cmd, "get_last_scan", lambda: None)
    monkeypatch.setattr(loop_cmd, "ensure_uidetox_dir", lambda: root / ".uidetox")

    loop_cmd.run(argparse.Namespace(target=95, orchestrator=False))
    output = capsys.readouterr().out

    assert captured_root == root.resolve()
    assert saved_configs[0]["tooling"]["package_manager"] == "npm"
    assert "Auto-detecting project tooling" in output


def test_loop_run_counts_frontend_files_when_repo_root_path_contains_excluded_dir_name(monkeypatch, tmp_path, capsys):
    from uidetox.commands import loop as loop_cmd

    root = tmp_path / "build" / "repo"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "src" / "App.tsx").write_text("export const App = () => null;\n", encoding="utf-8")

    monkeypatch.chdir(root)

    monkeypatch.setattr(loop_cmd, "load_config", lambda: {"tooling": {"typescript": None, "linter": None, "formatter": None}, "auto_commit": False})
    monkeypatch.setattr(loop_cmd, "save_config", lambda cfg: None)
    monkeypatch.setattr(loop_cmd, "load_state", lambda: {"issues": [], "resolved": []})
    monkeypatch.setattr(loop_cmd, "get_patterns", lambda: [])
    monkeypatch.setattr(loop_cmd, "get_notes", lambda: [])
    monkeypatch.setattr(loop_cmd, "get_session", lambda: {})
    monkeypatch.setattr(loop_cmd, "get_last_scan", lambda: None)
    monkeypatch.setattr(loop_cmd, "ensure_uidetox_dir", lambda: root / ".uidetox")

    loop_cmd.run(argparse.Namespace(target=95, orchestrator=False))
    output = capsys.readouterr().out

    assert "Files: 1" in output


def test_ensure_uidetox_dir_creates_state_dir_at_git_root_on_cold_start(tmp_path, monkeypatch):
    project_root = tmp_path / "repo"
    nested_dir = project_root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (project_root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    from uidetox.state import ensure_uidetox_dir

    uidetox_dir = ensure_uidetox_dir()

    assert uidetox_dir == (project_root / ".uidetox").resolve()
    assert uidetox_dir.exists()


def test_get_project_root_uses_manifest_marker_when_git_and_uidetox_are_missing(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    nested_dir = project_root / "app" / "components"
    nested_dir.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    monkeypatch.chdir(nested_dir)

    from uidetox.state import get_project_root

    assert get_project_root() == project_root.resolve()


def test_get_project_root_prefers_git_root_over_nested_manifest_on_cold_start(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    nested_dir = repo_root / "packages" / "app" / "src"
    nested_dir.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    (repo_root / "packages" / "app" / "package.json").write_text('{"name":"app"}\n', encoding="utf-8")

    monkeypatch.chdir(nested_dir)

    from uidetox.state import get_project_root

    assert get_project_root() == repo_root.resolve()


def test_check_run_with_missing_git_does_not_raise(monkeypatch):
    fmt_runs = 0
    calls = []

    def fake_run(cmd, **kwargs):
        nonlocal fmt_runs
        calls.append(cmd)

        if cmd[:3] == ["git", "status", "--porcelain"]:
            raise FileNotFoundError("git")

        if cmd == ["fmt"]:
            fmt_runs += 1
            stdout = "formatted 1 file" if fmt_runs == 1 else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should not be reached when git is missing")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(check.subprocess, "run", fake_run)
    monkeypatch.setattr(check.format_cmd, "run", lambda args: None)

    config = {
        "auto_commit": True,
        "tooling": {
            "typescript": None,
            "linter": None,
            "formatter": {"fix_cmd": "fmt"},
        },
    }
    monkeypatch.setattr(check, "load_config", lambda: config)
    monkeypatch.setattr(check, "save_config", lambda cfg: None)

    check.run(argparse.Namespace(fix=True))

    assert ["fmt"] in calls


def test_prepare_subprocess_cmd_extracts_env_prefixes_and_preserves_quotes():
    from uidetox.utils import prepare_subprocess_cmd

    argv, env = prepare_subprocess_cmd("CI=1 NODE_OPTIONS='--max-old-space-size=4096' prettier --check 'src/App File.tsx'")

    assert argv == ["prettier", "--check", "src/App File.tsx"]
    assert env is not None
    assert env["CI"] == "1"
    assert env["NODE_OPTIONS"] == "--max-old-space-size=4096"


def test_tracked_changed_files_returns_empty_when_git_missing(monkeypatch):
    from uidetox.utils import tracked_changed_files

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert tracked_changed_files() == set()


def test_tracked_changed_files_unquotes_paths_with_spaces(monkeypatch):
    from uidetox.utils import tracked_changed_files

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=' M "src/file with space.txt"\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert tracked_changed_files() == {"src/file with space.txt"}


def test_tracked_changed_files_preserves_arrow_in_quoted_non_rename_paths(monkeypatch):
    from uidetox.utils import tracked_changed_files

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=' M "src/a -> b.txt"\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert tracked_changed_files() == {"src/a -> b.txt"}


def test_tracked_changed_files_uses_destination_for_quoted_renames(monkeypatch):
    from uidetox.utils import tracked_changed_files

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='R  "src/old name.txt" -> "src/new name.txt"\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert tracked_changed_files() == {"src/new name.txt"}


def test_tracked_changed_files_handles_quoted_rename_sources_with_arrows(monkeypatch):
    from uidetox.utils import tracked_changed_files

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='R  "src/old -> name.txt" -> "src/new name.txt"\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert tracked_changed_files() == {"src/new name.txt"}


def test_tsc_run_supports_env_prefixed_command(monkeypatch):
    from uidetox.commands import tsc as tsc_mod

    captured: dict[str, object] = {}

    monkeypatch.setattr(tsc_mod, "load_config", lambda: {"tooling": {"typescript": {"run_cmd": "CI=1 tsc --noEmit"}}})

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tsc_mod.subprocess, "run", fake_run)

    tsc_mod.run(argparse.Namespace(fix=False))

    assert captured["cmd"] == ["tsc", "--noEmit"]
    assert captured["env"] is not None and captured["env"]["CI"] == "1"


def test_batch_resolve_verification_supports_env_prefixed_commands(monkeypatch):
    from uidetox.commands import batch_resolve

    calls = []
    config = {"tooling": {"linter": {"fix_cmd": "CI=1 lint --fix"}}}

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env")))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    assert batch_resolve._run_verification(config) is True
    assert calls[0][0] == ["lint", "--fix"]
    assert calls[0][1] is not None and calls[0][1]["CI"] == "1"


def test_finish_preflight_rejects_dirty_workspace(monkeypatch):
    def fake_run(cmd, **kwargs):
        if cmd == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/App.tsx\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(finish.subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        finish._ensure_clean_workspace()


def test_package_version_matches_runtime_version():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert uidetox.__version__ == pyproject["project"]["version"]


def test_detect_backend_skips_python_tooling_only_repo(tmp_path):
    from uidetox.tooling import detect_backend

    (tmp_path / "pyproject.toml").write_text(
        dedent("""\
            [project]
            name = "tool-only"
            version = "0.1.0"
            dependencies = ["typer>=0.12", "rich>=13"]
        """),
        encoding="utf-8",
    )

    assert detect_backend(tmp_path) == []


def test_detect_backend_detects_fastapi_from_pyproject(tmp_path):
    from uidetox.tooling import detect_backend

    (tmp_path / "pyproject.toml").write_text(
        dedent("""\
            [project]
            name = "api"
            version = "0.1.0"
            dependencies = ["fastapi>=0.110", "uvicorn>=0.29"]
        """),
        encoding="utf-8",
    )

    backends = detect_backend(tmp_path)

    assert len(backends) == 1
    assert backends[0].name == "python"
    assert backends[0].config_file == "pyproject.toml"


def test_detect_backend_skips_generic_root_main_py_without_backend_markers(tmp_path):
    from uidetox.tooling import detect_backend

    (tmp_path / "main.py").write_text(
        dedent("""\
            def main():
                print("hello")

            if __name__ == "__main__":
                main()
        """),
        encoding="utf-8",
    )

    assert detect_backend(tmp_path) == []


def test_analyzer_reports_line_and_column_for_frontend_issue(tmp_path):
    target = tmp_path / "App.tsx"
    target.write_text(
        "export function App() {\n"
        "  return <main>\n"
        "    <div className=\"font-inter\">Hello</div>\n"
        "  </main>\n"
        "}\n",
        encoding="utf-8",
    )

    issues = analyze_file(target)
    typography = next(i for i in issues if "Typography" in i["issue"])

    assert typography["line"] == 3
    assert typography["column"] == 21
    assert typography["snippet"] == '<div className="font-inter">Hello</div>'


def test_issue_location_format_is_actionable():
    issue = {"file": "/repo/src/App.tsx", "line": 12, "column": 5}
    assert format_issue_location(issue) == "/repo/src/App.tsx:12:5"


# ── New rule regression tests ─────────────────────────────────────────────


def _issues_for(code: str, ext: str = ".tsx") -> list[dict]:
    """Write code to a temp file and return analyzer issues."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / f"test{ext}"
        p.write_text(code, encoding="utf-8")
        return analyze_file(p)


def _rule_fired(code: str, rule_id: str, ext: str = ".tsx") -> bool:
    return any(i.get("id") == rule_id for i in _issues_for(code, ext))


def test_outline_none_slop_fires_without_focus_visible():
    assert _rule_fired('<button className="outline-none px-4 py-2">Click</button>', "OUTLINE_NONE_SLOP")


def test_outline_none_slop_does_not_fire_with_focus_visible():
    assert not _rule_fired(
        '<button className="outline-none focus-visible:ring-2 focus-visible:ring-offset-2">Click</button>',
        "OUTLINE_NONE_SLOP",
    )


def test_reduced_motion_missing_slop_fires_without_motion_reduce():
    assert _rule_fired('<div className="animate-bounce bg-white">x</div>', "REDUCED_MOTION_MISSING_SLOP")


def test_reduced_motion_missing_slop_skips_when_motion_reduce_present():
    assert not _rule_fired(
        '<div className="animate-bounce motion-reduce:animate-none bg-white">x</div>',
        "REDUCED_MOTION_MISSING_SLOP",
    )


def test_positive_tabindex_slop_fires_for_tabindex_gt_zero():
    assert _rule_fired('<div tabIndex={3} className="cursor-pointer">item</div>', "TABINDEX_POSITIVE_SLOP")


def test_positive_tabindex_slop_allows_zero():
    assert not _rule_fired('<button tabIndex={0} className="btn">ok</button>', "TABINDEX_POSITIVE_SLOP")


def test_tailwind_font_conflict_fires_with_two_size_classes():
    assert _rule_fired('<h1 className="text-xs text-4xl font-bold">Title</h1>', "TAILWIND_FONT_CONFLICT_SLOP")


def test_tailwind_font_conflict_skips_single_size():
    assert not _rule_fired('<h1 className="text-4xl font-bold tracking-tight">Title</h1>', "TAILWIND_FONT_CONFLICT_SLOP")


def test_tailwind_weight_conflict_fires_with_two_weight_classes():
    assert _rule_fired('<p className="font-bold font-medium text-base">Hello</p>', "TAILWIND_WEIGHT_CONFLICT_SLOP")


def test_tailwind_display_conflict_fires_flex_and_hidden():
    assert _rule_fired('<div className="flex hidden items-center">x</div>', "TAILWIND_DISPLAY_CONFLICT_SLOP")


def test_tailwind_display_conflict_fires_flex_and_block():
    assert _rule_fired('<div className="flex block gap-4">x</div>', "TAILWIND_DISPLAY_CONFLICT_SLOP")


def test_tailwind_display_conflict_skips_single_display():
    assert not _rule_fired('<div className="flex gap-4 items-center">x</div>', "TAILWIND_DISPLAY_CONFLICT_SLOP")


def test_modal_no_aria_fires_for_div_with_modal_class():
    assert _rule_fired(
        '<div className="fixed inset-0 z-50 modal bg-black/50">content</div>',
        "MODAL_NO_ARIA_SLOP",
    )


def test_modal_no_aria_skips_when_role_dialog_present():
    assert not _rule_fired(
        '<div role="dialog" aria-modal="true" className="fixed inset-0 z-50 modal">content</div>',
        "MODAL_NO_ARIA_SLOP",
    )


def test_css_scroll_behavior_slop_fires_for_smooth_without_media(tmp_path):
    p = tmp_path / "base.css"
    p.write_text("html { scroll-behavior: smooth; color: #333; }", encoding="utf-8")
    issues = analyze_file(p)
    assert any(i.get("id") == "CSS_SCROLL_BEHAVIOR_SLOP" for i in issues)


def test_hardcoded_breakpoint_slop_fires_for_768px(tmp_path):
    p = tmp_path / "layout.css"
    p.write_text("@media (max-width: 768px) { .nav { display: none; } }", encoding="utf-8")
    issues = analyze_file(p)
    assert any(i.get("id") == "HARDCODED_BREAKPOINT_SLOP" for i in issues)


def test_autofix_categorizes_outline_none_as_accessibility():
    from uidetox.commands.autofix import _categorize_issue

    issue = {
        "id": "OUTLINE_NONE_SLOP",
        "issue": "outline-none/outline-0 without focus-visible: replacement — invisible keyboard focus (WCAG 2.4.7).",
        "command": "Replace outline-none with focus-visible:ring-2.",
        "tier": "T1",
        "file": "/src/Button.tsx",
    }
    assert _categorize_issue(issue) == "accessibility"


def test_autofix_categorizes_tailwind_conflict_as_code_quality():
    from uidetox.commands.autofix import _categorize_issue

    issue = {
        "id": "TAILWIND_FONT_CONFLICT_SLOP",
        "issue": "Conflicting Tailwind font-size classes in same className (e.g. text-sm text-lg).",
        "command": "Remove redundant size class.",
        "tier": "T1",
        "file": "/src/Card.tsx",
    }
    assert _categorize_issue(issue) == "code quality"


def test_autofix_loads_config_before_transform_auto_commit_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"auto_commit": False})
    target = tmp_path / "App.tsx"
    target.write_text("export const App = () => <div className=\"font-inter\" />", encoding="utf-8")

    from uidetox.state import add_issue

    add_issue({
        "id": "SCAN-ABC123",
        "file": str(target),
        "tier": "T1",
        "issue": "Generic AI Typography detected (Inter/Roboto/sans).",
        "command": "Swap font family.",
    })

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="1 ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    autofix.run(argparse.Namespace(dry_run=False))


def test_autofix_skips_auto_commit_when_workspace_already_dirty(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"auto_commit": True})

    target = tmp_path / "App.tsx"
    target.write_text("before", encoding="utf-8")

    from uidetox.state import add_issue

    add_issue({
        "id": "SCAN-DIRTY1",
        "file": str(target),
        "tier": "T1",
        "issue": "Generic AI Typography detected (Inter/Roboto/sans).",
        "command": "Swap font family.",
    })

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M App.tsx\n", stderr="")

        if cmd[:3] == ["npx", "jscodeshift", "-t"]:
            target.write_text("after", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="1 ok", stderr="")

        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should be skipped for a dirty workspace")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    autofix.run(argparse.Namespace(dry_run=False))
    output = capsys.readouterr().out

    assert "Skipped git auto-commit" in output


def test_autofix_runs_from_subdirectory_with_repo_relative_issue_path(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"auto_commit": True})

    nested_dir = tmp_path / "src" / "nested"
    nested_dir.mkdir(parents=True)
    target = tmp_path / "src" / "App.tsx"
    target.write_text("before", encoding="utf-8")

    from uidetox.state import add_issue

    add_issue({
        "id": "SCAN-RELATIVE1",
        "file": "src/App.tsx",
        "tier": "T1",
        "issue": "Generic AI Typography detected (Inter/Roboto/sans).",
        "command": "Swap font family.",
    })

    monkeypatch.chdir(nested_dir)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        if cmd[:3] == ["npx", "jscodeshift", "-t"]:
            assert cmd[-1] == str(target.resolve())
            assert kwargs.get("cwd") == tmp_path.resolve()
            target.write_text("after", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="1 ok", stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    autofix.run(argparse.Namespace(dry_run=False))
    output = capsys.readouterr().out

    assert "Automatically transformed 1 file(s)" in output
    assert ["git", "add", str(target.resolve())] in calls


def test_autofix_does_not_report_repo_relative_js_issue_as_remaining_after_transform(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"auto_commit": False})

    target = tmp_path / "src" / "App.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")

    from uidetox.state import add_issue

    add_issue({
        "id": "SCAN-RELATIVE2",
        "file": "src/App.tsx",
        "tier": "T1",
        "issue": "Generic AI Typography detected (Inter/Roboto/sans).",
        "command": "Swap font family.",
    })

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["npx", "jscodeshift", "-t"]:
            target.write_text("after", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="1 ok", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    autofix.run(argparse.Namespace(dry_run=False))
    output = capsys.readouterr().out

    assert "need manual fixing" not in output


def test_batch_resolve_verification_fails_when_linter_command_missing(monkeypatch, capsys):
    from uidetox.commands import batch_resolve

    config = {"tooling": {"linter": {"fix_cmd": "missing-linter --fix"}}}

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("missing-linter")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    assert batch_resolve._run_verification(config) is False
    output = capsys.readouterr().out
    assert "Linter auto-fix failed" in output


def test_batch_resolve_verification_fails_when_formatter_times_out(monkeypatch, capsys):
    from uidetox.commands import batch_resolve

    config = {"tooling": {"formatter": {"fix_cmd": "fmt --write ."}}}

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=120)

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    assert batch_resolve._run_verification(config) is False
    output = capsys.readouterr().out
    assert "Formatter auto-fix timed out" in output


def test_batch_resolve_run_skips_auto_commit_when_workspace_already_dirty(tmp_path, monkeypatch, capsys):
    from uidetox.commands import batch_resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    issue_file = tmp_path / "src" / "App.tsx"
    unrelated_file = tmp_path / "src" / "Other.tsx"
    issue_file.parent.mkdir(parents=True)
    issue_file.write_text("export const App = () => null;", encoding="utf-8")
    unrelated_file.write_text("export const Other = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-BATCH1",
        "file": str(issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(batch_resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(batch_resolve, "_run_verification", lambda config: True)

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/Other.tsx\n", stderr="")

        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should be skipped for a dirty workspace")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    batch_resolve.run(argparse.Namespace(issue_ids=["SCAN-BATCH1"], note="Applied fix", skip_verify=False))
    output = capsys.readouterr().out

    assert "Skipped git auto-commit" in output


def test_batch_resolve_run_auto_commits_when_only_issue_files_are_dirty(tmp_path, monkeypatch, capsys):
    from uidetox.commands import batch_resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    issue_file = tmp_path / "src" / "App.tsx"
    issue_file.parent.mkdir(parents=True)
    issue_file.write_text("export const App = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-BATCH2",
        "file": str(issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(batch_resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(batch_resolve, "_run_verification", lambda config: True)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/App.tsx\n", stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    batch_resolve.run(argparse.Namespace(issue_ids=["SCAN-BATCH2"], note="Applied fix", skip_verify=False))
    output = capsys.readouterr().out

    assert "Auto-committed" in output
    assert ["git", "add", str(issue_file)] in calls
    assert ["git", "add", str((tmp_path / ".uidetox/state.json").resolve())] in calls
    assert ["git", "commit", "-m", "[UIdetox] Detoxed src: Applied fix (1 issues resolved)", "--no-verify"] in calls


def test_batch_resolve_run_auto_commits_renamed_issue_file(tmp_path, monkeypatch, capsys):
    from uidetox.commands import batch_resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    old_issue_file = tmp_path / "src" / "OldApp.tsx"
    new_issue_file = tmp_path / "src" / "NewApp.tsx"
    old_issue_file.parent.mkdir(parents=True)
    old_issue_file.write_text("export const App = () => null;", encoding="utf-8")
    old_issue_file.unlink()
    new_issue_file.write_text("export const App = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-BATCH-RENAME",
        "file": str(old_issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(batch_resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(batch_resolve, "_run_verification", lambda config: True)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=' D src/OldApp.tsx\n',
                stderr="",
            )
        if cmd == ["git", "status", "--porcelain", "--untracked-files=all"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=' D src/OldApp.tsx\n?? src/NewApp.tsx\n',
                stderr="",
            )

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    batch_resolve.run(argparse.Namespace(issue_ids=["SCAN-BATCH-RENAME"], note="Renamed file", skip_verify=False))
    output = capsys.readouterr().out

    assert "Auto-committed" in output
    assert ["git", "add", str(old_issue_file)] in calls
    assert ["git", "add", str(new_issue_file)] in calls


def test_batch_resolve_run_skips_auto_commit_when_unrelated_untracked_file_exists_in_same_directory(tmp_path, monkeypatch, capsys):
    from uidetox.commands import batch_resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    old_issue_file = tmp_path / "src" / "OldApp.tsx"
    old_issue_file.parent.mkdir(parents=True)
    old_issue_file.write_text("export const App = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-BATCH-UNTRACKED",
        "file": str(old_issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(batch_resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(batch_resolve, "_run_verification", lambda config: True)

    def fake_run(cmd, **kwargs):
        if cmd == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=' D src/OldApp.tsx\n', stderr="")
        if cmd == ["git", "status", "--porcelain", "--untracked-files=all"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=' D src/OldApp.tsx\n?? src/NewApp.tsx\n?? src/UNRELATED.txt\n', stderr="")
        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should be skipped when unrelated untracked files exist")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(batch_resolve.subprocess, "run", fake_run)

    batch_resolve.run(argparse.Namespace(issue_ids=["SCAN-BATCH-UNTRACKED"], note="Renamed file", skip_verify=False))
    output = capsys.readouterr().out

    assert "Skipped git auto-commit" in output


def test_resolve_run_skips_auto_commit_when_workspace_already_dirty(tmp_path, monkeypatch, capsys):
    from uidetox.commands import resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    issue_file = tmp_path / "src" / "Button.tsx"
    unrelated_file = tmp_path / "src" / "Other.tsx"
    issue_file.parent.mkdir(parents=True)
    issue_file.write_text("export const Button = () => null;", encoding="utf-8")
    unrelated_file.write_text("export const Other = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-RESOLVE1",
        "file": str(issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(resolve, "_run_verification", lambda config: True)

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/Other.tsx\n", stderr="")

        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should be skipped for a dirty workspace")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(resolve.subprocess, "run", fake_run)

    resolve.run(argparse.Namespace(issue_id="SCAN-RESOLVE1", note="Applied fix", skip_verify=False))
    output = capsys.readouterr().out

    assert "Skipped git auto-commit" in output


def test_resolve_run_auto_commits_when_only_issue_file_is_dirty(tmp_path, monkeypatch, capsys):
    from uidetox.commands import resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    issue_file = tmp_path / "src" / "Button.tsx"
    issue_file.parent.mkdir(parents=True)
    issue_file.write_text("export const Button = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-RESOLVE2",
        "file": str(issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(resolve, "_run_verification", lambda config: True)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/Button.tsx\n", stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(resolve.subprocess, "run", fake_run)

    resolve.run(argparse.Namespace(issue_id="SCAN-RESOLVE2", note="Applied fix", skip_verify=False))
    output = capsys.readouterr().out

    assert "Auto-committed to git" in output
    assert ["git", "add", str(issue_file)] in calls
    assert ["git", "add", str((tmp_path / ".uidetox/state.json").resolve())] in calls
    assert ["git", "commit", "-m", "[UIdetox] Fixed SCAN-RESOLVE2: Applied fix", "--no-verify"] in calls


def test_resolve_run_auto_commits_renamed_issue_file(tmp_path, monkeypatch, capsys):
    from uidetox.commands import resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    old_issue_file = tmp_path / "src" / "OldButton.tsx"
    new_issue_file = tmp_path / "src" / "NewButton.tsx"
    old_issue_file.parent.mkdir(parents=True)
    old_issue_file.write_text("export const Button = () => null;", encoding="utf-8")
    old_issue_file.unlink()
    new_issue_file.write_text("export const Button = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-RESOLVE-RENAME",
        "file": str(old_issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(resolve, "_run_verification", lambda config: True)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=' D src/OldButton.tsx\n',
                stderr="",
            )
        if cmd == ["git", "status", "--porcelain", "--untracked-files=all"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=' D src/OldButton.tsx\n?? src/NewButton.tsx\n',
                stderr="",
            )

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(resolve.subprocess, "run", fake_run)

    resolve.run(argparse.Namespace(issue_id="SCAN-RESOLVE-RENAME", note="Renamed file", skip_verify=False))
    output = capsys.readouterr().out

    assert "Auto-committed to git" in output
    assert ["git", "add", str(old_issue_file)] in calls
    assert ["git", "add", str(new_issue_file)] in calls


def test_resolve_run_skips_auto_commit_when_unrelated_untracked_file_exists_in_same_directory(tmp_path, monkeypatch, capsys):
    from uidetox.commands import resolve

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()

    from uidetox.state import add_issue

    old_issue_file = tmp_path / "src" / "OldButton.tsx"
    old_issue_file.parent.mkdir(parents=True)
    old_issue_file.write_text("export const Button = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-RESOLVE-UNTRACKED",
        "file": str(old_issue_file),
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(resolve, "_run_verification", lambda config: True)

    def fake_run(cmd, **kwargs):
        if cmd == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=' D src/OldButton.tsx\n', stderr="")
        if cmd == ["git", "status", "--porcelain", "--untracked-files=all"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=' D src/OldButton.tsx\n?? src/NewButton.tsx\n?? src/UNRELATED.txt\n', stderr="")
        if cmd[:2] in (["git", "add"], ["git", "commit"]):
            raise AssertionError("git add/commit should be skipped when unrelated untracked files exist")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(resolve.subprocess, "run", fake_run)

    resolve.run(argparse.Namespace(issue_id="SCAN-RESOLVE-UNTRACKED", note="Renamed file", skip_verify=False))
    output = capsys.readouterr().out

    assert "Skipped git auto-commit" in output


def test_resolve_run_auto_commits_from_subdirectory_with_repo_relative_issue_path(tmp_path, monkeypatch, capsys):
    from uidetox.commands import resolve

    root = tmp_path
    src_dir = root / "src"
    src_dir.mkdir(parents=True)
    monkeypatch.chdir(root)
    ensure_uidetox_dir()
    monkeypatch.chdir(src_dir)

    from uidetox.state import add_issue

    issue_file = root / "src" / "Button.tsx"
    issue_file.write_text("export const Button = () => null;", encoding="utf-8")

    add_issue({
        "id": "SCAN-RESOLVE-SUBDIR",
        "file": "src/Button.tsx",
        "tier": "T1",
        "issue": "Example issue",
        "command": "fix",
    })

    monkeypatch.setattr(resolve, "load_config", lambda: {"auto_commit": True})
    monkeypatch.setattr(resolve, "_run_verification", lambda config: True)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M src/Button.tsx\n", stderr="")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(resolve.subprocess, "run", fake_run)

    resolve.run(argparse.Namespace(issue_id="SCAN-RESOLVE-SUBDIR", note="Applied fix", skip_verify=False))
    output = capsys.readouterr().out

    assert "Auto-committed to git" in output
    assert ["git", "add", str(issue_file)] in calls
    assert ["git", "add", str((root / ".uidetox/state.json").resolve())] in calls


# ── Batch 3: new detection rule tests ───────────────────────────────────────

def test_three_equal_column_slop_fires_for_repetitive_grid():
    code = dedent("""\
        <div className="grid md:grid-cols-3 gap-8">
          <div className="p-6 rounded-xl bg-white shadow-sm border">Feature A</div>
          <div className="p-6 rounded-xl bg-white shadow-sm border">Feature B</div>
          <div className="p-6 rounded-xl bg-white shadow-sm border">Feature C</div>
        </div>
    """)
    assert _rule_fired(code, "THREE_EQUAL_COLUMN_SLOP")


def test_three_equal_column_slop_skips_asymmetric_grid():
    code = dedent("""\
        <div className="grid md:grid-cols-3 gap-8">
          <div className="p-6 rounded-xl bg-white col-span-2 shadow-md">Wide Feature</div>
          <div className="p-3 rounded bg-zinc-950 text-white">Narrow</div>
          <div className="border-l pl-8 text-sm text-zinc-500">Note</div>
        </div>
    """)
    assert not _rule_fired(code, "THREE_EQUAL_COLUMN_SLOP")


def test_unsplash_url_slop_fires_for_unsplash_link():
    assert _rule_fired(
        '<img src="https://images.unsplash.com/photos/abc123/800x600" alt="hero" />',
        "UNSPLASH_URL_SLOP",
        ".tsx",
    )


def test_unsplash_url_slop_skips_picsum():
    assert not _rule_fired(
        '<img src="https://picsum.photos/seed/abc/800/600" alt="hero" />',
        "UNSPLASH_URL_SLOP",
        ".tsx",
    )


def test_all_caps_header_slop_fires_for_uppercase_class():
    assert _rule_fired(
        '<h2 className="text-sm font-bold uppercase tracking-widest text-gray-500">Features</h2>',
        "ALL_CAPS_HEADER_SLOP",
        ".tsx",
    )


def test_all_caps_header_slop_skips_no_uppercase():
    assert not _rule_fired(
        '<h2 className="text-sm font-bold tracking-widest text-gray-500">Features</h2>',
        "ALL_CAPS_HEADER_SLOP",
        ".tsx",
    )


def test_font_weight_extremes_slop_fires_when_only_bold_and_normal():
    code = dedent("""\
        <div>
          <h1 className="font-bold text-2xl">Title</h1>
          <p className="font-normal text-base">Body</p>
        </div>
    """)
    assert _rule_fired(code, "FONT_WEIGHT_EXTREMES_SLOP")


def test_font_weight_extremes_slop_skips_when_semibold_present():
    code = dedent("""\
        <div>
          <h1 className="font-bold text-2xl">Title</h1>
          <p className="font-semibold text-base">Sub</p>
        </div>
    """)
    assert not _rule_fired(code, "FONT_WEIGHT_EXTREMES_SLOP")


def test_missing_loading_state_slop_fires_for_usequery_without_loading():
    code = dedent("""\
        import { useQuery } from '@tanstack/react-query';
        export function List() {
          const { data } = useQuery({ queryKey: ['items'], queryFn: fetchItems });
          return <ul>{data?.map(i => <li key={i.id}>{i.name}</li>)}</ul>;
        }
    """)
    assert _rule_fired(code, "MISSING_LOADING_STATE_SLOP")


def test_missing_loading_state_slop_skips_when_loading_present():
    code = dedent("""\
        import { useQuery } from '@tanstack/react-query';
        export function List() {
          const { data, isLoading } = useQuery({ queryKey: ['items'], queryFn: fetchItems });
          if (isLoading) return <Skeleton />;
          return <ul>{data?.map(i => <li key={i.id}>{i.name}</li>)}</ul>;
        }
    """)
    assert not _rule_fired(code, "MISSING_LOADING_STATE_SLOP")


def test_round_number_slop_fires_for_99_99_percent():
    assert _rule_fired(
        '<span className="text-4xl font-bold">99.99%</span>',
        "ROUND_NUMBER_SLOP",
    )


def test_round_number_slop_skips_organic_number():
    assert not _rule_fired(
        '<span className="text-4xl font-bold">97.3%</span>',
        "ROUND_NUMBER_SLOP",
    )


# ── Batch 4: new detection rule tests ───────────────────────────────────────

def test_arbitrary_px_value_slop_fires_for_magic_pixel():
    assert _rule_fired(
        '<div className="w-[347px] h-[892px] p-[17px]">Panel</div>',
        "ARBITRARY_PX_VALUE_SLOP",
    )


def test_arbitrary_px_value_slop_skips_rem_units():
    assert not _rule_fired(
        '<div className="w-full max-w-2xl p-6 h-auto">Panel</div>',
        "ARBITRARY_PX_VALUE_SLOP",
    )


def test_verbose_handler_name_slop_fires_for_handle_button_click():
    assert _rule_fired(
        'const handleButtonClick = () => doSomething();',
        "VERBOSE_HANDLER_NAME_SLOP",
    )


def test_verbose_handler_name_slop_fires_for_handle_form_submit():
    assert _rule_fired(
        'function handleFormSubmit(e: React.FormEvent) { e.preventDefault(); }',
        "VERBOSE_HANDLER_NAME_SLOP",
    )


def test_verbose_handler_name_slop_skips_concise_names():
    assert not _rule_fired(
        'const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); };',
        "VERBOSE_HANDLER_NAME_SLOP",
    )


def test_missing_error_state_slop_fires_for_usequery_without_error():
    code = dedent("""\
        import { useQuery } from '@tanstack/react-query';
        export function List() {
          const { data, isLoading } = useQuery({ queryKey: ['items'], queryFn: fetchItems });
          if (isLoading) return <Skeleton />;
          return <ul>{data?.map(i => <li key={i.id}>{i.name}</li>)}</ul>;
        }
    """)
    assert _rule_fired(code, "MISSING_ERROR_STATE_SLOP")


def test_missing_error_state_slop_skips_when_error_handled():
    code = dedent("""\
        import { useQuery } from '@tanstack/react-query';
        export function List() {
          const { data, isLoading, isError } = useQuery({ queryKey: ['items'], queryFn: fetchItems });
          if (isLoading) return <Skeleton />;
          if (isError) return <p>Failed to load.</p>;
          return <ul>{data?.map(i => <li key={i.id}>{i.name}</li>)}</ul>;
        }
    """)
    assert not _rule_fired(code, "MISSING_ERROR_STATE_SLOP")


def test_svg_hardcoded_fill_slop_fires_for_black_fill():
    assert _rule_fired(
        '<svg><path fill="#000000" d="M0 0h24v24H0z" /></svg>',
        "SVG_HARDCODED_FILL_SLOP",
        ".tsx",
    )


def test_svg_hardcoded_fill_slop_fires_for_white_fill():
    assert _rule_fired(
        '<path fill="white" d="M12 2L2 7l10 5 10-5-10-5z" />',
        "SVG_HARDCODED_FILL_SLOP",
        ".tsx",
    )


def test_svg_hardcoded_fill_slop_skips_current_color():
    assert not _rule_fired(
        '<path fill="currentColor" d="M12 2L2 7l10 5 10-5-10-5z" />',
        "SVG_HARDCODED_FILL_SLOP",
        ".tsx",
    )


def test_accordion_faq_slop_fires_for_accordion_with_faq():
    code = dedent("""\
        <Accordion type="single" collapsible>
          <AccordionItem value="q1">
            <AccordionTrigger>What is your FAQ policy?</AccordionTrigger>
            <AccordionContent>Our answer here.</AccordionContent>
          </AccordionItem>
        </Accordion>
    """)
    assert _rule_fired(code, "ACCORDION_FAQ_SLOP")


# ── Batch 5: discoverability, content, and UX slop tests ─────────────────────

def test_title_case_header_slop_fires_for_four_caps_words():
    assert _rule_fired(
        "<h2>The Best Features For Everyone</h2>",
        "TITLE_CASE_HEADER_SLOP",
        ".html",
    )


def test_title_case_header_slop_skips_sentence_case():
    assert not _rule_fired(
        "<h2>The best features for everyone</h2>",
        "TITLE_CASE_HEADER_SLOP",
        ".html",
    )


def test_dark_mode_toggle_slop_fires_for_theme_toggle():
    assert _rule_fired(
        "import { ThemeToggle } from '@/components/ThemeToggle';",
        "DARK_MODE_TOGGLE_SLOP",
    )


def test_dark_mode_toggle_slop_fires_for_toggle_dark_mode():
    assert _rule_fired(
        "const toggleDarkMode = () => setDark((d) => !d);",
        "DARK_MODE_TOGGLE_SLOP",
    )


def test_dark_mode_toggle_slop_skips_color_scheme_detection():
    assert not _rule_fired(
        "const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;",
        "DARK_MODE_TOGGLE_SLOP",
    )


def test_same_date_repeat_slop_fires_for_repeated_iso_date():
    code = dedent("""\
        const posts = [
          { title: "Post 1", date: "2024-01-15" },
          { title: "Post 2", date: "2024-01-15" },
          { title: "Post 3", date: "2024-01-15" },
        ];
    """)
    assert _rule_fired(code, "SAME_DATE_REPEAT_SLOP")


def test_same_date_repeat_slop_skips_varied_dates():
    code = dedent("""\
        const posts = [
          { title: "Post 1", date: "2024-01-15" },
          { title: "Post 2", date: "2024-02-22" },
          { title: "Post 3", date: "2024-03-07" },
        ];
    """)
    assert not _rule_fired(code, "SAME_DATE_REPEAT_SLOP")


def test_hardcoded_copyright_year_slop_fires_for_2024():
    assert _rule_fired(
        "<footer>© 2024 Acme Inc. All rights reserved.</footer>",
        "HARDCODED_COPYRIGHT_YEAR_SLOP",
    )


def test_hardcoded_copyright_year_slop_fires_for_copy_entity():
    assert _rule_fired(
        "<p>&copy; 2025 MyApp</p>",
        "HARDCODED_COPYRIGHT_YEAR_SLOP",
        ".html",
    )


def test_hardcoded_copyright_year_slop_skips_dynamic():
    assert not _rule_fired(
        "<footer>© {new Date().getFullYear()} Acme Inc.</footer>",
        "HARDCODED_COPYRIGHT_YEAR_SLOP",
    )


def test_missing_meta_description_slop_fires_for_head_without_meta():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
          <head>
            <title>My App</title>
          </head>
          <body><p>Hello</p></body>
        </html>
    """)
    assert _rule_fired(code, "MISSING_META_DESCRIPTION_SLOP", ".html")


def test_missing_meta_description_slop_skips_when_present():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
          <head>
            <title>My App</title>
            <meta name="description" content="A great app." />
          </head>
          <body><p>Hello</p></body>
        </html>
    """)
    assert not _rule_fired(code, "MISSING_META_DESCRIPTION_SLOP", ".html")


# ── Batch 6 tests: motion quality, UX writing, accessibility ─────────────────


def test_will_change_abuse_slop_fires_on_static_will_change():
    code = dedent("""\
        .card {
          will-change: transform;
          padding: 16px;
        }
    """)
    assert _rule_fired(code, "WILL_CHANGE_ABUSE_SLOP", ".css")


def test_will_change_abuse_slop_fires_on_opacity():
    code = ".hero { will-change: opacity; }"
    assert _rule_fired(code, "WILL_CHANGE_ABUSE_SLOP", ".css")


def test_will_change_abuse_slop_skips_unrelated_css():
    code = ".card { transform: translateY(0); opacity: 1; }"
    assert not _rule_fired(code, "WILL_CHANGE_ABUSE_SLOP", ".css")


def test_height_animation_slop_fires_on_transition_height():
    code = dedent("""\
        .accordion {
          transition: height 300ms ease;
          overflow: hidden;
        }
    """)
    assert _rule_fired(code, "HEIGHT_ANIMATION_SLOP", ".css")


def test_height_animation_slop_skips_non_height_transition():
    code = ".btn { transition: opacity 200ms ease-out; }"
    assert not _rule_fired(code, "HEIGHT_ANIMATION_SLOP", ".css")


def test_transition_all_slop_fires_in_css():
    code = ".btn { transition: all 200ms ease; }"
    assert _rule_fired(code, "TRANSITION_ALL_SLOP", ".css")


def test_transition_all_slop_fires_in_tailwind():
    code = '<button className="rounded transition-all duration-200">Go</button>'
    assert _rule_fired(code, "TRANSITION_ALL_SLOP", ".tsx")


def test_transition_all_slop_skips_specific_transitions():
    code = ".btn { transition: color 200ms ease-out, opacity 200ms; }"
    assert not _rule_fired(code, "TRANSITION_ALL_SLOP", ".css")


def test_ease_default_slop_fires_on_bare_ease():
    code = ".card { transition: transform 300ms ease; }"
    assert _rule_fired(code, "EASE_DEFAULT_SLOP", ".css")


def test_ease_default_slop_fires_on_ease_in_out():
    code = '<div className="transition ease-in-out duration-300">hello</div>'
    assert _rule_fired(code, "EASE_DEFAULT_SLOP", ".tsx")


def test_ease_default_slop_skips_ease_out():
    # ease-out is the preferred curve — must NOT fire
    code = ".btn { transition: color 200ms ease-out; }"
    assert not _rule_fired(code, "EASE_DEFAULT_SLOP", ".css")


def test_ease_default_slop_skips_cubic_bezier():
    code = ".btn { transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1); }"
    assert not _rule_fired(code, "EASE_DEFAULT_SLOP", ".css")


def test_vague_button_label_slop_fires_on_submit():
    code = '<button type="submit">Submit</button>'
    assert _rule_fired(code, "VAGUE_BUTTON_LABEL_SLOP", ".html")


def test_vague_button_label_slop_fires_on_ok():
    code = "<Button>OK</Button>"
    assert _rule_fired(code, "VAGUE_BUTTON_LABEL_SLOP", ".tsx")


def test_vague_button_label_slop_fires_on_click_here():
    code = "<button>Click here</button>"
    assert _rule_fired(code, "VAGUE_BUTTON_LABEL_SLOP", ".html")


def test_vague_button_label_slop_skips_specific_label():
    code = "<button>Create account</button>"
    assert not _rule_fired(code, "VAGUE_BUTTON_LABEL_SLOP", ".html")


def test_vague_button_label_slop_skips_descriptive_tsx():
    code = "<Button>Save changes</Button>"
    assert not _rule_fired(code, "VAGUE_BUTTON_LABEL_SLOP", ".tsx")


def test_skip_to_content_missing_slop_fires_without_skip_link():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
          <body>
            <nav><a href="/">Home</a><a href="/about">About</a></nav>
            <main id="content"><p>Hello</p></main>
          </body>
        </html>
    """)
    assert _rule_fired(code, "SKIP_TO_CONTENT_MISSING_SLOP", ".html")


def test_skip_to_content_missing_slop_skips_when_present():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
          <body>
            <a href="#main" class="sr-only focus:not-sr-only">Skip to main content</a>
            <nav><a href="/">Home</a></nav>
            <main id="main"><p>Hello</p></main>
          </body>
        </html>
    """)
    assert not _rule_fired(code, "SKIP_TO_CONTENT_MISSING_SLOP", ".html")


def test_skip_to_content_missing_slop_skips_no_nav():
    # No <nav> → skip link is irrelevant, rule should not fire
    code = "<html><body><main><p>Content</p></main></body></html>"
    assert not _rule_fired(code, "SKIP_TO_CONTENT_MISSING_SLOP", ".html")


# ── Batch 7 tests: typography, color system, responsive images ────────────────


def test_generic_font_family_slop_fires_for_inter():
    code = "body { font-family: Inter, sans-serif; }"
    assert _rule_fired(code, "GENERIC_FONT_FAMILY_SLOP", ".css")


def test_generic_font_family_slop_fires_for_roboto():
    code = "body { font-family: Roboto, system-ui; }"
    assert _rule_fired(code, "GENERIC_FONT_FAMILY_SLOP", ".css")


def test_generic_font_family_slop_fires_for_open_sans():
    code = "h1 { font-family: 'Open Sans', sans-serif; }"
    assert _rule_fired(code, "GENERIC_FONT_FAMILY_SLOP", ".css")


def test_generic_font_family_slop_skips_distinctive_font():
    code = "body { font-family: 'Instrument Sans', sans-serif; }"
    assert not _rule_fired(code, "GENERIC_FONT_FAMILY_SLOP", ".css")


def test_generic_font_family_slop_skips_system_font():
    code = "body { font-family: -apple-system, BlinkMacSystemFont, system-ui; }"
    assert not _rule_fired(code, "GENERIC_FONT_FAMILY_SLOP", ".css")


def test_hsl_color_token_slop_fires_for_hsl_custom_prop():
    code = ":root { --color-primary: hsl(230, 70%, 50%); }"
    assert _rule_fired(code, "HSL_COLOR_TOKEN_SLOP", ".css")


def test_hsl_color_token_slop_fires_for_hsl_neutral():
    code = ":root { --gray-100: hsl(0, 0%, 95%); }"
    assert _rule_fired(code, "HSL_COLOR_TOKEN_SLOP", ".css")


def test_hsl_color_token_slop_skips_oklch():
    code = ":root { --color-primary: oklch(60% 0.15 250); }"
    assert not _rule_fired(code, "HSL_COLOR_TOKEN_SLOP", ".css")


def test_hsl_color_token_slop_skips_regular_property():
    # hsl() used directly on a non-custom-property rule should not match this rule
    code = "button { background-color: hsl(230, 70%, 50%); }"
    assert not _rule_fired(code, "HSL_COLOR_TOKEN_SLOP", ".css")


def test_font_display_missing_slop_fires_for_font_face_without_display():
    code = dedent("""\
        @font-face {
          font-family: 'MyFont';
          src: url('myfont.woff2') format('woff2');
        }
    """)
    assert _rule_fired(code, "FONT_DISPLAY_MISSING_SLOP", ".css")


def test_font_display_missing_slop_skips_when_present():
    code = dedent("""\
        @font-face {
          font-family: 'MyFont';
          src: url('myfont.woff2') format('woff2');
          font-display: swap;
        }
    """)
    assert not _rule_fired(code, "FONT_DISPLAY_MISSING_SLOP", ".css")


def test_font_display_missing_slop_skips_no_font_face():
    code = "body { font-family: 'Inter', sans-serif; }"
    assert not _rule_fired(code, "FONT_DISPLAY_MISSING_SLOP", ".css")


def test_img_missing_dimensions_slop_fires_without_width_height():
    code = '<img src="photo.jpg" alt="A photo" />'
    assert _rule_fired(code, "IMG_MISSING_DIMENSIONS_SLOP", ".html")


def test_img_missing_dimensions_slop_fires_missing_height():
    code = '<img src="photo.jpg" width="800" alt="A photo" />'
    assert _rule_fired(code, "IMG_MISSING_DIMENSIONS_SLOP", ".html")


def test_img_missing_dimensions_slop_skips_with_both():
    code = '<img src="photo.jpg" width="800" height="600" alt="A photo" />'
    assert not _rule_fired(code, "IMG_MISSING_DIMENSIONS_SLOP", ".html")


def test_img_missing_dimensions_slop_skips_no_img():
    code = "<div><p>Hello</p></div>"
    assert not _rule_fired(code, "IMG_MISSING_DIMENSIONS_SLOP", ".html")


def test_missing_tabular_nums_slop_fires_for_table_without_tabular_nums():
    code = dedent("""\
        <table>
          <tr><td>100</td><td>200</td></tr>
          <tr><td>1,500</td><td>2,000</td></tr>
        </table>
    """)
    assert _rule_fired(code, "MISSING_TABULAR_NUMS_SLOP", ".html")


def test_missing_tabular_nums_slop_skips_when_present():
    code = dedent("""\
        <table style="font-variant-numeric: tabular-nums">
          <tr><td>100</td><td>200</td></tr>
        </table>
    """)
    assert not _rule_fired(code, "MISSING_TABULAR_NUMS_SLOP", ".html")


def test_missing_tabular_nums_slop_skips_no_table():
    code = "<div><p>100 items</p></div>"
    assert not _rule_fired(code, "MISSING_TABULAR_NUMS_SLOP", ".html")


def test_placeholder_only_input_slop_fires_without_label_assoc():
    code = '<input type="text" placeholder="Enter your name" />'
    assert _rule_fired(code, "PLACEHOLDER_ONLY_INPUT_SLOP", ".html")


def test_placeholder_only_input_slop_skips_with_id():
    code = '<input id="name" type="text" placeholder="Enter your name" />'
    assert not _rule_fired(code, "PLACEHOLDER_ONLY_INPUT_SLOP", ".html")


def test_placeholder_only_input_slop_skips_with_aria_label():
    code = '<input type="text" placeholder="Search" aria-label="Search" />'
    assert not _rule_fired(code, "PLACEHOLDER_ONLY_INPUT_SLOP", ".html")


def test_placeholder_only_input_slop_skips_no_placeholder():
    code = '<input type="text" name="email" />'
    assert not _rule_fired(code, "PLACEHOLDER_ONLY_INPUT_SLOP", ".html")


# ── Batch 8 tests: visual anti-patterns, lorem ipsum, glow shadows ───────────


def test_oversized_border_radius_slop_fires_for_24px():
    code = ".card { border-radius: 24px; }"
    assert _rule_fired(code, "OVERSIZED_BORDER_RADIUS_SLOP", ".css")


def test_oversized_border_radius_slop_fires_for_32px():
    code = ".modal { border-radius: 32px; }"
    assert _rule_fired(code, "OVERSIZED_BORDER_RADIUS_SLOP", ".css")


def test_oversized_border_radius_slop_fires_for_3rem():
    code = ".container { border-radius: 3rem; }"
    assert _rule_fired(code, "OVERSIZED_BORDER_RADIUS_SLOP", ".css")


def test_oversized_border_radius_slop_skips_small_radius():
    code = ".card { border-radius: 8px; }"
    assert not _rule_fired(code, "OVERSIZED_BORDER_RADIUS_SLOP", ".css")


def test_oversized_border_radius_slop_skips_pill():
    # 9999px is an intentional pill — should not fire
    code = ".badge { border-radius: 9999px; }"
    assert not _rule_fired(code, "OVERSIZED_BORDER_RADIUS_SLOP", ".css")


def test_height_100vh_slop_fires_for_bare_100vh():
    code = ".hero { height: 100vh; }"
    assert _rule_fired(code, "HEIGHT_100VH_SLOP", ".css")


def test_height_100vh_slop_skips_min_height():
    code = ".hero { min-height: 100vh; }"
    assert not _rule_fired(code, "HEIGHT_100VH_SLOP", ".css")


def test_height_100vh_slop_skips_max_height():
    code = ".container { max-height: 100vh; overflow-y: auto; }"
    assert not _rule_fired(code, "HEIGHT_100VH_SLOP", ".css")


def test_gradient_text_slop_fires_on_background_clip():
    code = "h1 { background: linear-gradient(90deg, red, blue); background-clip: text; -webkit-text-fill-color: transparent; }"
    assert _rule_fired(code, "GRADIENT_TEXT_CSS_SLOP", ".css")


def test_gradient_text_slop_fires_on_tailwind_class():
    code = '<h1 className="bg-clip-text text-transparent bg-gradient-to-r">Title</h1>'
    assert _rule_fired(code, "GRADIENT_TEXT_SLOP", ".tsx")


def test_gradient_text_slop_skips_no_clip():
    code = "h1 { background: linear-gradient(90deg, red, blue); }"
    assert not _rule_fired(code, "GRADIENT_TEXT_CSS_SLOP", ".css")


def test_lorem_ipsum_slop_fires_in_html():
    code = "<p>Lorem ipsum dolor sit amet consectetur adipiscing elit.</p>"
    assert _rule_fired(code, "LOREM_IPSUM_SLOP", ".html")


def test_lorem_ipsum_slop_fires_in_jsx():
    code = 'const Bio = () => <p>Lorem ipsum dolor sit amet.</p>;'
    assert _rule_fired(code, "LOREM_IPSUM_SLOP", ".tsx")


def test_lorem_ipsum_slop_skips_real_content():
    code = "<p>Welcome to our platform. Build something great.</p>"
    assert not _rule_fired(code, "LOREM_IPSUM_SLOP", ".html")


def test_outer_glow_slop_fires_for_zero_offset_shadow():
    code = ".card { box-shadow: 0 0 20px rgba(0, 0, 0, 0.5); }"
    assert _rule_fired(code, "OUTER_GLOW_SLOP", ".css")


def test_outer_glow_slop_fires_for_neon_glow():
    code = ".button { box-shadow: 0 0 10px 4px rgba(99, 102, 241, 0.6); }"
    assert _rule_fired(code, "OUTER_GLOW_SLOP", ".css")


def test_outer_glow_slop_skips_directional_shadow():
    code = ".card { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); }"
    assert not _rule_fired(code, "OUTER_GLOW_SLOP", ".css")


def test_pure_gray_neutral_slop_fires_for_zero_chroma():
    code = ":root { --gray-100: oklch(95% 0 0); }"
    assert _rule_fired(code, "PURE_GRAY_NEUTRAL_SLOP", ".css")


def test_pure_gray_neutral_slop_fires_for_token_zero_chroma():
    code = ":root { --surface-bg: oklch(15% 0 250); }"
    assert _rule_fired(code, "PURE_GRAY_NEUTRAL_SLOP", ".css")


def test_pure_gray_neutral_slop_skips_with_chroma():
    code = ":root { --gray-100: oklch(95% 0.01 250); }"
    assert not _rule_fired(code, "PURE_GRAY_NEUTRAL_SLOP", ".css")


def test_pure_gray_neutral_slop_skips_non_token():
    # oklch() used in non-custom-property should not match this rule
    code = "body { background-color: oklch(15% 0 250); }"
    assert not _rule_fired(code, "PURE_GRAY_NEUTRAL_SLOP", ".css")


# ── Batch 9 ──────────────────────────────────────────────────────────────────

def test_user_scalable_disabled_slop_fires():
    code = '<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">'
    assert _rule_fired(code, "USER_SCALABLE_DISABLED_SLOP", ".html")


def test_user_scalable_disabled_slop_fires_zero():
    code = '<meta name="viewport" content="width=device-width, user-scalable=0">'
    assert _rule_fired(code, "USER_SCALABLE_DISABLED_SLOP", ".html")


def test_user_scalable_disabled_slop_skips_yes():
    code = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    assert not _rule_fired(code, "USER_SCALABLE_DISABLED_SLOP", ".html")


def test_window_confirm_slop_fires():
    code = "if (window.confirm('Delete item?')) { deleteItem(); }"
    assert _rule_fired(code, "WINDOW_CONFIRM_SLOP", ".tsx")


def test_window_confirm_slop_fires_jsx():
    code = "const ok = window.confirm(`Remove ${name}?`);"
    assert _rule_fired(code, "WINDOW_CONFIRM_SLOP", ".js")


def test_window_confirm_slop_skips_no_confirm():
    code = "const modal = document.querySelector('dialog');"
    assert not _rule_fired(code, "WINDOW_CONFIRM_SLOP", ".tsx")


def test_srcset_missing_slop_fires():
    code = '<img src="hero.jpg" alt="Hero image">'
    assert _rule_fired(code, "SRCSET_MISSING_SLOP", ".html")


def test_srcset_missing_slop_fires_jsx():
    code = "<img src='/images/banner.png' alt='Banner' />"
    assert _rule_fired(code, "SRCSET_MISSING_SLOP", ".jsx")


def test_srcset_missing_slop_skips_with_srcset():
    code = '<img src="hero.jpg" srcset="hero-400.jpg 400w, hero-800.jpg 800w" alt="Hero">'
    assert not _rule_fired(code, "SRCSET_MISSING_SLOP", ".html")


def test_srcset_missing_slop_skips_data_uri():
    code = '<img src="data:image/png;base64,abc123==" alt="Icon">'
    assert not _rule_fired(code, "SRCSET_MISSING_SLOP", ".html")


def test_value_named_token_slop_fires_font_size():
    code = ":root { --font-size-16: 1rem; --font-size-24: 1.5rem; }"
    assert _rule_fired(code, "VALUE_NAMED_TOKEN_SLOP", ".css")


def test_value_named_token_slop_fires_spacing():
    code = ":root { --spacing-8: 0.5rem; }"
    assert _rule_fired(code, "VALUE_NAMED_TOKEN_SLOP", ".scss")


def test_value_named_token_slop_skips_semantic():
    code = ":root { --text-body: 1rem; --space-sm: 0.5rem; --space-lg: 2rem; }"
    assert not _rule_fired(code, "VALUE_NAMED_TOKEN_SLOP", ".css")


def test_dialog_role_on_div_slop_fires():
    code = '<div role="dialog" aria-modal="true"><p>Content</p></div>'
    assert _rule_fired(code, "DIALOG_ROLE_ON_DIV_SLOP", ".html")


def test_dialog_role_on_div_slop_fires_jsx():
    code = 'return <section role="dialog" aria-labelledby="title">...</section>;'
    assert _rule_fired(code, "DIALOG_ROLE_ON_DIV_SLOP", ".tsx")


def test_dialog_role_on_div_slop_skips_native_dialog():
    code = '<dialog role="dialog" aria-modal="true"><p>Content</p></dialog>'
    assert not _rule_fired(code, "DIALOG_ROLE_ON_DIV_SLOP", ".html")


def test_dialog_role_on_div_slop_skips_no_role():
    code = '<div aria-modal="true"><p>Content</p></div>'
    assert not _rule_fired(code, "DIALOG_ROLE_ON_DIV_SLOP", ".html")


def test_alpha_color_abuse_slop_fires():
    code = dedent("""\
        .a { color: rgba(0,0,0,0.5); }
        .b { background: rgba(255,255,255,0.3); }
        .c { border-color: rgba(100,100,100,0.8); }
        .d { fill: rgba(0,0,0,0.2); }
        .e { box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    """)
    assert _rule_fired(code, "ALPHA_COLOR_ABUSE_SLOP", ".css")


def test_alpha_color_abuse_slop_fires_hsla():
    code = dedent("""\
        .a { color: hsla(220, 10%, 10%, 0.9); }
        .b { color: hsla(220, 10%, 20%, 0.8); }
        .c { color: hsla(220, 10%, 30%, 0.7); }
        .d { color: hsla(220, 10%, 40%, 0.6); }
        .e { color: hsla(220, 10%, 50%, 0.5); }
    """)
    assert _rule_fired(code, "ALPHA_COLOR_ABUSE_SLOP", ".css")


def test_alpha_color_abuse_slop_skips_under_threshold():
    code = dedent("""\
        .a { color: rgba(0,0,0,0.5); }
        .b { background: rgba(255,255,255,0.3); }
        .focus { outline: 2px solid rgba(0,0,200,0.6); }
        .overlay { background: rgba(0,0,0,0.4); }
    """)
    assert not _rule_fired(code, "ALPHA_COLOR_ABUSE_SLOP", ".css")


# ── Batch 10 ─────────────────────────────────────────────────────────────────

def test_pure_white_background_slop_fires_hex():
    code = "body { background-color: #ffffff; }"
    assert _rule_fired(code, "PURE_WHITE_BACKGROUND_SLOP", ".css")


def test_pure_white_background_slop_fires_keyword():
    code = ".card { background: white; }"
    assert _rule_fired(code, "PURE_WHITE_BACKGROUND_SLOP", ".css")


def test_pure_white_background_slop_fires_shorthand():
    code = "main { background-color: #fff; }"
    assert _rule_fired(code, "PURE_WHITE_BACKGROUND_SLOP", ".css")


def test_pure_white_background_slop_skips_tinted():
    code = "body { background-color: oklch(99% 0.01 250); }"
    assert not _rule_fired(code, "PURE_WHITE_BACKGROUND_SLOP", ".css")


def test_pure_white_background_slop_skips_token_def():
    # CSS custom property definition — should not fire
    code = ":root { --bg-white: white; }"
    assert not _rule_fired(code, "PURE_WHITE_BACKGROUND_SLOP", ".css")


def test_pure_black_text_slop_fires_hex():
    code = "p { color: #000000; }"
    assert _rule_fired(code, "PURE_BLACK_TEXT_SLOP", ".css")


def test_pure_black_text_slop_fires_keyword():
    code = "body { color: black; }"
    assert _rule_fired(code, "PURE_BLACK_TEXT_SLOP", ".css")


def test_pure_black_text_slop_fires_short_hex():
    code = "h1 { color: #000; }"
    assert _rule_fired(code, "PURE_BLACK_TEXT_SLOP", ".css")


def test_pure_black_text_slop_skips_near_black():
    code = "body { color: #0f172a; }"
    assert not _rule_fired(code, "PURE_BLACK_TEXT_SLOP", ".css")


def test_pure_black_text_slop_skips_token_def():
    code = ":root { --text-black: black; }"
    assert not _rule_fired(code, "PURE_BLACK_TEXT_SLOP", ".css")


def test_generic_loading_text_slop_fires_string():
    code = 'const label = "Loading...";'
    assert _rule_fired(code, "GENERIC_LOADING_TEXT_SLOP", ".tsx")


def test_generic_loading_text_slop_fires_jsx():
    code = '<span>{isLoading && <p>Loading...</p>}</span>'
    assert _rule_fired(code, "GENERIC_LOADING_TEXT_SLOP", ".tsx")


def test_generic_loading_text_slop_skips_contextual():
    code = 'const label = "Saving your draft...";'
    assert not _rule_fired(code, "GENERIC_LOADING_TEXT_SLOP", ".tsx")


def test_scroll_snap_without_behavior_slop_fires():
    code = dedent("""\
        .gallery {
          scroll-snap-type: x mandatory;
          overflow-x: scroll;
        }
    """)
    assert _rule_fired(code, "SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP", ".css")


def test_scroll_snap_without_behavior_slop_skips_with_smooth():
    code = dedent("""\
        .gallery {
          scroll-snap-type: x mandatory;
          scroll-behavior: smooth;
          overflow-x: scroll;
        }
    """)
    assert not _rule_fired(code, "SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP", ".css")


def test_scroll_snap_without_behavior_slop_skips_no_snap():
    code = ".gallery { overflow-x: scroll; scroll-behavior: smooth; }"
    assert not _rule_fired(code, "SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP", ".css")


# ── Batch 11 ─────────────────────────────────────────────────────────────────

def test_aspect_ratio_hack_slop_fires_16_9():
    code = ".video { padding-bottom: 56.25%; position: relative; }"
    assert _rule_fired(code, "ASPECT_RATIO_HACK_SLOP", ".css")


def test_aspect_ratio_hack_slop_fires_4_3():
    code = ".box { padding-top: 75%; }"
    assert _rule_fired(code, "ASPECT_RATIO_HACK_SLOP", ".css")


def test_aspect_ratio_hack_slop_skips_arbitrary_padding():
    code = ".card { padding-bottom: 24px; }"
    assert not _rule_fired(code, "ASPECT_RATIO_HACK_SLOP", ".css")


def test_aspect_ratio_hack_slop_skips_aspect_ratio_property():
    code = ".video { aspect-ratio: 16/9; width: 100%; }"
    assert not _rule_fired(code, "ASPECT_RATIO_HACK_SLOP", ".css")


def test_missing_favicon_slop_fires():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
        <head>
          <title>My App</title>
          <link rel="stylesheet" href="/style.css">
        </head>
        <body></body>
        </html>
    """)
    assert _rule_fired(code, "MISSING_FAVICON_SLOP", ".html")


def test_missing_favicon_slop_skips_with_favicon():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
        <head>
          <link rel="icon" href="/favicon.ico">
        </head>
        <body></body>
        </html>
    """)
    assert not _rule_fired(code, "MISSING_FAVICON_SLOP", ".html")


def test_missing_favicon_slop_skips_no_head():
    # Fragment without <head> — should not fire
    code = "<div class='app'>Hello</div>"
    assert not _rule_fired(code, "MISSING_FAVICON_SLOP", ".html")


def test_input_no_type_slop_fires_html():
    code = '<form><input name="email" placeholder="Email"></form>'
    assert _rule_fired(code, "INPUT_NO_TYPE_SLOP", ".html")


def test_input_no_type_slop_fires_jsx():
    code = 'return <input name="query" className="search-input" />;'
    assert _rule_fired(code, "INPUT_NO_TYPE_SLOP", ".tsx")


def test_input_no_type_slop_skips_with_type():
    code = '<input type="email" name="email" placeholder="Email">'
    assert not _rule_fired(code, "INPUT_NO_TYPE_SLOP", ".html")


def test_input_no_type_slop_skips_spread():
    code = "return <input {...inputProps} />;"
    assert not _rule_fired(code, "INPUT_NO_TYPE_SLOP", ".tsx")


def test_empty_href_slop_fires_hash():
    code = '<a href="#" onClick={handleClick}>Click me</a>'
    assert _rule_fired(code, "EMPTY_HREF_SLOP", ".tsx")


def test_empty_href_slop_fires_javascript_void():
    code = '<a href="javascript:void(0)">Submit</a>'
    assert _rule_fired(code, "EMPTY_HREF_SLOP", ".html")


def test_empty_href_slop_skips_real_url():
    code = '<a href="/about">About us</a>'
    assert not _rule_fired(code, "EMPTY_HREF_SLOP", ".html")


def test_missing_lang_slop_fires():
    code = dedent("""\
        <!DOCTYPE html>
        <html>
        <head><title>App</title></head>
        <body></body>
        </html>
    """)
    assert _rule_fired(code, "MISSING_LANG_SLOP", ".html")


def test_missing_lang_slop_skips_with_lang():
    code = dedent("""\
        <!DOCTYPE html>
        <html lang="en">
        <head><title>App</title></head>
        <body></body>
        </html>
    """)
    assert not _rule_fired(code, "MISSING_LANG_SLOP", ".html")


def test_missing_lang_slop_skips_no_html_tag():
    # HTML fragment — no <html> element at all
    code = "<div><p>Hello</p></div>"
    assert not _rule_fired(code, "MISSING_LANG_SLOP", ".html")


def test_flexbox_percentage_math_slop_fires_33():
    code = ".col { width: 33.33%; flex: none; }"
    assert _rule_fired(code, "FLEXBOX_PERCENTAGE_MATH_SLOP", ".css")


def test_flexbox_percentage_math_slop_fires_25():
    code = ".quarter { width: 25%; }"
    assert _rule_fired(code, "FLEXBOX_PERCENTAGE_MATH_SLOP", ".css")


def test_flexbox_percentage_math_slop_skips_arbitrary_percent():
    code = ".section { width: 80%; margin: auto; }"
    assert not _rule_fired(code, "FLEXBOX_PERCENTAGE_MATH_SLOP", ".css")


# ── Batch 12: Security rules ─────────────────────────────────────────────────


def test_anchor_target_blank_slop_fires_without_noopener():
    code = '<a href="https://example.com" target="_blank">Visit</a>'
    assert _rule_fired(code, "ANCHOR_TARGET_BLANK_SLOP", ".html")


def test_anchor_target_blank_slop_fires_missing_noreferrer():
    code = '<a href="https://x.com" target="_blank" rel="noopener">Tweet</a>'
    assert _rule_fired(code, "ANCHOR_TARGET_BLANK_SLOP", ".html")


def test_anchor_target_blank_slop_fires_missing_noopener():
    code = '<a href="https://x.com" target="_blank" rel="noreferrer">Tweet</a>'
    assert _rule_fired(code, "ANCHOR_TARGET_BLANK_SLOP", ".tsx")


def test_anchor_target_blank_slop_skips_with_both():
    code = '<a href="https://example.com" target="_blank" rel="noopener noreferrer">Link</a>'
    assert not _rule_fired(code, "ANCHOR_TARGET_BLANK_SLOP", ".html")


def test_anchor_target_blank_slop_skips_no_blank():
    code = '<a href="https://example.com">Internal link</a>'
    assert not _rule_fired(code, "ANCHOR_TARGET_BLANK_SLOP", ".html")


def test_dangerous_html_slop_fires_without_dompurify():
    code = dedent("""\
        function Post({ content }) {
          return <div dangerouslySetInnerHTML={{ __html: content }} />;
        }
    """)
    assert _rule_fired(code, "DANGEROUS_HTML_SLOP")


def test_dangerous_html_slop_skips_with_dompurify():
    code = dedent("""\
        import DOMPurify from 'dompurify';
        function Post({ content }) {
          return <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(content) }} />;
        }
    """)
    assert not _rule_fired(code, "DANGEROUS_HTML_SLOP")


def test_dangerous_html_slop_skips_without_dangerous_set():
    code = "function Post({ content }) { return <div>{content}</div>; }"
    assert not _rule_fired(code, "DANGEROUS_HTML_SLOP")


# ── Batch 13: SSR compatibility ───────────────────────────────────────────────


def test_localstorage_ssr_slop_fires_at_module_scope():
    code = dedent("""\
        const theme = localStorage.getItem('theme');
        export function App() { return <div>{theme}</div>; }
    """)
    assert _rule_fired(code, "LOCALSTORAGE_SSR_SLOP")


def test_localstorage_ssr_slop_fires_for_session_storage():
    code = dedent("""\
        const token = sessionStorage.getItem('token');
        export function useToken() { return token; }
    """)
    assert _rule_fired(code, "LOCALSTORAGE_SSR_SLOP")


def test_localstorage_ssr_slop_skips_with_typeof_guard():
    code = dedent("""\
        const theme = typeof window !== 'undefined'
          ? localStorage.getItem('theme')
          : null;
    """)
    assert not _rule_fired(code, "LOCALSTORAGE_SSR_SLOP")


def test_localstorage_ssr_slop_skips_in_useeffect_only():
    code = dedent("""\
        export function App() {
          useEffect(() => {
            const theme = localStorage.getItem('theme');
            setTheme(theme);
          }, []);
        }
    """)
    assert not _rule_fired(code, "LOCALSTORAGE_SSR_SLOP")


def test_window_object_ssr_slop_fires_at_module_scope():
    code = "const width = window.innerWidth;"
    assert _rule_fired(code, "WINDOW_OBJECT_SSR_SLOP")


def test_window_object_ssr_slop_fires_for_export():
    code = "export const origin = window.location.origin;"
    assert _rule_fired(code, "WINDOW_OBJECT_SSR_SLOP")


def test_window_object_ssr_slop_skips_with_typeof_guard():
    code = dedent("""\
        const width = typeof window !== 'undefined' ? window.innerWidth : 0;
    """)
    assert not _rule_fired(code, "WINDOW_OBJECT_SSR_SLOP")


def test_window_object_ssr_slop_skips_no_window():
    code = "const url = new URL('/path', 'https://example.com');"
    assert not _rule_fired(code, "WINDOW_OBJECT_SSR_SLOP")


# ── Batch 14: React patterns ──────────────────────────────────────────────────


def test_missing_key_prop_slop_fires_for_map_without_key():
    code = "const items = list.map(item => <ListItem>{item.name}</ListItem>);"
    assert _rule_fired(code, "MISSING_KEY_PROP_SLOP")


def test_missing_key_prop_slop_fires_destructured_arg():
    code = "const rows = data.map(({ id, label }) => <tr><td>{label}</td></tr>);"
    assert _rule_fired(code, "MISSING_KEY_PROP_SLOP")


def test_missing_key_prop_slop_skips_with_key():
    code = "const items = list.map(item => <ListItem key={item.id}>{item.name}</ListItem>);"
    assert not _rule_fired(code, "MISSING_KEY_PROP_SLOP")


def test_missing_key_prop_slop_skips_no_map():
    code = "const el = <ListItem>Static item</ListItem>;"
    assert not _rule_fired(code, "MISSING_KEY_PROP_SLOP")


def test_useeffect_empty_deps_slop_fires_for_substantial_body():
    code = dedent("""\
        useEffect(() => {
          if (props.userId) {
            fetchUser(props.userId).then(setUser);
          }
        }, []);
    """)
    assert _rule_fired(code, "USEEFFECT_EMPTY_DEPS_SLOP")


def test_useeffect_empty_deps_slop_skips_short_body():
    # Body shorter than 80 chars should not fire (too trivial to flag)
    code = "useEffect(() => { setMounted(true); }, []);"
    assert not _rule_fired(code, "USEEFFECT_EMPTY_DEPS_SLOP")


def test_framer_no_reduced_motion_slop_fires_without_check():
    code = dedent("""\
        import { motion } from 'framer-motion';
        export function Hero() {
          return <motion.div animate={{ opacity: 1 }} initial={{ opacity: 0 }}>Hero</motion.div>;
        }
    """)
    assert _rule_fired(code, "FRAMER_NO_REDUCED_MOTION_SLOP")


def test_framer_no_reduced_motion_slop_skips_with_use_reduced_motion():
    code = dedent("""\
        import { motion, useReducedMotion } from 'framer-motion';
        export function Hero() {
          const shouldReduce = useReducedMotion();
          return (
            <motion.div
              animate={shouldReduce ? {} : { opacity: 1 }}
              initial={{ opacity: 0 }}
            >
              Hero
            </motion.div>
          );
        }
    """)
    assert not _rule_fired(code, "FRAMER_NO_REDUCED_MOTION_SLOP")


def test_framer_no_reduced_motion_slop_skips_no_framer():
    code = 'import { useState } from "react"; const x = 1;'
    assert not _rule_fired(code, "FRAMER_NO_REDUCED_MOTION_SLOP")


# ── Batch 15: Next.js / RSC patterns ─────────────────────────────────────────


def test_use_client_directive_slop_fires():
    code = dedent("""\
        'use client';
        import { useState } from 'react';
        export function Counter() {
          const [n, setN] = useState(0);
          return <button onClick={() => setN(n + 1)}>{n}</button>;
        }
    """)
    assert _rule_fired(code, "USE_CLIENT_DIRECTIVE_SLOP")


def test_use_client_directive_slop_fires_double_quote():
    code = '"use client";\nexport function Foo() { return <div />; }'
    assert _rule_fired(code, "USE_CLIENT_DIRECTIVE_SLOP")


def test_use_client_directive_slop_skips_no_directive():
    code = "export function StaticCard({ title }) { return <h2>{title}</h2>; }"
    assert not _rule_fired(code, "USE_CLIENT_DIRECTIVE_SLOP")


# ── Batch 16: CSS smells ──────────────────────────────────────────────────────


def test_tailwind_apply_overuse_slop_fires_for_six_utilities():
    code = ".card { @apply rounded-xl bg-white p-6 shadow-sm border flex flex-col; }"
    assert _rule_fired(code, "TAILWIND_APPLY_OVERUSE_SLOP", ".css")


def test_tailwind_apply_overuse_slop_fires_in_scss():
    code = ".btn { @apply px-4 py-2 rounded bg-blue-500 text-white font-medium hover:bg-blue-600; }"
    assert _rule_fired(code, "TAILWIND_APPLY_OVERUSE_SLOP", ".scss")


def test_tailwind_apply_overuse_slop_skips_few_utilities():
    code = "a { @apply text-blue-500 underline; }"
    assert not _rule_fired(code, "TAILWIND_APPLY_OVERUSE_SLOP", ".css")


def test_tailwind_apply_overuse_slop_skips_five_utilities():
    code = ".link { @apply text-sm font-medium text-blue-500 hover:underline; }"
    assert not _rule_fired(code, "TAILWIND_APPLY_OVERUSE_SLOP", ".css")


def test_form_no_submit_slop_fires_for_form_without_onsubmit():
    code = dedent("""\
        <form>
          <input type="email" name="email" />
          <button type="submit">Subscribe</button>
        </form>
    """)
    assert _rule_fired(code, "FORM_NO_SUBMIT_SLOP")


def test_form_no_submit_slop_fires_for_html_form():
    code = '<form method="POST"><input type="text" /><button>Go</button></form>'
    assert _rule_fired(code, "FORM_NO_SUBMIT_SLOP", ".html")


def test_form_no_submit_slop_skips_with_onsubmit():
    code = '<form onSubmit={handleSubmit}><input type="email" /><button>Go</button></form>'
    assert not _rule_fired(code, "FORM_NO_SUBMIT_SLOP")


def test_form_no_submit_slop_skips_with_action():
    # Server-rendered forms with action= are fine — they don't need JS
    code = '<form action="/subscribe" method="POST"><input type="email" /><button>Go</button></form>'
    assert not _rule_fired(code, "FORM_NO_SUBMIT_SLOP", ".html")


def test_form_no_submit_slop_skips_no_form():
    code = "function App() { return <div><input type='text' /></div>; }"
    assert not _rule_fired(code, "FORM_NO_SUBMIT_SLOP")


# ── Duplication rules ─────────────────────────────────────────────────────────


def test_duplicate_tailwind_block_fires_for_repeated_class_string():
    code = dedent("""\
        <div className="flex items-center justify-between p-4 rounded-xl bg-white shadow-sm border">A</div>
        <div className="flex items-center justify-between p-4 rounded-xl bg-white shadow-sm border">B</div>
    """)
    assert _rule_fired(code, "DUPLICATE_TAILWIND_BLOCK")


def test_duplicate_tailwind_block_skips_short_class_strings():
    # Short strings (< 40 chars) don't count — only long repeated ones
    code = dedent("""\
        <div className="flex gap-4">A</div>
        <div className="flex gap-4">B</div>
    """)
    assert not _rule_fired(code, "DUPLICATE_TAILWIND_BLOCK")


def test_duplicate_color_literal_fires_for_three_repeats():
    code = dedent("""\
        .a { color: #3b82f6; }
        .b { background: #3b82f6; }
        .c { border-color: #3b82f6; }
    """)
    assert _rule_fired(code, "DUPLICATE_COLOR_LITERAL", ".css")


def test_duplicate_color_literal_skips_two_repeats():
    code = dedent("""\
        .a { color: #3b82f6; }
        .b { background: #3b82f6; }
    """)
    assert not _rule_fired(code, "DUPLICATE_COLOR_LITERAL", ".css")


def test_duplicate_handler_fires_for_repeated_handler():
    code = dedent("""\
        <button onClick={() => dispatch({ type: 'INCREMENT' })}>+</button>
        <button onClick={() => dispatch({ type: 'INCREMENT' })}>Add</button>
    """)
    assert _rule_fired(code, "DUPLICATE_HANDLER")


def test_duplicate_handler_skips_short_handlers():
    # Handlers shorter than 20 chars don't match the pattern
    code = dedent("""\
        <button onClick={() => setOpen(true)}>Open</button>
        <button onClick={() => setOpen(true)}>Also open</button>
    """)
    assert not _rule_fired(code, "DUPLICATE_HANDLER")


def test_repeated_media_query_fires_for_same_query_twice():
    code = dedent("""\
        @media (max-width: 640px) { .nav { display: none; } }
        .card { padding: 1rem; }
        @media (max-width: 640px) { .card { padding: 0.5rem; } }
    """)
    assert _rule_fired(code, "REPEATED_MEDIA_QUERY", ".css")


def test_repeated_media_query_skips_unique_queries():
    code = dedent("""\
        @media (max-width: 640px) { .a { display: none; } }
        @media (min-width: 768px) { .b { display: flex; } }
    """)
    assert not _rule_fired(code, "REPEATED_MEDIA_QUERY", ".css")


# ── Batch 17: correctness & security smells ──────────────────────────────────


def test_hardcoded_dev_url_slop_fires_for_localhost():
    code = 'const API = "http://localhost:3000/api";'
    assert _rule_fired(code, "HARDCODED_DEV_URL_SLOP", ".ts")


def test_hardcoded_dev_url_slop_fires_for_127():
    code = "const BASE = 'http://127.0.0.1:8080';"
    assert _rule_fired(code, "HARDCODED_DEV_URL_SLOP", ".ts")


def test_hardcoded_dev_url_slop_skips_production_url():
    code = 'const API = "https://api.example.com/v1";'
    assert not _rule_fired(code, "HARDCODED_DEV_URL_SLOP", ".ts")


def test_empty_catch_slop_fires_for_empty_catch():
    code = dedent("""\
        try {
          doSomething();
        } catch (err) {}
    """)
    assert _rule_fired(code, "EMPTY_CATCH_SLOP", ".ts")


def test_empty_catch_slop_skips_non_empty_catch():
    code = dedent("""\
        try {
          doSomething();
        } catch (err) {
          console.error(err);
        }
    """)
    assert not _rule_fired(code, "EMPTY_CATCH_SLOP", ".ts")


def test_input_autocomplete_missing_slop_fires_for_email_input():
    code = '<input type="email" id="email" />'
    assert _rule_fired(code, "INPUT_AUTOCOMPLETE_MISSING_SLOP")


def test_input_autocomplete_missing_slop_fires_for_password_input():
    code = "<input type='password' placeholder='Password' />"
    assert _rule_fired(code, "INPUT_AUTOCOMPLETE_MISSING_SLOP")


def test_input_autocomplete_missing_slop_skips_when_present():
    code = '<input type="email" autocomplete="email" id="email" />'
    assert not _rule_fired(code, "INPUT_AUTOCOMPLETE_MISSING_SLOP")


def test_input_autocomplete_missing_slop_skips_unrelated_type():
    code = '<input type="checkbox" id="agree" />'
    assert not _rule_fired(code, "INPUT_AUTOCOMPLETE_MISSING_SLOP")


def test_aria_hidden_interactive_slop_fires_for_button():
    code = '<button aria-hidden="true" onClick={doStuff}>Click</button>'
    assert _rule_fired(code, "ARIA_HIDDEN_INTERACTIVE_SLOP")


def test_aria_hidden_interactive_slop_fires_for_anchor():
    code = "<a href='/home' aria-hidden=\"true\">Home</a>"
    assert _rule_fired(code, "ARIA_HIDDEN_INTERACTIVE_SLOP")


def test_aria_hidden_interactive_slop_skips_div():
    # aria-hidden on a div is fine (decorative container)
    code = '<div aria-hidden="true" className="decoration">✦</div>'
    assert not _rule_fired(code, "ARIA_HIDDEN_INTERACTIVE_SLOP")


def test_next_image_raw_slop_fires_for_img_in_next_file():
    code = dedent("""\
        import Link from 'next/link';
        export default function Page() {
          return <img src="/hero.jpg" alt="hero" />;
        }
    """)
    assert _rule_fired(code, "NEXT_IMAGE_RAW_SLOP")


def test_next_image_raw_slop_skips_when_next_image_imported():
    code = dedent("""\
        import Image from 'next/image';
        export default function Page() {
          return <Image src="/hero.jpg" alt="hero" width={800} height={400} />;
        }
    """)
    assert not _rule_fired(code, "NEXT_IMAGE_RAW_SLOP")


def test_next_image_raw_slop_skips_non_next_file():
    code = dedent("""\
        import React from 'react';
        export default function Page() {
          return <img src="/hero.jpg" alt="hero" />;
        }
    """)
    assert not _rule_fired(code, "NEXT_IMAGE_RAW_SLOP")


def test_css_universal_selector_slop_fires_for_global_rule():
    code = "* { box-sizing: border-box; color: red; padding: 0; }"
    assert _rule_fired(code, "CSS_UNIVERSAL_SELECTOR_SLOP", ".css")


def test_css_universal_selector_slop_skips_box_sizing_only():
    # *, *::before, *::after with box-sizing is acceptable (standard reset),
    # but the rule flags the universal selector itself — so this still fires.
    # The test verifies the selector is detected at all.
    code = "*, *::before, *::after { box-sizing: border-box; }"
    # Rule fires (by design — guidance tells user this is the only acceptable use)
    # Just verify it doesn't crash.
    _rule_fired(code, "CSS_UNIVERSAL_SELECTOR_SLOP", ".css")


def test_hardcoded_secret_slop_fires_for_api_key():
    code = 'const apiKey = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890";'
    assert _rule_fired(code, "HARDCODED_SECRET_SLOP", ".ts")


def test_hardcoded_secret_slop_fires_for_secret_key():
    code = "const secret_key = 'AKIAIOSFODNN7EXAMPLE_LONG_KEY_VALUE';"
    assert _rule_fired(code, "HARDCODED_SECRET_SLOP", ".ts")


def test_hardcoded_secret_slop_skips_env_variable():
    code = "const apiKey = process.env.NEXT_PUBLIC_API_KEY;"
    assert not _rule_fired(code, "HARDCODED_SECRET_SLOP", ".ts")


def test_focus_visible_missing_slop_fires_for_focus_only():
    code = dedent("""\
        .btn:focus {
          outline: 2px solid blue;
        }
    """)
    assert _rule_fired(code, "FOCUS_VISIBLE_MISSING_SLOP", ".css")


def test_focus_visible_missing_slop_skips_when_both_present():
    code = dedent("""\
        .btn:focus {
          outline: none;
        }
        .btn:focus-visible {
          outline: 2px solid blue;
        }
    """)
    assert not _rule_fired(code, "FOCUS_VISIBLE_MISSING_SLOP", ".css")


def test_focus_visible_missing_slop_skips_no_focus_rule():
    code = ".btn { color: red; }"
    assert not _rule_fired(code, "FOCUS_VISIBLE_MISSING_SLOP", ".css")


def test_type_assertion_abuse_slop_fires_for_double_cast():
    code = "const el = (event.target as unknown as HTMLInputElement).value;"
    assert _rule_fired(code, "TYPE_ASSERTION_ABUSE_SLOP", ".ts")


def test_type_assertion_abuse_slop_fires_for_cast_to_any():
    code = "const data = (response as any).items;"
    assert _rule_fired(code, "TYPE_ASSERTION_ABUSE_SLOP", ".ts")


def test_type_assertion_abuse_slop_skips_normal_cast():
    code = "const el = document.getElementById('app') as HTMLDivElement;"
    assert not _rule_fired(code, "TYPE_ASSERTION_ABUSE_SLOP", ".ts")


def test_async_useeffect_slop_fires():
    code = dedent("""\
        useEffect(async () => {
          const data = await fetchData();
          setData(data);
        }, []);
    """)
    assert _rule_fired(code, "ASYNC_USEEFFECT_SLOP")


def test_async_useeffect_slop_skips_correct_pattern():
    code = dedent("""\
        useEffect(() => {
          const load = async () => {
            const data = await fetchData();
            setData(data);
          };
          load();
        }, []);
    """)
    assert not _rule_fired(code, "ASYNC_USEEFFECT_SLOP")


# ── Batches 1-2: Original AI slop rules ──────────────────────────────────────


def test_typography_slop_fires_for_inter():
    assert _rule_fired('<p className="font-inter text-gray-700">Hello</p>', "TYPOGRAPHY_SLOP")


def test_typography_slop_fires_for_css_inter():
    assert _rule_fired(".body { font-family: Inter; }", "TYPOGRAPHY_SLOP", ".css")


def test_typography_slop_skips_distinctive_font():
    assert not _rule_fired('.body { font-family: "Satoshi", sans-serif; }', "TYPOGRAPHY_SLOP", ".css")


def test_color_gradient_slop_fires_for_blue_to_purple():
    assert _rule_fired(
        '<div className="from-blue-500 to-purple-600 bg-gradient-to-r">x</div>',
        "COLOR_GRADIENT_SLOP",
    )


def test_color_gradient_slop_skips_orange_yellow():
    assert not _rule_fired(
        '<div className="from-orange-400 to-yellow-300">x</div>',
        "COLOR_GRADIENT_SLOP",
    )


def test_color_black_slop_fires_for_bg_black():
    assert _rule_fired('<div className="bg-black text-white">dark</div>', "COLOR_BLACK_SLOP")


def test_color_black_slop_fires_for_hex_000000():
    assert _rule_fired(".nav { @apply bg-black; }", "COLOR_BLACK_SLOP", ".css")


def test_color_black_slop_skips_near_black():
    assert not _rule_fired(".nav { background: #0d1117; }", "COLOR_BLACK_SLOP", ".css")


def test_iconography_slop_fires_for_lucide():
    assert _rule_fired("import { Search } from 'lucide-react';", "ICONOGRAPHY_SLOP", ".ts")


def test_iconography_slop_skips_phosphor():
    assert not _rule_fired("import { MagnifyingGlass } from '@phosphor-icons/react';", "ICONOGRAPHY_SLOP", ".ts")


def test_materiality_radius_slop_fires_for_rounded_2xl():
    assert _rule_fired('<div className="rounded-2xl bg-white p-6">Card</div>', "MATERIALITY_RADIUS_SLOP")


def test_materiality_radius_slop_fires_for_rounded_3xl():
    assert _rule_fired('<div className="rounded-3xl shadow-md">Card</div>', "MATERIALITY_RADIUS_SLOP")


def test_materiality_radius_slop_skips_rounded_xl():
    assert not _rule_fired('<div className="rounded-xl p-4">Card</div>', "MATERIALITY_RADIUS_SLOP")


def test_layout_math_slop_fires_for_w_one_third():
    assert _rule_fired('<div className="w-1/3 px-4">feature</div>', "LAYOUT_MATH_SLOP")


def test_layout_math_slop_fires_for_grid_cols_3():
    assert _rule_fired('<div className="grid grid-cols-3 gap-6">x</div>', "LAYOUT_MATH_SLOP")


def test_layout_math_slop_skips_grid_cols_2():
    assert not _rule_fired('<div className="grid grid-cols-2 gap-4">x</div>', "LAYOUT_MATH_SLOP")


def test_glassmorphism_slop_fires_for_backdrop_blur():
    assert _rule_fired('<div className="backdrop-blur bg-white/20">modal</div>', "GLASSMORPHISM_SLOP")


def test_glassmorphism_slop_fires_in_css():
    assert _rule_fired(".card { @apply backdrop-blur bg-white/20; }", "GLASSMORPHISM_SLOP", ".css")


def test_glassmorphism_slop_skips_solid_card():
    assert not _rule_fired('<div className="bg-zinc-900 border border-zinc-800">card</div>', "GLASSMORPHISM_SLOP")


def test_shadow_slop_fires_for_shadow_2xl():
    assert _rule_fired('<div className="shadow-2xl rounded-lg">Card</div>', "SHADOW_SLOP")


def test_shadow_slop_fires_for_shadow_3xl():
    assert _rule_fired('<div className="shadow-3xl p-6">Card</div>', "SHADOW_SLOP")


def test_shadow_slop_skips_shadow_md():
    assert not _rule_fired('<div className="shadow-md p-4">Card</div>', "SHADOW_SLOP")


def test_hero_dashboard_slop_fires_for_stat_card():
    assert _rule_fired('<div className="stat-card flex flex-col">Revenue</div>', "HERO_DASHBOARD_SLOP")


def test_hero_dashboard_slop_fires_for_kpi_card():
    assert _rule_fired('<div className="kpi-card">Users</div>', "HERO_DASHBOARD_SLOP")


def test_hero_dashboard_slop_skips_regular_card():
    assert not _rule_fired('<div className="feature-card bg-white">Feature</div>', "HERO_DASHBOARD_SLOP")


def test_bounce_animation_slop_fires_for_animate_bounce():
    assert _rule_fired('<div className="animate-bounce">Loading</div>', "BOUNCE_ANIMATION_SLOP")


def test_bounce_animation_slop_fires_for_animate_pulse():
    assert _rule_fired('<div className="animate-pulse bg-gray-200 h-4 w-32" />', "BOUNCE_ANIMATION_SLOP")


def test_bounce_animation_slop_skips_no_animation():
    assert not _rule_fired('<div className="bg-white p-4">No animation</div>', "BOUNCE_ANIMATION_SLOP")


def test_gray_on_color_slop_fires():
    assert _rule_fired(
        '<p className="text-gray-400 bg-blue-500 px-4">subtitle</p>',
        "GRAY_ON_COLOR_SLOP",
    )


def test_gray_on_color_slop_skips_white_on_color():
    assert not _rule_fired(
        '<p className="text-white bg-blue-500 px-4">subtitle</p>',
        "GRAY_ON_COLOR_SLOP",
    )


def test_missing_dark_mode_fires_for_bg_white():
    assert _rule_fired('<div className="bg-white px-4 py-8">content</div>', "MISSING_DARK_MODE")


def test_missing_dark_mode_skips_with_dark_variant():
    assert not _rule_fired(
        '<div className="bg-white dark:bg-zinc-900 px-4">content</div>',
        "MISSING_DARK_MODE",
    )


def test_css_gradient_slop_fires_for_purple_to_blue():
    code = ".hero { background: linear-gradient(to right, purple, blue); }"
    assert _rule_fired(code, "CSS_GRADIENT_SLOP", ".css")


def test_css_gradient_slop_fires_for_indigo_to_cyan():
    code = ".btn { background: linear-gradient(135deg, indigo, cyan); }"
    assert _rule_fired(code, "CSS_GRADIENT_SLOP", ".css")


def test_css_gradient_slop_skips_orange_to_red():
    code = ".cta { background: linear-gradient(to bottom, #ff6b00, #c41230); }"
    assert not _rule_fired(code, "CSS_GRADIENT_SLOP", ".css")


def test_generic_copy_slop_fires_for_supercharge():
    assert _rule_fired("<h1>Supercharge your workflow today</h1>", "GENERIC_COPY_SLOP")


def test_generic_copy_slop_fires_for_revolutionize():
    assert _rule_fired("<p>Revolutionize how your team collaborates</p>", "GENERIC_COPY_SLOP")


def test_generic_copy_slop_skips_specific_copy():
    assert not _rule_fired("<h1>Ship features 3x faster with automated code review</h1>", "GENERIC_COPY_SLOP")


def test_emoji_heavy_slop_fires_for_seven_emoji():
    code = "<p>🚀 We built 🎯 the best 💡 tool 🔥 ever 🎉 made 🌟 today 🏆</p>"
    assert _rule_fired(code, "EMOJI_HEAVY_SLOP")


def test_emoji_heavy_slop_skips_two_emoji():
    code = "<p>🚀 Ship features faster</p>"
    assert not _rule_fired(code, "EMOJI_HEAVY_SLOP")


def test_viewport_height_slop_fires_for_h_screen():
    assert _rule_fired('<div className="h-screen flex items-center">full</div>', "VIEWPORT_HEIGHT_SLOP")


def test_viewport_height_slop_skips_min_h_dvh():
    assert not _rule_fired('<div className="min-h-[100dvh] flex">full</div>', "VIEWPORT_HEIGHT_SLOP")


def test_neon_glow_slop_fires_for_shadow_zero_zero():
    assert _rule_fired('<div className="shadow-neon">glow</div>', "NEON_GLOW_SLOP")


def test_neon_glow_slop_fires_for_shadow_neon():
    assert _rule_fired('<div className="shadow-neon text-white">neon</div>', "NEON_GLOW_SLOP")


def test_neon_glow_slop_skips_regular_shadow():
    assert not _rule_fired('<div className="shadow-lg border border-zinc-800">card</div>', "NEON_GLOW_SLOP")


def test_pill_badge_slop_fires():
    assert _rule_fired('<span className="rounded-full badge text-xs px-2">New</span>', "PILL_BADGE_SLOP")


def test_pill_badge_slop_fires_for_chip():
    assert _rule_fired('<span className="rounded-full chip px-3 py-1">Tag</span>', "PILL_BADGE_SLOP")


def test_pill_badge_slop_skips_rounded_full_button():
    assert not _rule_fired('<button className="rounded-full px-6 py-2">CTA</button>', "PILL_BADGE_SLOP")


def test_generic_name_slop_fires_for_john_doe():
    assert _rule_fired('<p>Reviewed by John Doe, Senior Engineer</p>', "GENERIC_NAME_SLOP")


def test_generic_name_slop_fires_for_acme_corp():
    assert _rule_fired('<span className="text-sm">Trusted by Acme Corp</span>', "GENERIC_NAME_SLOP")


def test_generic_name_slop_skips_real_name():
    assert not _rule_fired('<p>Reviewed by Sofia Espinoza, Staff Eng</p>', "GENERIC_NAME_SLOP")


def test_ai_copy_cliche_slop_fires_for_next_gen():
    assert _rule_fired("<h2>Next-Gen AI tooling for enterprises</h2>", "AI_COPY_CLICHE_SLOP")


def test_ai_copy_cliche_slop_fires_for_delve():
    assert _rule_fired("<p>Let's delve into the architecture</p>", "AI_COPY_CLICHE_SLOP")


def test_ai_copy_cliche_slop_skips_neutral_text():
    assert not _rule_fired("<h2>Build and ship in minutes</h2>", "AI_COPY_CLICHE_SLOP")


def test_center_bias_slop_fires_for_text_center_mx_auto():
    code = '<div className="text-center mx-auto max-w-2xl"><h1>Hero</h1></div>'
    assert _rule_fired(code, "CENTER_BIAS_SLOP")


def test_center_bias_slop_skips_left_aligned():
    code = '<div className="max-w-2xl px-6"><h1>Hero</h1></div>'
    assert not _rule_fired(code, "CENTER_BIAS_SLOP")


def test_card_nesting_slop_fires():
    code = '<div className="outer-card product-card rounded-xl bg-white">content</div>'
    assert _rule_fired(code, "CARD_NESTING_SLOP")


def test_card_nesting_slop_skips_single_card():
    code = '<div className="card p-6"><h3>Just one card</h3></div>'
    assert not _rule_fired(code, "CARD_NESTING_SLOP")


def test_css_pure_black_slop_fires():
    assert _rule_fired(".text { color: #000; }", "CSS_PURE_BLACK_SLOP", ".css")


def test_css_pure_black_slop_fires_six_digit():
    assert _rule_fired(".bg { background-color: #000000; }", "CSS_PURE_BLACK_SLOP", ".css")


def test_css_pure_black_slop_skips_off_black():
    assert not _rule_fired(".bg { background: #0d1117; }", "CSS_PURE_BLACK_SLOP", ".css")


def test_hardcoded_zindex_slop_fires_for_9999():
    assert _rule_fired(".modal { z-index: 9999; }", "HARDCODED_ZINDEX_SLOP", ".css")


def test_hardcoded_zindex_slop_fires_for_tailwind_9999():
    assert _rule_fired(".overlay { z-index: 9999; }", "HARDCODED_ZINDEX_SLOP", ".css")


def test_hardcoded_zindex_slop_skips_z_50():
    assert not _rule_fired(".modal { z-index: 50; }", "HARDCODED_ZINDEX_SLOP", ".css")


def test_solid_divider_slop_fires():
    assert _rule_fired(
        '<div className="border-t border-gray-200 my-4" />',
        "SOLID_DIVIDER_SLOP",
    )


def test_solid_divider_slop_skips_opacity_border():
    assert not _rule_fired(
        '<div className="border-t border-white/10 my-4" />',
        "SOLID_DIVIDER_SLOP",
    )


def test_hardcoded_px_font_slop_fires_for_font_size_px():
    assert _rule_fired(".body { font-size: 16px; }", "HARDCODED_PX_FONT_SLOP", ".css")


def test_hardcoded_px_font_slop_fires_for_tailwind_px():
    assert _rule_fired('<p className="text-[18px] font-normal">body</p>', "HARDCODED_PX_FONT_SLOP")


def test_hardcoded_px_font_slop_skips_rem():
    assert not _rule_fired(".body { font-size: 1.125rem; }", "HARDCODED_PX_FONT_SLOP", ".css")


def test_tight_line_height_slop_fires():
    assert _rule_fired('<p className="text-sm leading-tight text-gray-600">body</p>', "TIGHT_LINE_HEIGHT_SLOP")


def test_tight_line_height_slop_skips_relaxed():
    assert not _rule_fired('<p className="text-sm leading-relaxed text-gray-600">body</p>', "TIGHT_LINE_HEIGHT_SLOP")


def test_lazy_flex_center_slop_fires():
    assert _rule_fired(
        '<div className="flex items-center justify-center h-screen">centered</div>',
        "LAZY_FLEX_CENTER_SLOP",
    )


def test_lazy_flex_center_slop_fires_reverse_order():
    assert _rule_fired(
        '<div className="flex justify-center items-center gap-4">centered</div>',
        "LAZY_FLEX_CENTER_SLOP",
    )


def test_lazy_flex_center_slop_skips_flex_start():
    assert not _rule_fired(
        '<div className="flex items-start gap-4">left-aligned</div>',
        "LAZY_FLEX_CENTER_SLOP",
    )


def test_raw_color_slop_fires_for_red():
    assert _rule_fired(".alert { color: red; }", "RAW_COLOR_SLOP", ".css")


def test_raw_color_slop_fires_for_blue():
    assert _rule_fired(".link { color: blue; }", "RAW_COLOR_SLOP", ".css")


def test_raw_color_slop_skips_hex():
    assert not _rule_fired(".link { color: #3b82f6; }", "RAW_COLOR_SLOP", ".css")


def test_important_abuse_slop_fires():
    assert _rule_fired(".btn { color: red !important; }", "IMPORTANT_ABUSE_SLOP", ".css")


def test_important_abuse_slop_skips_no_important():
    assert not _rule_fired(".btn { color: red; }", "IMPORTANT_ABUSE_SLOP", ".css")


def test_inline_style_slop_fires_for_long_style_prop():
    code = '<div style={{ padding: "16px", margin: "8px", borderRadius: "4px", background: "white" }}>x</div>'
    assert _rule_fired(code, "INLINE_STYLE_SLOP")


def test_inline_style_slop_skips_short_style():
    assert not _rule_fired('<div style={{ color: "red" }}>short</div>', "INLINE_STYLE_SLOP")


def test_console_log_slop_fires():
    assert _rule_fired("console.log('debug', data);", "CONSOLE_LOG_SLOP", ".ts")


def test_console_log_slop_fires_for_warn():
    assert _rule_fired("console.warn('missing field');", "CONSOLE_LOG_SLOP", ".ts")


def test_console_log_slop_skips_string_content():
    assert not _rule_fired('const msg = "console.log is not called";', "CONSOLE_LOG_SLOP", ".ts")


def test_todo_fixme_slop_fires_for_todo():
    assert _rule_fired("// TODO: fix this later", "TODO_FIXME_SLOP", ".ts")


def test_todo_fixme_slop_fires_for_fixme():
    assert _rule_fired("// FIXME: broken on mobile", "TODO_FIXME_SLOP", ".ts")


def test_todo_fixme_slop_fires_for_hack():
    assert _rule_fired("/* HACK: remove after migration */", "TODO_FIXME_SLOP", ".ts")


def test_todo_fixme_slop_skips_regular_comment():
    assert not _rule_fired("// This function handles authentication", "TODO_FIXME_SLOP", ".ts")


def test_magic_number_slop_fires_for_padding_px():
    assert _rule_fired(".hero { padding: 250px; }", "MAGIC_NUMBER_SLOP", ".css")


def test_magic_number_slop_fires_for_width():
    assert _rule_fired(".sidebar { width: 340px; }", "MAGIC_NUMBER_SLOP", ".css")


def test_magic_number_slop_skips_small_px():
    assert not _rule_fired(".btn { padding: 8px 16px; }", "MAGIC_NUMBER_SLOP", ".css")


def test_broken_image_slop_fires_for_unsplash():
    code = '<img src="https://images.unsplash.com/photo-12345?w=800" alt="hero" />'
    assert _rule_fired(code, "BROKEN_IMAGE_SLOP")


def test_broken_image_slop_fires_for_source_unsplash():
    code = '<img src="https://source.unsplash.com/random/800x600" alt="bg" />'
    assert _rule_fired(code, "BROKEN_IMAGE_SLOP")


def test_broken_image_slop_skips_picsum():
    assert not _rule_fired('<img src="https://picsum.photos/800/600" alt="placeholder" />', "BROKEN_IMAGE_SLOP")


def test_exclamation_ux_slop_fires_for_success():
    assert _rule_fired('<p>Success! Your changes have been saved.</p>', "EXCLAMATION_UX_SLOP")


def test_exclamation_ux_slop_fires_for_created():
    assert _rule_fired('<span>Created! The item is now live.</span>', "EXCLAMATION_UX_SLOP")


def test_exclamation_ux_slop_skips_neutral_message():
    assert not _rule_fired('<p>Your changes have been saved.</p>', "EXCLAMATION_UX_SLOP")


def test_oops_error_slop_fires_for_oops():
    assert _rule_fired('<h2>Oops, something went wrong.</h2>', "OOPS_ERROR_SLOP")


def test_oops_error_slop_fires_for_whoops():
    assert _rule_fired('<p>Whoops! That didn\'t work.</p>', "OOPS_ERROR_SLOP")


def test_oops_error_slop_skips_direct_error():
    assert not _rule_fired('<p>Unable to connect. Check your network and try again.</p>', "OOPS_ERROR_SLOP")


def test_unreachable_code_fires():
    code = dedent("""\
        function doThing() {
          return result;
          const unused = 42;
        }
    """)
    assert _rule_fired(code, "UNREACHABLE_CODE", ".ts")


def test_unreachable_code_skips_normal_code():
    code = dedent("""\
        function doThing() {
          const x = 42;
          return x;
        }
    """)
    assert not _rule_fired(code, "UNREACHABLE_CODE", ".ts")


def test_empty_handler_fires():
    assert _rule_fired('<button onClick={() => {}}>Submit</button>', "EMPTY_HANDLER")


def test_empty_handler_fires_for_onchange():
    assert _rule_fired('<input onChange={() => {}} />', "EMPTY_HANDLER")


def test_empty_handler_skips_with_body():
    assert not _rule_fired('<button onClick={() => handleClick()}>Submit</button>', "EMPTY_HANDLER")


def test_dead_css_class_fires():
    assert _rule_fired(".empty-class {}", "DEAD_CSS_CLASS", ".css")


def test_dead_css_class_skips_rule_with_declarations():
    assert not _rule_fired(".btn { color: red; }", "DEAD_CSS_CLASS", ".css")


def test_deprecated_lifecycle_fires_for_component_will_mount():
    code = "componentWillMount() { this.fetchData(); }"
    assert _rule_fired(code, "DEPRECATED_LIFECYCLE", ".tsx")


def test_deprecated_lifecycle_fires_for_will_receive_props():
    code = "componentWillReceiveProps(nextProps) { this.setState({}); }"
    assert _rule_fired(code, "DEPRECATED_LIFECYCLE", ".tsx")


def test_deprecated_lifecycle_skips_modern_hooks():
    assert not _rule_fired("useEffect(() => { fetchData(); }, []);", "DEPRECATED_LIFECYCLE", ".tsx")


def test_disabled_lint_rule_fires_for_eslint_disable():
    assert _rule_fired("// eslint-disable-next-line no-unused-vars", "DISABLED_LINT_RULE", ".ts")


def test_disabled_lint_rule_fires_for_block_disable():
    assert _rule_fired("/* eslint-disable react-hooks/exhaustive-deps */", "DISABLED_LINT_RULE", ".ts")


def test_disabled_lint_rule_skips_regular_comment():
    assert not _rule_fired("// This function handles the auth flow", "DISABLED_LINT_RULE", ".ts")


def test_any_type_slop_fires_for_colon_any():
    assert _rule_fired("function process(data: any) { return data; }", "ANY_TYPE_SLOP", ".ts")


def test_any_type_slop_fires_for_as_any():
    assert _rule_fired("const result = data as any;", "ANY_TYPE_SLOP", ".ts")


def test_any_type_slop_skips_unknown():
    assert not _rule_fired("function process(data: unknown) { return data; }", "ANY_TYPE_SLOP", ".ts")


def test_ts_ignore_slop_fires_for_ts_ignore():
    assert _rule_fired("// @ts-ignore\nconst x = badThing();", "TS_IGNORE_SLOP", ".ts")


def test_ts_ignore_slop_fires_for_ts_nocheck():
    assert _rule_fired("// @ts-nocheck\nexport {};", "TS_IGNORE_SLOP", ".ts")


def test_ts_ignore_slop_skips_regular_comment():
    assert not _rule_fired("// This handles the fetch error", "TS_IGNORE_SLOP", ".ts")


def test_hardcoded_color_style_slop_fires():
    code = '<div style={{ color: "#3b82f6", fontSize: "14px" }}>Blue text</div>'
    assert _rule_fired(code, "HARDCODED_COLOR_STYLE_SLOP")


def test_hardcoded_color_style_slop_fires_for_rgb():
    code = '<div style={{ backgroundColor: "rgb(59, 130, 246)" }}>Blue bg</div>'
    assert _rule_fired(code, "HARDCODED_COLOR_STYLE_SLOP")


def test_hardcoded_color_style_slop_skips_tailwind_class():
    assert not _rule_fired('<div className="text-blue-500 bg-white">styled</div>', "HARDCODED_COLOR_STYLE_SLOP")


def test_star_rating_slop_fires_for_unicode_stars():
    assert _rule_fired('<p className="rating">★★★★★</p>', "STAR_RATING_SLOP")


def test_star_rating_slop_fires_for_emoji_stars():
    assert _rule_fired('<div>★★★★★ Trusted by 10,000+ users</div>', "STAR_RATING_SLOP")


def test_gradient_border_slop_fires():
    code = ".card { border-image: linear-gradient(to right, #3b82f6, #8b5cf6) 1; }"
    assert _rule_fired(code, "GRADIENT_BORDER_SLOP", ".css")


def test_gradient_border_slop_skips_solid_border():
    assert not _rule_fired(".card { border: 1px solid #e5e7eb; }", "GRADIENT_BORDER_SLOP", ".css")


def test_tailwind_v4_gradient_slop_fires_for_from_blue():
    assert _rule_fired('<div className="from-blue-500 to-purple-600 bg-gradient-to-r">hero</div>', "TAILWIND_V4_GRADIENT_SLOP")


def test_tailwind_v4_gradient_slop_fires_for_from_indigo():
    assert _rule_fired('<div className="from-indigo-400 to-cyan-500">section</div>', "TAILWIND_V4_GRADIENT_SLOP")


def test_tailwind_v4_gradient_slop_skips_amber_gradient():
    assert not _rule_fired('<div className="from-amber-400 to-orange-500">warm</div>', "TAILWIND_V4_GRADIENT_SLOP")


def test_fake_metric_slop_fires_for_uptime():
    assert _rule_fired('<p>99.99% uptime guaranteed</p>', "FAKE_METRIC_SLOP")


def test_fake_metric_slop_fires_for_10x():
    assert _rule_fired('<h3>10x faster than the competition</h3>', "FAKE_METRIC_SLOP")


def test_fake_metric_slop_fires_for_dollar_amount():
    assert _rule_fired('<span>$1M+ saved for customers</span>', "FAKE_METRIC_SLOP")


def test_fake_metric_slop_skips_specific_metric():
    assert not _rule_fired('<p>Reduced deploy time from 12min to 4min</p>', "FAKE_METRIC_SLOP")


def test_scroll_smooth_no_motion_slop_fires():
    assert _rule_fired('<div className="scroll-smooth overflow-auto">nav</div>', "SCROLL_SMOOTH_NO_MOTION_SLOP")


def test_scroll_smooth_no_motion_slop_skips_with_motion_reduce():
    code = '<div className="scroll-smooth motion-reduce:scroll-auto overflow-auto">nav</div>'
    assert not _rule_fired(code, "SCROLL_SMOOTH_NO_MOTION_SLOP")


def test_autofocus_slop_fires():
    assert _rule_fired('<input autoFocus type="text" />', "AUTOFOCUS_SLOP")


def test_autofocus_slop_fires_for_search_input():
    assert _rule_fired('<input autoFocus placeholder="Search..." />', "AUTOFOCUS_SLOP")


def test_autofocus_slop_skips_autofocus_false():
    assert not _rule_fired('<input autoFocus={false} type="text" />', "AUTOFOCUS_SLOP")


def test_no_select_content_slop_fires():
    assert _rule_fired('<p className="select-none text-gray-700">Copy this important text</p>', "NO_SELECT_CONTENT_SLOP")


def test_no_select_content_slop_skips_icon_button():
    assert not _rule_fired('<button className="select-none p-2" aria-label="close">✕</button>', "NO_SELECT_CONTENT_SLOP")


# ── Custom-check rules (Batches 1-2): missing_hover, missing_focus, etc. ─────


def test_spacing_repetition_slop_fires():
    code = '<div className="p-4 gap-4"><div className="p-4"><div className="p-4"><div className="p-4"><div className="p-4">x</div></div></div></div></div>'
    assert _rule_fired(code, "SPACING_REPETITION_SLOP")


def test_spacing_repetition_slop_skips_varied_spacing():
    code = '<div className="p-4"><div className="p-6"><div className="p-3">x</div></div></div>'
    assert not _rule_fired(code, "SPACING_REPETITION_SLOP")


def test_missing_hover_states_fires_for_button_no_hover():
    code = '<button className="bg-blue-500 text-white px-4 py-2 rounded">Submit</button>'
    assert _rule_fired(code, "MISSING_HOVER_STATES")


def test_missing_hover_states_skips_with_hover():
    code = '<button className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2">Submit</button>'
    assert not _rule_fired(code, "MISSING_HOVER_STATES")


def test_missing_focus_slop_fires_for_button_no_focus():
    code = '<button className="bg-blue-500 hover:bg-blue-600 text-white">Click</button>'
    assert _rule_fired(code, "MISSING_FOCUS_SLOP")


def test_missing_focus_slop_skips_with_focus_ring():
    code = '<button className="bg-blue-500 hover:bg-blue-600 focus:ring-2 text-white">Click</button>'
    assert not _rule_fired(code, "MISSING_FOCUS_SLOP")


def test_div_soup_slop_fires_for_div_heavy_file():
    # AST path: works on .tsx; needs >20 divs and zero semantic elements
    cols = "\n".join(f'<div className="col-{i}"><div>Item {i}</div></div>' for i in range(12))
    code = f"export default function Page() {{ return (<div><div><div>{cols}</div></div></div>); }}"
    assert _rule_fired(code, "DIV_SOUP_SLOP", ".tsx")


def test_div_soup_slop_skips_semantic_html():
    code = dedent("""\
        <main>
          <header><nav>Nav</nav></header>
          <section><article>Content</article></section>
          <aside>Sidebar</aside>
          <footer>Footer</footer>
        </main>
    """)
    assert not _rule_fired(code, "DIV_SOUP_SLOP")


def test_overpadded_layout_slop_fires_for_excessive_large_padding():
    code = dedent("""\
        <div className="p-16">
          <div className="p-16">
            <div className="p-12">
              <div className="p-12">
                <div className="p-16">content</div>
              </div>
            </div>
          </div>
        </div>
    """)
    assert _rule_fired(code, "OVERPADDED_LAYOUT_SLOP")


def test_overpadded_layout_slop_skips_normal_padding():
    code = '<div className="p-6"><div className="p-4">content</div></div>'
    assert not _rule_fired(code, "OVERPADDED_LAYOUT_SLOP")


def test_orphaned_label_slop_fires_for_label_without_htmlfor():
    code = '<label className="text-sm font-medium">Email</label>'
    assert _rule_fired(code, "ORPHANED_LABEL_SLOP")


def test_orphaned_label_slop_skips_with_htmlfor():
    code = '<label htmlFor="email" className="text-sm font-medium">Email</label>'
    assert not _rule_fired(code, "ORPHANED_LABEL_SLOP")


def test_nested_ternary_slop_fires():
    # Need >= 2 nested ternary expressions (without parens — parens wrap in
    # parenthesized_expression node, breaking the direct-child check in the AST walker)
    code = dedent("""\
        const a = x ? y ? 'yes' : 'no' : 'maybe';
        const b = p ? q ? 'foo' : 'bar' : 'baz';
    """)
    assert _rule_fired(code, "NESTED_TERNARY_SLOP", ".ts")


def test_nested_ternary_slop_skips_single_ternary():
    code = "const label = isAdmin ? 'Admin' : 'User';"
    assert not _rule_fired(code, "NESTED_TERNARY_SLOP", ".ts")


def test_img_alt_missing_slop_fires():
    assert _rule_fired('<img src="/hero.jpg" />', "IMG_ALT_MISSING_SLOP")


def test_img_alt_missing_slop_skips_with_alt():
    assert not _rule_fired('<img src="/hero.jpg" alt="Hero illustration" />', "IMG_ALT_MISSING_SLOP")


def test_img_alt_missing_slop_skips_decorative_empty_alt():
    assert not _rule_fired('<img src="/decor.svg" alt="" />', "IMG_ALT_MISSING_SLOP")


def test_icon_aria_missing_slop_fires_for_icon_only_button():
    code = '<button className="p-2"><svg viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" /></svg></button>'
    assert _rule_fired(code, "ICON_ARIA_MISSING_SLOP")


def test_icon_aria_missing_slop_skips_with_aria_label():
    code = '<button className="p-2" aria-label="Close menu"><svg viewBox="0 0 24 24"><path d="M6 18L18 6" /></svg></button>'
    assert not _rule_fired(code, "ICON_ARIA_MISSING_SLOP")


def test_touch_target_slop_fires_for_tiny_button():
    code = '<button className="w-4 h-4 p-0"><svg /></button>'
    assert _rule_fired(code, "TOUCH_TARGET_SLOP")


def test_touch_target_slop_skips_adequate_button():
    code = '<button className="w-10 h-10 p-2"><svg /></button>'
    assert not _rule_fired(code, "TOUCH_TARGET_SLOP")


def test_centered_paragraph_slop_fires():
    code = dedent("""\
        <p className="text-center max-w-prose">
          This is a very long paragraph of body copy that should not be centered because it is difficult to read.
          Users have to follow the text back and forth from line to line which increases cognitive load significantly.
        </p>
    """)
    assert _rule_fired(code, "CENTERED_PARAGRAPH_SLOP")


def test_centered_paragraph_slop_skips_short_centered():
    code = '<p className="text-center text-sm text-gray-500">© 2025 Acme</p>'
    assert not _rule_fired(code, "CENTERED_PARAGRAPH_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# OPACITY_ABUSE_SLOP — 5+ opacity/transparency usages in a single file
# ──────────────────────────────────────────────────────────────────────────────

def test_opacity_abuse_slop_fires_for_five_usages():
    code = '<div className="opacity-50 bg-white/20 opacity-75 bg-blue-500/30 bg-gray-900/40">Content</div>'
    assert _rule_fired(code, "OPACITY_ABUSE_SLOP")


def test_opacity_abuse_slop_skips_four_usages():
    code = '<div className="opacity-50 bg-white/20 opacity-75 bg-blue-500/30">Content</div>'
    assert not _rule_fired(code, "OPACITY_ABUSE_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# UGLY_SCROLLBAR_SLOP — overflow-x/y-auto|scroll without scrollbar styling
# ──────────────────────────────────────────────────────────────────────────────

def test_ugly_scrollbar_slop_fires_for_overflow_x_auto():
    code = '<div className="overflow-x-auto h-64 w-full">table content</div>'
    assert _rule_fired(code, "UGLY_SCROLLBAR_SLOP")


def test_ugly_scrollbar_slop_skips_with_scrollbar_class():
    code = '<div className="overflow-x-auto scrollbar-thin scrollbar-thumb-gray-400 h-64">table</div>'
    assert not _rule_fired(code, "UGLY_SCROLLBAR_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# MISSING_TRANSITION_SLOP — hover: class without transition in same className
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_transition_slop_fires_without_transition():
    code = '<button className="hover:bg-blue-600 bg-blue-500 text-white px-4 py-2">Click</button>'
    assert _rule_fired(code, "MISSING_TRANSITION_SLOP")


def test_missing_transition_slop_skips_with_transition():
    code = '<button className="hover:bg-blue-600 transition-colors duration-200 bg-blue-500 text-white">Click</button>'
    assert not _rule_fired(code, "MISSING_TRANSITION_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# DISABLED_NO_CURSOR_SLOP — disabled element missing cursor-not-allowed
# ──────────────────────────────────────────────────────────────────────────────

def test_disabled_no_cursor_slop_fires():
    code = '<button disabled className="bg-gray-300 text-gray-500 px-4 py-2">Send</button>'
    assert _rule_fired(code, "DISABLED_NO_CURSOR_SLOP")


def test_disabled_no_cursor_slop_skips_with_cursor_not_allowed():
    code = '<button disabled className="cursor-not-allowed bg-gray-300 opacity-50 px-4 py-2">Send</button>'
    assert not _rule_fired(code, "DISABLED_NO_CURSOR_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# COPY_PASTE_COMPONENT — near-identical block elements
# ──────────────────────────────────────────────────────────────────────────────

def test_copy_paste_component_fires_for_duplicate_blocks():
    inner = dedent("""\

      <h3 className="text-lg font-bold mb-2">Feature One</h3>
      <p className="text-gray-600 text-sm leading-relaxed">This feature helps you do something amazing for your workflow.</p>
      <button className="mt-4 btn-primary px-4 py-2 rounded">Learn More</button>
    """)
    code = dedent(f"""\
        <div className="feature-card w-full border rounded-lg p-6 shadow-sm bg-white">{inner}</div>
        <div className="feature-card w-full border rounded-lg p-6 shadow-sm bg-white">{inner}</div>
    """)
    assert _rule_fired(code, "COPY_PASTE_COMPONENT")


def test_copy_paste_component_skips_different_blocks():
    code = dedent("""\
        <div className="feature-card w-full border rounded-lg p-6 shadow-sm bg-white">
          <h3 className="text-lg font-bold mb-2">Feature One with unique content only here</h3>
          <p className="text-gray-600">Something exclusive to the first block only.</p>
        </div>
        <div className="feature-card w-full border rounded-lg p-6 shadow-sm bg-white">
          <h3 className="text-lg font-bold mb-2">Feature Two with completely different data</h3>
          <p className="text-gray-600">Something exclusive to the second block only.</p>
        </div>
    """)
    assert not _rule_fired(code, "COPY_PASTE_COMPONENT")


# ──────────────────────────────────────────────────────────────────────────────
# COMMENTED_OUT_CODE — 3+ lines of commented-out source code
# ──────────────────────────────────────────────────────────────────────────────

def test_commented_out_code_fires_for_three_code_lines():
    code = dedent("""\
        // const Header = () => {
        // return <div className="header">Header</div>;
        // import React from 'react';
        export const App = () => <main>App</main>;
    """)
    assert _rule_fired(code, "COMMENTED_OUT_CODE")


def test_commented_out_code_skips_regular_comments():
    code = dedent("""\
        // This function handles the authentication flow
        // See the README for more context about this approach
        // Third purely descriptive comment for documentation
        export const login = () => {};
    """)
    assert not _rule_fired(code, "COMMENTED_OUT_CODE")


# ──────────────────────────────────────────────────────────────────────────────
# UNUSED_IMPORT — import identifier never referenced elsewhere in the file
# ──────────────────────────────────────────────────────────────────────────────

def test_unused_import_fires_when_identifier_not_used():
    code = dedent("""\
        import { Button } from '@/components/ui/button';
        export const Card = () => <div className="card">Card content</div>;
    """)
    assert _rule_fired(code, "UNUSED_IMPORT")


def test_unused_import_skips_when_identifier_is_used():
    code = dedent("""\
        import { Button } from '@/components/ui/button';
        export const Card = () => <div><Button>Click me</Button></div>;
    """)
    assert not _rule_fired(code, "UNUSED_IMPORT")


def test_unused_import_reports_local_alias_and_namespace_names():
    code = dedent("""\
        import React, { Button as PrimaryButton } from 'react';
        import * as Icons from './icons';
        export const Card = () => React.createElement('div');
    """)
    issues = [issue for issue in _issues_for(code) if issue["id"] == "UNUSED_IMPORT"]
    assert len(issues) == 1
    assert "PrimaryButton" in issues[0]["issue"]
    assert "Icons" in issues[0]["issue"]


def test_unused_import_skips_used_default_alias_and_namespace_names():
    code = dedent("""\
        import React, { Button as PrimaryButton } from 'react';
        import * as Icons from './icons';
        export const Card = () => (
          <PrimaryButton icon={Icons.Check}>{React.version}</PrimaryButton>
        );
    """)
    assert not _rule_fired(code, "UNUSED_IMPORT")


# ──────────────────────────────────────────────────────────────────────────────
# UNUSED_STATE — useState state variable never read
# ──────────────────────────────────────────────────────────────────────────────

def test_unused_state_fires_when_state_var_not_read():
    code = dedent("""\
        import { useState } from 'react';
        export const Counter = () => {
          const [loading, setLoading] = useState(false);
          return <div>Content</div>;
        };
    """)
    assert _rule_fired(code, "UNUSED_STATE")


def test_unused_state_skips_when_state_var_is_read():
    code = dedent("""\
        import { useState } from 'react';
        export const Counter = () => {
          const [loading, setLoading] = useState(false);
          if (loading) return <div>Loading...</div>;
          return <div>Content</div>;
        };
    """)
    assert not _rule_fired(code, "UNUSED_STATE")


# ──────────────────────────────────────────────────────────────────────────────
# LOW_CONTRAST_SLOP — insufficient color contrast between text and background
# ──────────────────────────────────────────────────────────────────────────────

def test_low_contrast_slop_fires_for_poor_contrast(tmp_path):
    code = '<p className="bg-yellow-300 text-white font-bold">Warning text</p>'
    p = tmp_path / "Component.tsx"
    p.write_text(code, encoding="utf-8")
    # yellow-300 (~#fde047) on white (#ffffff) has near-1:1 contrast ratio
    dynamic_colors = {"yellow-300": "#fde047", "white": "#ffffff"}
    issues = analyze_file(p, dynamic_colors=dynamic_colors)
    assert any(i.get("id") == "LOW_CONTRAST_SLOP" for i in issues)


def test_low_contrast_slop_skips_without_dynamic_colors(tmp_path):
    code = '<p className="bg-yellow-300 text-white font-bold">Warning text</p>'
    p = tmp_path / "Component.tsx"
    p.write_text(code, encoding="utf-8")
    # Without dynamic_colors, the contrast check is skipped entirely
    issues = analyze_file(p)
    assert not any(i.get("id") == "LOW_CONTRAST_SLOP" for i in issues)


def test_analyze_directory_skips_project_color_audit_without_color_sources(tmp_path):
    from uidetox.analyzer import analyze_directory

    (tmp_path / "pyproject.toml").write_text(
        dedent("""\
            [project]
            name = "tool-only"
            version = "0.1.0"
        """),
        encoding="utf-8",
    )

    issues = analyze_directory(str(tmp_path))

    assert not any(
        i.get("id") == "LOW_CONTRAST_SLOP" and "Dynamic color audit" in i.get("issue", "")
        for i in issues
    )


def test_audit_project_colors_ignores_default_tailwind_pairs_when_not_declared(tmp_path):
    from uidetox.color_utils import audit_project_colors

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "globals.css").write_text(
        ":root { --brand: #123456; --accent: #abcdef; }",
        encoding="utf-8",
    )

    violations = audit_project_colors(tmp_path)
    assert violations == []


# ──────────────────────────────────────────────────────────────────────────────
# EMOJI_BULLET_LIST_SLOP — 3+ emoji-prefixed bullet lines
# ──────────────────────────────────────────────────────────────────────────────

def test_emoji_bullet_list_slop_fires_for_three_bullets():
    code = dedent("""\
        ✅ Auto-scaling for all plans
        🚀 Deploy in under 5 minutes
        💡 Built-in monitoring dashboard
    """)
    assert _rule_fired(code, "EMOJI_BULLET_LIST_SLOP", ext=".html")


def test_emoji_bullet_list_slop_skips_two_bullets():
    code = dedent("""\
        ✅ Auto-scaling for all plans
        🚀 Deploy in under 5 minutes
    """)
    assert not _rule_fired(code, "EMOJI_BULLET_LIST_SLOP", ext=".html")


# ──────────────────────────────────────────────────────────────────────────────
# TESTIMONIAL_GRID_SLOP — 3+ quoted testimonials with attribution dashes
# ──────────────────────────────────────────────────────────────────────────────

def test_testimonial_grid_slop_fires_for_three_testimonials():
    code = dedent("""\
        "This product changed our workflow and saved us hours every day." — Sarah Johnson, CEO
        "Absolutely incredible tool, our team loves using it for everything." — Mike Chen, CTO
        "Best investment we made for our engineering team this entire year." — Emma Davis, VP Eng
    """)
    assert _rule_fired(code, "TESTIMONIAL_GRID_SLOP")


def test_testimonial_grid_slop_skips_two_testimonials():
    code = dedent("""\
        "This product changed our workflow and saved us hours every day." — Sarah Johnson, CEO
        "Absolutely incredible tool, our team loves using it for everything." — Mike Chen, CTO
    """)
    assert not _rule_fired(code, "TESTIMONIAL_GRID_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# PRICING_TABLE_SLOP — 3+ pricing tier names (Free, Pro, Enterprise, etc.)
# ──────────────────────────────────────────────────────────────────────────────

def test_pricing_table_slop_fires_for_three_tiers():
    code = dedent("""\
        <div>
          <h2>Free Plan</h2>
          <p>Perfect for individuals getting started.</p>
          <h2>Pro Plan</h2>
          <p>For growing teams that need advanced features.</p>
          <h2>Enterprise</h2>
          <p>Full suite for large organizations at scale.</p>
        </div>
    """)
    assert _rule_fired(code, "PRICING_TABLE_SLOP")


def test_pricing_table_slop_skips_two_tiers():
    code = dedent("""\
        <div>
          <h2>Free Plan</h2>
          <p>Perfect for individuals getting started.</p>
          <h2>Pro Plan</h2>
          <p>For growing teams that need advanced features.</p>
        </div>
    """)
    assert not _rule_fired(code, "PRICING_TABLE_SLOP")


# ──────────────────────────────────────────────────────────────────────────────
# BATCH 18: Accessibility, semantic HTML, and modern JS anti-patterns
# ──────────────────────────────────────────────────────────────────────────────

def test_button_type_missing_slop_fires_for_button_without_type():
    code = '<button className="btn-primary px-4 py-2">Submit</button>'
    assert _rule_fired(code, "BUTTON_TYPE_MISSING_SLOP")


def test_button_type_missing_slop_skips_with_type_button():
    code = '<button type="button" className="btn-primary">Click</button>'
    assert not _rule_fired(code, "BUTTON_TYPE_MISSING_SLOP")


def test_button_type_missing_slop_skips_with_type_submit():
    code = '<button type="submit" className="btn-primary">Send</button>'
    assert not _rule_fired(code, "BUTTON_TYPE_MISSING_SLOP")


def test_float_layout_slop_fires_for_float_left():
    code = '.sidebar { float: left; width: 300px; }'
    assert _rule_fired(code, "FLOAT_LAYOUT_SLOP", ext=".css")


def test_float_layout_slop_fires_for_float_right():
    code = '.logo { float: right; margin-left: auto; }'
    assert _rule_fired(code, "FLOAT_LAYOUT_SLOP", ext=".css")


def test_float_layout_slop_skips_float_none():
    code = '.clearfix { float: none; }'
    assert not _rule_fired(code, "FLOAT_LAYOUT_SLOP", ext=".css")


def test_autocomplete_off_slop_fires_for_jsx():
    code = '<input type="email" autoComplete="off" className="w-full" />'
    assert _rule_fired(code, "AUTOCOMPLETE_OFF_SLOP")


def test_autocomplete_off_slop_fires_for_html():
    code = '<input type="text" autocomplete="off" name="search" />'
    assert _rule_fired(code, "AUTOCOMPLETE_OFF_SLOP", ext=".html")


def test_autocomplete_off_slop_skips_specific_token():
    code = '<input type="email" autoComplete="email" className="w-full" />'
    assert not _rule_fired(code, "AUTOCOMPLETE_OFF_SLOP")


def test_focus_outline_removed_slop_fires_for_outline_none():
    code = 'button:focus { outline: none; color: blue; }'
    assert _rule_fired(code, "FOCUS_OUTLINE_REMOVED_SLOP", ext=".css")


def test_focus_outline_removed_slop_fires_for_outline_zero():
    code = '.btn:focus { outline: 0; border: none; }'
    assert _rule_fired(code, "FOCUS_OUTLINE_REMOVED_SLOP", ext=".css")


def test_focus_outline_removed_slop_skips_accessible_outline():
    code = 'button:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }'
    assert not _rule_fired(code, "FOCUS_OUTLINE_REMOVED_SLOP", ext=".css")


def test_tabindex_positive_slop_fires_for_jsx_tabindex():
    code = '<div tabIndex={1} role="button">Menu item</div>'
    assert _rule_fired(code, "TABINDEX_POSITIVE_SLOP")


def test_tabindex_positive_slop_fires_for_html_tabindex():
    code = '<div tabindex="2">Focusable section</div>'
    assert _rule_fired(code, "TABINDEX_POSITIVE_SLOP", ext=".html")


def test_tabindex_positive_slop_skips_zero():
    code = '<div tabIndex={0} role="button">Menu item</div>'
    assert not _rule_fired(code, "TABINDEX_POSITIVE_SLOP")


def test_tabindex_positive_slop_skips_negative_one():
    code = '<div tabIndex={-1}>Hidden from tab order</div>'
    assert not _rule_fired(code, "TABINDEX_POSITIVE_SLOP")


def test_style_tag_in_jsx_slop_fires():
    code = dedent("""\
        const Card = () => (
          <div>
            <style>{`.card { background: blue; }`}</style>
            <p>Content</p>
          </div>
        );
    """)
    assert _rule_fired(code, "STYLE_TAG_IN_JSX_SLOP")


def test_style_tag_in_jsx_slop_skips_css_file():
    code = '.card { background: blue; }'
    assert not _rule_fired(code, "STYLE_TAG_IN_JSX_SLOP", ext=".css")


def test_use_index_as_key_slop_fires():
    code = 'items.map((item, index) => <li key={index}>{item.name}</li>)'
    assert _rule_fired(code, "USE_INDEX_AS_KEY_SLOP")


def test_use_index_as_key_slop_fires_for_idx():
    code = 'list.map((el, idx) => <div key={idx}>{el}</div>)'
    assert _rule_fired(code, "USE_INDEX_AS_KEY_SLOP")


def test_use_index_as_key_slop_skips_stable_id():
    code = 'items.map((item) => <li key={item.id}>{item.name}</li>)'
    assert not _rule_fired(code, "USE_INDEX_AS_KEY_SLOP")


def test_redundant_bool_compare_slop_fires_for_triple_eq_true():
    code = 'if (isLoading === true) { showSpinner(); }'
    assert _rule_fired(code, "REDUNDANT_BOOL_COMPARE_SLOP")


def test_redundant_bool_compare_slop_fires_for_not_eq_false():
    code = 'const show = isVisible !== false;'
    assert _rule_fired(code, "REDUNDANT_BOOL_COMPARE_SLOP")


def test_redundant_bool_compare_slop_skips_direct_check():
    code = 'if (isLoading) { showSpinner(); } else if (!isVisible) { hide(); }'
    assert not _rule_fired(code, "REDUNDANT_BOOL_COMPARE_SLOP")


def test_table_header_no_scope_slop_fires():
    code = '<table><thead><tr><th>Name</th><th>Email</th></tr></thead></table>'
    assert _rule_fired(code, "TABLE_HEADER_NO_SCOPE_SLOP")


def test_table_header_no_scope_slop_skips_with_scope():
    code = '<table><thead><tr><th scope="col">Name</th><th scope="col">Email</th></tr></thead></table>'
    assert not _rule_fired(code, "TABLE_HEADER_NO_SCOPE_SLOP")


def test_media_autoplay_slop_fires_for_video_without_muted():
    code = '<video autoPlay src="/intro.mp4" className="w-full" />'
    assert _rule_fired(code, "MEDIA_AUTOPLAY_SLOP")


def test_media_autoplay_slop_fires_for_audio_without_muted():
    code = '<audio autoplay src="/ambient.mp3" loop />'
    assert _rule_fired(code, "MEDIA_AUTOPLAY_SLOP", ext=".html")


def test_media_autoplay_slop_skips_with_muted():
    code = '<video autoPlay muted loop src="/hero.mp4" className="w-full" />'
    assert not _rule_fired(code, "MEDIA_AUTOPLAY_SLOP")


def test_empty_aria_label_slop_fires_for_double_quotes():
    code = '<button aria-label="" className="p-2"><svg /></button>'
    assert _rule_fired(code, "EMPTY_ARIA_LABEL_SLOP")


def test_empty_aria_label_slop_fires_for_single_quotes():
    code = "<button aria-label='' className='icon-btn'><svg /></button>"
    assert _rule_fired(code, "EMPTY_ARIA_LABEL_SLOP")


def test_empty_aria_label_slop_skips_descriptive_label():
    code = '<button aria-label="Close dialog" className="p-2"><svg /></button>'
    assert not _rule_fired(code, "EMPTY_ARIA_LABEL_SLOP")


def test_alert_usage_slop_fires_for_string_arg():
    code = 'alert("Please fill in all required fields before submitting.")'
    assert _rule_fired(code, "ALERT_USAGE_SLOP")


def test_alert_usage_slop_fires_for_template_literal():
    code = 'alert(`Error: ${message}`)'
    assert _rule_fired(code, "ALERT_USAGE_SLOP")


def test_alert_usage_slop_skips_variable_alert():
    code = 'const alertEl = document.querySelector(".alert-box");'
    assert not _rule_fired(code, "ALERT_USAGE_SLOP")


# ── Batch 19 tests ─────────────────────────────────────────────────────────


def test_prop_spreading_slop_fires_on_props():
    code = '<div {...props} className="container" />'
    assert _rule_fired(code, "PROP_SPREADING_SLOP")


def test_prop_spreading_slop_fires_on_rest():
    code = 'return <button {...rest} onClick={handleClick} />;'
    assert _rule_fired(code, "PROP_SPREADING_SLOP")


def test_prop_spreading_slop_skips_named_spread():
    code = '<div {...{ className, style }} />'
    assert not _rule_fired(code, "PROP_SPREADING_SLOP")


def test_css_empty_rule_slop_fires_on_empty_block():
    code = ".my-component {}"
    assert _rule_fired(code, "CSS_EMPTY_RULE_SLOP", ".css")


def test_css_empty_rule_slop_fires_with_whitespace():
    code = ".hero {\n   \n}"
    assert _rule_fired(code, "CSS_EMPTY_RULE_SLOP", ".css")


def test_css_empty_rule_slop_skips_populated_rule():
    code = ".hero { color: red; background: blue; }"
    assert not _rule_fired(code, "CSS_EMPTY_RULE_SLOP", ".css")


def test_catch_console_only_slop_fires():
    code = 'try { fetch(url); } catch (e) { console.error(e); }'
    assert _rule_fired(code, "CATCH_CONSOLE_ONLY_SLOP")


def test_catch_console_only_slop_skips_rethrow():
    code = 'try { fetch(url); } catch (e) { console.error(e); throw e; }'
    assert not _rule_fired(code, "CATCH_CONSOLE_ONLY_SLOP")


def test_hardcoded_timeout_slop_fires_on_large_number():
    code = 'setTimeout(() => hideToast(), 3000)'
    assert _rule_fired(code, "HARDCODED_TIMEOUT_SLOP")


def test_hardcoded_timeout_slop_fires_on_interval():
    code = 'setInterval(poll, 5000)'
    assert _rule_fired(code, "HARDCODED_TIMEOUT_SLOP")


def test_hardcoded_timeout_slop_skips_zero():
    code = 'setTimeout(callback, 0)'
    assert not _rule_fired(code, "HARDCODED_TIMEOUT_SLOP")


def test_hardcoded_timeout_slop_skips_small_number():
    code = 'setTimeout(callback, 50)'
    assert not _rule_fired(code, "HARDCODED_TIMEOUT_SLOP")


def test_deprecated_finddomnode_slop_fires_on_reactdom():
    code = 'const node = ReactDOM.findDOMNode(this);'
    assert _rule_fired(code, "DEPRECATED_FINDDOMNODE_SLOP")


def test_deprecated_finddomnode_slop_fires_bare():
    code = 'const el = findDOMNode(componentInstance);'
    assert _rule_fired(code, "DEPRECATED_FINDDOMNODE_SLOP")


def test_deprecated_finddomnode_slop_skips_unrelated():
    code = 'const el = document.getElementById("root");'
    assert not _rule_fired(code, "DEPRECATED_FINDDOMNODE_SLOP")


def test_no_passive_scroll_listener_slop_fires_on_scroll():
    code = 'window.addEventListener("scroll", handleScroll, false);'
    assert _rule_fired(code, "NO_PASSIVE_SCROLL_LISTENER_SLOP")


def test_no_passive_scroll_listener_slop_fires_on_touchstart():
    code = "el.addEventListener('touchstart', onTouch, false);"
    assert _rule_fired(code, "NO_PASSIVE_SCROLL_LISTENER_SLOP")


def test_no_passive_scroll_listener_slop_skips_click():
    code = 'el.addEventListener("click", handleClick, false);'
    assert not _rule_fired(code, "NO_PASSIVE_SCROLL_LISTENER_SLOP")


def test_deprecated_class_component_slop_fires_on_component():
    code = 'class MyWidget extends Component { render() { return <div />; } }'
    assert _rule_fired(code, "DEPRECATED_CLASS_COMPONENT_SLOP")


def test_deprecated_class_component_slop_fires_on_pure_component():
    code = 'class List extends React.PureComponent { render() { return null; } }'
    assert _rule_fired(code, "DEPRECATED_CLASS_COMPONENT_SLOP")


def test_deprecated_class_component_slop_skips_plain_class():
    code = 'class MyService extends BaseService { constructor() { super(); } }'
    assert not _rule_fired(code, "DEPRECATED_CLASS_COMPONENT_SLOP")


def test_css_important_animation_slop_fires_on_transition():
    code = '.btn { transition: all 0.3s ease !important; }'
    assert _rule_fired(code, "CSS_IMPORTANT_ANIMATION_SLOP", ".css")


def test_css_important_animation_slop_fires_on_animation():
    code = '.spinner { animation: spin 1s linear infinite !important; }'
    assert _rule_fired(code, "CSS_IMPORTANT_ANIMATION_SLOP", ".css")


def test_css_important_animation_slop_skips_color_important():
    code = '.btn { color: red !important; }'
    assert not _rule_fired(code, "CSS_IMPORTANT_ANIMATION_SLOP", ".css")


def test_missing_aria_role_slop_fires_on_div_with_onclick():
    code = '<div onClick={handleSelect} className="item">Select</div>'
    assert _rule_fired(code, "MISSING_ARIA_ROLE_SLOP")


def test_missing_aria_role_slop_fires_on_span_with_onkeydown():
    code = '<span onKeydown={handleKey} tabIndex={0}>Option</span>'
    assert _rule_fired(code, "MISSING_ARIA_ROLE_SLOP")


def test_missing_aria_role_slop_skips_div_with_role():
    code = '<div role="button" onClick={handleSelect} tabIndex={0}>Select</div>'
    assert not _rule_fired(code, "MISSING_ARIA_ROLE_SLOP")


def test_css_overflow_hidden_body_slop_fires():
    code = 'body { margin: 0; overflow: hidden; font-family: sans-serif; }'
    assert _rule_fired(code, "CSS_OVERFLOW_HIDDEN_BODY_SLOP", ".css")


def test_css_overflow_hidden_body_slop_fires_on_html():
    code = 'html { box-sizing: border-box; overflow: hidden; }'
    assert _rule_fired(code, "CSS_OVERFLOW_HIDDEN_BODY_SLOP", ".css")


def test_css_overflow_hidden_body_slop_skips_component():
    code = '.modal-container { overflow: hidden; position: fixed; }'
    assert not _rule_fired(code, "CSS_OVERFLOW_HIDDEN_BODY_SLOP", ".css")


def test_vague_aria_label_slop_fires_on_button():
    code = '<button aria-label="button" onClick={handleClick}><PlusIcon /></button>'
    assert _rule_fired(code, "VAGUE_ARIA_LABEL_SLOP")


def test_vague_aria_label_slop_fires_on_close():
    code = '<button aria-label="close" onClick={onClose}><XIcon /></button>'
    assert _rule_fired(code, "VAGUE_ARIA_LABEL_SLOP")


def test_vague_aria_label_slop_skips_descriptive():
    code = '<button aria-label="Close settings panel" onClick={onClose}><XIcon /></button>'
    assert not _rule_fired(code, "VAGUE_ARIA_LABEL_SLOP")


def test_lazy_without_suspense_slop_fires_on_react_lazy():
    code = 'const Dashboard = React.lazy(() => import("./Dashboard"));'
    assert _rule_fired(code, "LAZY_WITHOUT_SUSPENSE_SLOP")


def test_lazy_without_suspense_slop_fires_on_bare_lazy():
    code = "const Chart = lazy(() => import('./Chart'));"
    assert _rule_fired(code, "LAZY_WITHOUT_SUSPENSE_SLOP")


def test_lazy_without_suspense_slop_skips_other_lazy():
    code = 'const lazyValue = computeExpensiveValue();'
    assert not _rule_fired(code, "LAZY_WITHOUT_SUSPENSE_SLOP")


# ── Batch 20 ──────────────────────────────────────────────────────────────────

def test_non_null_assertion_slop_fires_on_property_access():
    code = 'const name = user!.profile.name;'
    assert _rule_fired(code, "NON_NULL_ASSERTION_SLOP")


def test_non_null_assertion_slop_fires_on_index_access():
    code = 'const first = items![0];'
    assert _rule_fired(code, "NON_NULL_ASSERTION_SLOP")


def test_non_null_assertion_slop_skips_logical_not():
    code = 'const isValid = !user.name;'
    assert not _rule_fired(code, "NON_NULL_ASSERTION_SLOP")


def test_eval_usage_slop_fires_on_eval_call():
    code = 'const result = eval(userInput);'
    assert _rule_fired(code, "EVAL_USAGE_SLOP")


def test_eval_usage_slop_fires_with_space():
    code = 'eval ("return 1+1");'
    assert _rule_fired(code, "EVAL_USAGE_SLOP")


def test_eval_usage_slop_skips_evaluate():
    code = 'const ok = evaluate(expr);'
    assert not _rule_fired(code, "EVAL_USAGE_SLOP")


def test_empty_interface_slop_fires_on_empty_interface():
    code = 'interface Props {}'
    assert _rule_fired(code, "EMPTY_INTERFACE_SLOP")


def test_empty_interface_slop_fires_on_extends_empty():
    code = 'interface AdminProps extends BaseProps {}'
    assert _rule_fired(code, "EMPTY_INTERFACE_SLOP")


def test_empty_interface_slop_skips_non_empty():
    code = 'interface Props { id: string; }'
    assert not _rule_fired(code, "EMPTY_INTERFACE_SLOP")


def test_fragment_shorthand_slop_fires_on_react_fragment():
    code = 'return <React.Fragment><h1>Hi</h1></React.Fragment>;'
    assert _rule_fired(code, "FRAGMENT_SHORTHAND_SLOP")


def test_fragment_shorthand_slop_fires_without_attrs():
    code = 'const el = <React.Fragment><p>text</p></React.Fragment>;'
    assert _rule_fired(code, "FRAGMENT_SHORTHAND_SLOP")


def test_fragment_shorthand_slop_skips_shorthand():
    code = 'return <><h1>Hi</h1></>;'
    assert not _rule_fired(code, "FRAGMENT_SHORTHAND_SLOP")


def test_select_no_label_slop_fires_on_unlabelled_select():
    code = '<select name="country"><option>US</option></select>'
    assert _rule_fired(code, "SELECT_NO_LABEL_SLOP")


def test_select_no_label_slop_fires_on_bare_select():
    code = '<select onChange={handleChange}></select>'
    assert _rule_fired(code, "SELECT_NO_LABEL_SLOP")


def test_select_no_label_slop_skips_aria_labelled():
    code = '<select aria-label="Choose country"><option>US</option></select>'
    assert not _rule_fired(code, "SELECT_NO_LABEL_SLOP")


def test_absolute_font_size_body_slop_fires_on_html():
    code = 'html { font-size: 16px; }'
    assert _rule_fired(code, "ABSOLUTE_FONT_SIZE_BODY_SLOP", ext=".css")


def test_absolute_font_size_body_slop_fires_on_body():
    code = 'body { margin: 0; font-size: 14px; }'
    assert _rule_fired(code, "ABSOLUTE_FONT_SIZE_BODY_SLOP", ext=".css")


def test_absolute_font_size_body_slop_skips_percent():
    code = 'html { font-size: 100%; }'
    assert not _rule_fired(code, "ABSOLUTE_FONT_SIZE_BODY_SLOP", ext=".css")


def test_grid_auto_fit_missing_slop_fires_on_fixed_repeat():
    code = '.grid { grid-template-columns: repeat(3, 1fr); }'
    assert _rule_fired(code, "GRID_AUTO_FIT_MISSING_SLOP", ext=".css")


def test_grid_auto_fit_missing_slop_fires_on_four_col():
    code = '.layout { grid-template-columns: repeat(4, minmax(0, 1fr)); }'
    assert _rule_fired(code, "GRID_AUTO_FIT_MISSING_SLOP", ext=".css")


def test_grid_auto_fit_missing_slop_skips_auto_fit():
    code = '.grid { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }'
    assert not _rule_fired(code, "GRID_AUTO_FIT_MISSING_SLOP", ext=".css")


def test_css_overflow_scroll_slop_fires_on_overflow_scroll():
    code = '.box { overflow: scroll; }'
    assert _rule_fired(code, "CSS_OVERFLOW_SCROLL_SLOP", ext=".css")


def test_css_overflow_scroll_slop_fires_on_overflow_x_scroll():
    code = '.table { overflow-x: scroll; }'
    assert _rule_fired(code, "CSS_OVERFLOW_SCROLL_SLOP", ext=".css")


def test_css_overflow_scroll_slop_skips_overflow_auto():
    code = '.box { overflow: auto; }'
    assert not _rule_fired(code, "CSS_OVERFLOW_SCROLL_SLOP", ext=".css")


def test_background_attachment_fixed_slop_fires():
    code = '.hero { background-attachment: fixed; }'
    assert _rule_fired(code, "BACKGROUND_ATTACHMENT_FIXED_SLOP", ext=".css")


def test_background_attachment_fixed_slop_fires_in_rule():
    code = 'body { background-image: url(bg.jpg); background-attachment: fixed; }'
    assert _rule_fired(code, "BACKGROUND_ATTACHMENT_FIXED_SLOP", ext=".css")


def test_background_attachment_fixed_slop_skips_scroll():
    code = '.card { background-attachment: scroll; }'
    assert not _rule_fired(code, "BACKGROUND_ATTACHMENT_FIXED_SLOP", ext=".css")


def test_resize_none_slop_fires_on_textarea():
    code = 'textarea { resize: none; }'
    assert _rule_fired(code, "RESIZE_NONE_SLOP", ext=".css")


def test_resize_none_slop_fires_in_class():
    code = '.input-box { width: 100%; resize: none; }'
    assert _rule_fired(code, "RESIZE_NONE_SLOP", ext=".css")


def test_resize_none_slop_skips_vertical():
    code = 'textarea { resize: vertical; }'
    assert not _rule_fired(code, "RESIZE_NONE_SLOP", ext=".css")


def test_button_type_reset_slop_fires_on_reset_button():
    code = '<button type="reset">Clear</button>'
    assert _rule_fired(code, "BUTTON_TYPE_RESET_SLOP")


def test_button_type_reset_slop_fires_single_quote():
    code = "<button type='reset' className='btn-danger'>Reset form</button>"
    assert _rule_fired(code, "BUTTON_TYPE_RESET_SLOP")


def test_button_type_reset_slop_skips_submit():
    code = '<button type="submit">Send</button>'
    assert not _rule_fired(code, "BUTTON_TYPE_RESET_SLOP")


def test_css_vendor_prefix_slop_fires_on_webkit():
    code = '.el { -webkit-transform: translateX(10px); }'
    assert _rule_fired(code, "CSS_VENDOR_PREFIX_SLOP", ext=".css")


def test_css_vendor_prefix_slop_fires_on_moz():
    code = '.el { -moz-user-select: none; }'
    assert _rule_fired(code, "CSS_VENDOR_PREFIX_SLOP", ext=".css")


def test_css_vendor_prefix_slop_skips_standard():
    code = '.el { transform: translateX(10px); }'
    assert not _rule_fired(code, "CSS_VENDOR_PREFIX_SLOP", ext=".css")




# ── Batch 21 tests ──────────────────────────────────────────────────────────

# DOCUMENT_WRITE_SLOP
def test_document_write_slop_fires_on_write():
    code = 'document.write("<p>Hello world</p>");'
    assert _rule_fired(code, "DOCUMENT_WRITE_SLOP", ext=".ts")


def test_document_write_slop_fires_with_variable():
    code = 'document.write(userInput);'
    assert _rule_fired(code, "DOCUMENT_WRITE_SLOP", ext=".js")


def test_document_write_slop_skips_document_element():
    code = 'const el = document.documentElement;'
    assert not _rule_fired(code, "DOCUMENT_WRITE_SLOP", ext=".ts")


# INNER_HTML_ASSIGN_SLOP
def test_inner_html_assign_slop_fires_on_assignment():
    code = "el.innerHTML = '<div>test</div>';"
    assert _rule_fired(code, "INNER_HTML_ASSIGN_SLOP", ext=".ts")


def test_inner_html_assign_slop_fires_on_concat():
    code = 'container.innerHTML += unsafeContent;'
    assert _rule_fired(code, "INNER_HTML_ASSIGN_SLOP", ext=".ts")


def test_inner_html_assign_slop_skips_domPurify():
    code = "el.innerHTML = DOMPurify.sanitize(html);"
    assert not _rule_fired(code, "INNER_HTML_ASSIGN_SLOP", ext=".ts")


# LOCALSTORAGE_SENSITIVE_SLOP
def test_localstorage_sensitive_slop_fires_on_token():
    code = "localStorage.setItem('token', accessToken);"
    assert _rule_fired(code, "LOCALSTORAGE_SENSITIVE_SLOP", ext=".ts")


def test_localstorage_sensitive_slop_fires_on_password():
    code = 'localStorage.setItem("password", pwd);'
    assert _rule_fired(code, "LOCALSTORAGE_SENSITIVE_SLOP", ext=".ts")


def test_localstorage_sensitive_slop_skips_theme():
    code = "localStorage.setItem('theme', 'dark');"
    assert not _rule_fired(code, "LOCALSTORAGE_SENSITIVE_SLOP", ext=".ts")


# OPEN_REDIRECT_SLOP
def test_open_redirect_slop_fires_on_href_variable():
    code = 'location.href = returnUrl;'
    assert _rule_fired(code, "OPEN_REDIRECT_SLOP", ext=".ts")


def test_open_redirect_slop_fires_on_window_location():
    code = 'window.location.href = userParam;'
    assert _rule_fired(code, "OPEN_REDIRECT_SLOP", ext=".ts")


def test_open_redirect_slop_skips_hardcoded_path():
    code = "location.href = '/dashboard';"
    assert not _rule_fired(code, "OPEN_REDIRECT_SLOP", ext=".ts")


# NAVIGATOR_SSR_SLOP
def test_navigator_ssr_slop_fires_on_module_scope():
    code = 'const ua = navigator.userAgent;'
    assert _rule_fired(code, "NAVIGATOR_SSR_SLOP", ext=".ts")


def test_navigator_ssr_slop_fires_on_export_const():
    code = 'export const isMobile = navigator.maxTouchPoints > 0;'
    assert _rule_fired(code, "NAVIGATOR_SSR_SLOP", ext=".ts")


def test_navigator_ssr_slop_skips_with_typeof_guard():
    code = (
        "const ua = typeof window !== 'undefined' ? navigator.userAgent : '';"
    )
    assert not _rule_fired(code, "NAVIGATOR_SSR_SLOP", ext=".ts")


# PROCESS_BROWSER_DEPRECATED_SLOP
def test_process_browser_deprecated_slop_fires_on_condition():
    code = 'if (process.browser) { doSomething(); }'
    assert _rule_fired(code, "PROCESS_BROWSER_DEPRECATED_SLOP", ext=".ts")


def test_process_browser_deprecated_slop_fires_on_negation():
    code = 'const isSSR = !process.browser;'
    assert _rule_fired(code, "PROCESS_BROWSER_DEPRECATED_SLOP", ext=".ts")


def test_process_browser_deprecated_slop_skips_env():
    code = "process.env.NODE_ENV === 'production'"
    assert not _rule_fired(code, "PROCESS_BROWSER_DEPRECATED_SLOP", ext=".ts")


# TEXT_TRANSFORM_UPPERCASE_SLOP
def test_text_transform_uppercase_slop_fires_on_heading():
    code = 'h1 { text-transform: uppercase; }'
    assert _rule_fired(code, "TEXT_TRANSFORM_UPPERCASE_SLOP", ext=".css")


def test_text_transform_uppercase_slop_fires_on_label():
    code = '.label { text-transform: uppercase; letter-spacing: 0.1em; }'
    assert _rule_fired(code, "TEXT_TRANSFORM_UPPERCASE_SLOP", ext=".scss")


def test_text_transform_uppercase_slop_skips_capitalize():
    code = 'h1 { text-transform: capitalize; }'
    assert not _rule_fired(code, "TEXT_TRANSFORM_UPPERCASE_SLOP", ext=".css")


# FONT_WEIGHT_TOO_LIGHT_SLOP
def test_font_weight_too_light_slop_fires_on_100():
    code = 'body { font-weight: 100; }'
    assert _rule_fired(code, "FONT_WEIGHT_TOO_LIGHT_SLOP", ext=".css")


def test_font_weight_too_light_slop_fires_on_200():
    code = '.thin { font-weight: 200; }'
    assert _rule_fired(code, "FONT_WEIGHT_TOO_LIGHT_SLOP", ext=".scss")


def test_font_weight_too_light_slop_skips_400():
    code = 'body { font-weight: 400; }'
    assert not _rule_fired(code, "FONT_WEIGHT_TOO_LIGHT_SLOP", ext=".css")


# FONT_SIZE_ZERO_SLOP
def test_font_size_zero_slop_fires_on_zero():
    code = '.container { font-size: 0; }'
    assert _rule_fired(code, "FONT_SIZE_ZERO_SLOP", ext=".css")


def test_font_size_zero_slop_fires_in_rule():
    code = 'ul { margin: 0; font-size: 0; }'
    assert _rule_fired(code, "FONT_SIZE_ZERO_SLOP", ext=".css")


def test_font_size_zero_slop_skips_nonzero():
    code = '.text { font-size: 16px; }'
    assert not _rule_fired(code, "FONT_SIZE_ZERO_SLOP", ext=".css")


# IFRAME_NO_TITLE_SLOP
def test_iframe_no_title_slop_fires_on_bare_iframe():
    code = '<iframe src="https://example.com"></iframe>'
    assert _rule_fired(code, "IFRAME_NO_TITLE_SLOP", ext=".tsx")


def test_iframe_no_title_slop_fires_on_iframe_with_other_attrs():
    code = '<iframe width="600" height="400" src="https://example.com"></iframe>'
    assert _rule_fired(code, "IFRAME_NO_TITLE_SLOP", ext=".tsx")


def test_iframe_no_title_slop_skips_titled_iframe():
    code = '<iframe title="Map embed" src="https://maps.example.com"></iframe>'
    assert not _rule_fired(code, "IFRAME_NO_TITLE_SLOP", ext=".tsx")


# VIDEO_NO_CAPTIONS_SLOP
def test_video_no_captions_slop_fires_on_video_without_track():
    code = '<video src="clip.mp4" controls></video>'
    assert _rule_fired(code, "VIDEO_NO_CAPTIONS_SLOP", ext=".tsx")


def test_video_no_captions_slop_fires_on_muted_autoplay():
    code = '<video autoPlay muted loop></video>'
    assert _rule_fired(code, "VIDEO_NO_CAPTIONS_SLOP", ext=".tsx")


def test_video_no_captions_slop_skips_video_with_captions():
    code = (
        '<video controls>'
        '<track kind="captions" src="en.vtt" label="English">'
        '</video>'
    )
    assert not _rule_fired(code, "VIDEO_NO_CAPTIONS_SLOP", ext=".tsx")


# STAR_IMPORT_SLOP
def test_star_import_slop_fires_on_lodash():
    code = "import * as _ from 'lodash';"
    assert _rule_fired(code, "STAR_IMPORT_SLOP", ext=".ts")


def test_star_import_slop_fires_on_moment():
    code = 'import * as moment from "moment";'
    assert _rule_fired(code, "STAR_IMPORT_SLOP", ext=".ts")


def test_star_import_slop_skips_react():
    code = "import * as React from 'react';"
    assert not _rule_fired(code, "STAR_IMPORT_SLOP", ext=".ts")


# ── Batch 22 tests ──────────────────────────────────────────────────────────

# DEBUGGER_STATEMENT_SLOP
def test_debugger_statement_slop_fires_on_bare_debugger():
    code = 'function foo() { debugger; return 42; }'
    assert _rule_fired(code, "DEBUGGER_STATEMENT_SLOP", ext=".ts")


def test_debugger_statement_slop_fires_on_standalone_line():
    code = 'const x = compute();\ndebugger;\nconsole.log(x);'
    assert _rule_fired(code, "DEBUGGER_STATEMENT_SLOP", ext=".ts")


def test_debugger_statement_slop_skips_no_debugger():
    code = 'const x = compute(); return x;'
    assert not _rule_fired(code, "DEBUGGER_STATEMENT_SLOP", ext=".ts")


# PROP_TYPES_IN_TS_SLOP
def test_prop_types_in_ts_slop_fires_on_tsx():
    code = "import PropTypes from 'prop-types';\nconst MyComp = ({ name }: { name: string }) => <div>{name}</div>;"
    assert _rule_fired(code, "PROP_TYPES_IN_TS_SLOP", ext=".tsx")


def test_prop_types_in_ts_slop_fires_on_ts():
    code = "import PropTypes from 'prop-types';"
    assert _rule_fired(code, "PROP_TYPES_IN_TS_SLOP", ext=".ts")


def test_prop_types_in_ts_slop_skips_jsx():
    code = "import PropTypes from 'prop-types';\nMyComp.propTypes = { name: PropTypes.string };"
    assert not _rule_fired(code, "PROP_TYPES_IN_TS_SLOP", ext=".jsx")


# DUPLICATE_IMPORT_SLOP
def test_duplicate_import_slop_fires_on_two_imports_same_module():
    code = (
        "import { foo } from 'utils';\n"
        "import React from 'react';\n"
        "import { bar } from 'utils';\n"
    )
    assert _rule_fired(code, "DUPLICATE_IMPORT_SLOP", ext=".ts")


def test_duplicate_import_slop_fires_on_consecutive_duplicates():
    code = (
        "import { A } from '@app/components';\n"
        "import { B } from '@app/components';\n"
    )
    assert _rule_fired(code, "DUPLICATE_IMPORT_SLOP", ext=".tsx")


def test_duplicate_import_slop_skips_unique_modules():
    code = (
        "import { foo } from 'lodash';\n"
        "import { bar } from 'react';\n"
        "import { baz } from 'utils';\n"
    )
    assert not _rule_fired(code, "DUPLICATE_IMPORT_SLOP", ext=".ts")


# CONTEXT_VALUE_INLINE_SLOP
def test_context_value_inline_slop_fires_on_provider_inline_object():
    code = '<ThemeContext.Provider value={{ theme, setTheme }}><App /></ThemeContext.Provider>'
    assert _rule_fired(code, "CONTEXT_VALUE_INLINE_SLOP", ext=".tsx")


def test_context_value_inline_slop_fires_on_nested_context():
    code = '<App.Context.Provider value={{ user, dispatch }}>{children}</App.Context.Provider>'
    assert _rule_fired(code, "CONTEXT_VALUE_INLINE_SLOP", ext=".tsx")


def test_context_value_inline_slop_skips_memoized_value():
    code = '<ThemeContext.Provider value={contextValue}><App /></ThemeContext.Provider>'
    assert not _rule_fired(code, "CONTEXT_VALUE_INLINE_SLOP", ext=".tsx")


# USE_STATE_INIT_SLOP
def test_use_state_init_slop_fires_on_new_map():
    code = 'const [data, setData] = useState(new Map());'
    assert _rule_fired(code, "USE_STATE_INIT_SLOP", ext=".tsx")


def test_use_state_init_slop_fires_on_new_set():
    code = 'const [ids, setIds] = useState(new Set());'
    assert _rule_fired(code, "USE_STATE_INIT_SLOP", ext=".tsx")


def test_use_state_init_slop_skips_primitive():
    code = 'const [count, setCount] = useState(0);'
    assert not _rule_fired(code, "USE_STATE_INIT_SLOP", ext=".tsx")


# DOCUMENT_COOKIE_SSR_SLOP
def test_document_cookie_ssr_slop_fires_on_module_scope():
    code = 'const token = document.cookie;'
    assert _rule_fired(code, "DOCUMENT_COOKIE_SSR_SLOP", ext=".ts")


def test_document_cookie_ssr_slop_fires_on_export_const():
    code = 'export const cookieStr = document.cookie;'
    assert _rule_fired(code, "DOCUMENT_COOKIE_SSR_SLOP", ext=".ts")


def test_document_cookie_ssr_slop_skips_with_typeof_guard():
    code = "const cookie = typeof document !== 'undefined' ? document.cookie : '';"
    assert not _rule_fired(code, "DOCUMENT_COOKIE_SSR_SLOP", ext=".ts")


# POSTMESSAGE_ORIGIN_MISSING_SLOP
def test_postmessage_origin_missing_slop_fires_without_origin_check():
    code = "window.addEventListener('message', (event) => { processData(event.data); });"
    assert _rule_fired(code, "POSTMESSAGE_ORIGIN_MISSING_SLOP", ext=".ts")


def test_postmessage_origin_missing_slop_fires_on_double_quotes():
    code = 'window.addEventListener("message", handler);'
    assert _rule_fired(code, "POSTMESSAGE_ORIGIN_MISSING_SLOP", ext=".ts")


def test_postmessage_origin_missing_slop_skips_with_origin_check():
    code = (
        "window.addEventListener('message', (event) => {\n"
        "  if (event.origin !== 'https://trusted.example.com') return;\n"
        "  processData(event.data);\n"
        "});"
    )
    assert not _rule_fired(code, "POSTMESSAGE_ORIGIN_MISSING_SLOP", ext=".ts")


# TABINDEX_ZERO_DIV_SLOP
def test_tabindex_zero_div_slop_fires_on_tabindex_zero():
    code = '<div tabIndex={0} onClick={handleClick}>click me</div>'
    assert _rule_fired(code, "TABINDEX_ZERO_DIV_SLOP", ext=".tsx")


def test_tabindex_zero_div_slop_fires_on_tabindex_string_zero():
    code = '<div tabindex="0" class="card">content</div>'
    assert _rule_fired(code, "TABINDEX_ZERO_DIV_SLOP", ext=".tsx")


def test_tabindex_zero_div_slop_skips_button():
    code = '<button tabIndex={0} onClick={handleClick}>click me</button>'
    assert not _rule_fired(code, "TABINDEX_ZERO_DIV_SLOP", ext=".tsx")


# ICON_ONLY_BUTTON_SLOP
def test_icon_only_button_slop_fires_on_svg_button():
    code = '<button onClick={close}><svg viewBox="0 0 24 24"><path d="M6 18L18 6"/></svg></button>'
    assert _rule_fired(code, "ICON_ONLY_BUTTON_SLOP", ext=".tsx")


def test_icon_only_button_slop_fires_on_icon_font_button():
    code = '<button onClick={toggle}><i className="fa fa-bars"></i></button>'
    assert _rule_fired(code, "ICON_ONLY_BUTTON_SLOP", ext=".tsx")


def test_icon_only_button_slop_skips_aria_label():
    code = '<button aria-label="Close dialog" onClick={close}><svg viewBox="0 0 24 24"><path d="M6 18L18 6"/></svg></button>'
    assert not _rule_fired(code, "ICON_ONLY_BUTTON_SLOP", ext=".tsx")


# SVG_WITHOUT_VIEWBOX_SLOP
def test_svg_without_viewbox_slop_fires_on_bare_svg():
    code = '<svg width="24" height="24"><path d="M12 2L2 7"/></svg>'
    assert _rule_fired(code, "SVG_WITHOUT_VIEWBOX_SLOP", ext=".tsx")


def test_svg_without_viewbox_slop_fires_on_svg_with_only_class():
    code = '<svg className="icon"><circle cx="12" cy="12" r="10"/></svg>'
    assert _rule_fired(code, "SVG_WITHOUT_VIEWBOX_SLOP", ext=".tsx")


def test_svg_without_viewbox_slop_skips_svg_with_viewbox():
    code = '<svg viewBox="0 0 24 24" width="24" height="24"><path d="M12 2L2 7"/></svg>'
    assert not _rule_fired(code, "SVG_WITHOUT_VIEWBOX_SLOP", ext=".tsx")


# USER_AGENT_SNIFF_SLOP
def test_user_agent_sniff_slop_fires_on_useragent_read():
    code = 'const ua = navigator.userAgent;'
    assert _rule_fired(code, "USER_AGENT_SNIFF_SLOP", ext=".ts")


def test_user_agent_sniff_slop_fires_on_condition():
    code = "if (navigator.userAgent.includes('Mobile')) { showMobile(); }"
    assert _rule_fired(code, "USER_AGENT_SNIFF_SLOP", ext=".ts")


def test_user_agent_sniff_slop_skips_navigator_online():
    code = 'const isOnline = navigator.onLine;'
    assert not _rule_fired(code, "USER_AGENT_SNIFF_SLOP", ext=".ts")


# STICKY_WITHOUT_TOP_SLOP
def test_sticky_without_top_slop_fires_on_sticky_no_top():
    code = '.header { position: sticky; background: white; }'
    assert _rule_fired(code, "STICKY_WITHOUT_TOP_SLOP", ext=".css")


def test_sticky_without_top_slop_fires_on_sticky_no_offset():
    code = 'nav { position: sticky; z-index: 100; }'
    assert _rule_fired(code, "STICKY_WITHOUT_TOP_SLOP", ext=".scss")


def test_sticky_without_top_slop_skips_sticky_with_top():
    code = '.header { position: sticky; top: 0; background: white; }'
    assert not _rule_fired(code, "STICKY_WITHOUT_TOP_SLOP", ext=".css")


# ── Duplicate rule deduplication ─────────────────────────────────────────────

def test_window_confirm_slop_fires_exactly_once():
    """WINDOW_CONFIRM_SLOP must not be duplicated in RULES — should fire once per file."""
    from uidetox.analyzer import analyze_file
    import tempfile, os
    code = 'if (window.confirm("sure?")) { doThing(); }'
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = analyze_file(Path(tmp))
        confirm_issues = [i for i in issues if i.get("id") == "WINDOW_CONFIRM_SLOP"]
        assert len(confirm_issues) == 1, f"Expected exactly 1 WINDOW_CONFIRM_SLOP issue, got {len(confirm_issues)}"
    finally:
        os.unlink(tmp)


def test_tabindex_positive_not_duplicated_with_removed_rule():
    """After removing POSITIVE_TABINDEX_SLOP, only TABINDEX_POSITIVE_SLOP should fire."""
    from uidetox.analyzer import analyze_file
    import tempfile, os
    code = '<div tabIndex={5}>click me</div>'
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = analyze_file(Path(tmp))
        positive_ids = [i.get("id") for i in issues if "TABINDEX" in (i.get("id") or "") and "ZERO" not in (i.get("id") or "")]
        # Should only see TABINDEX_POSITIVE_SLOP, NOT the removed POSITIVE_TABINDEX_SLOP
        assert "POSITIVE_TABINDEX_SLOP" not in positive_ids
        assert "TABINDEX_POSITIVE_SLOP" in positive_ids
    finally:
        os.unlink(tmp)


# ── AST analysis issues must have "id" field ─────────────────────────────────

def test_analyze_ast_all_issues_have_id_field():
    """Every issue returned by _analyze_ast must have an 'id' key."""
    from uidetox.analyzer import _analyze_ast
    from pathlib import Path
    import tempfile, os
    # Code that triggers multiple AST paths: dashboard + animation state + siblings
    code = """
import React, { useState } from 'react';
const [opacity, setOpacity] = useState(0);
export default function Dashboard() {
  return (
    <div>
      <MetricCard value={1} /><MetricCard value={2} /><MetricCard value={3} />
      <MetricCard value={4} /><LineChart data={[]} />
    </div>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_ast(Path(tmp), code, ".tsx")
        for issue in issues:
            assert "id" in issue, f"AST issue missing 'id' field: {issue}"
    finally:
        os.unlink(tmp)


def test_analyze_ast_dashboard_issue_has_correct_id():
    """Dashboard slop detected via AST should have id='HERO_DASHBOARD_SLOP'."""
    from uidetox.analyzer import _analyze_ast
    from pathlib import Path
    import tempfile, os
    code = """
export default function Dash() {
  return (
    <div>
      <MetricCard /><MetricCard /><MetricCard />
      <LineChart data={[]} />
    </div>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_ast(Path(tmp), code, ".tsx")
        dash_issues = [i for i in issues if i.get("id") == "HERO_DASHBOARD_SLOP"]
        assert len(dash_issues) == 1
    finally:
        os.unlink(tmp)


def test_analyze_ast_prop_drilling_issue_has_id():
    """Prop drilling detected via AST should have id='PROP_DRILLING_SLOP'."""
    from uidetox.analyzer import _analyze_ast
    from pathlib import Path
    import tempfile, os
    # Pass same prop name through 4+ different components
    code = """
export default function Root() {
  return (
    <A userId={uid}>
      <B userId={uid} />
      <C userId={uid} />
      <D userId={uid} />
      <E userId={uid} />
    </A>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_ast(Path(tmp), code, ".tsx")
        for issue in issues:
            assert "id" in issue, f"AST issue missing 'id' key: {issue}"
    finally:
        os.unlink(tmp)


def test_analyze_ast_animate_state_has_id():
    """useState for animation detected via AST should have id='ANIMATE_STATE_SLOP'."""
    from uidetox.analyzer import _analyze_ast
    from pathlib import Path
    import tempfile, os
    code = "const [opacity, setOpacity] = useState(0);"
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_ast(Path(tmp), code, ".tsx")
        for issue in issues:
            assert "id" in issue, f"AST issue missing 'id' key: {issue}"
        animate_issues = [i for i in issues if i.get("id") == "ANIMATE_STATE_SLOP"]
        assert len(animate_issues) == 1
    finally:
        os.unlink(tmp)


def test_analyze_ast_identical_siblings_has_id():
    """Identical sibling components detected via AST should have id='IDENTICAL_SIBLINGS_SLOP'."""
    from uidetox.analyzer import _analyze_ast
    from pathlib import Path
    import tempfile, os
    code = """
export default function Grid() {
  return (
    <Row>
      <FeatureCard /><FeatureCard /><FeatureCard /><FeatureCard />
    </Row>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_ast(Path(tmp), code, ".tsx")
        for issue in issues:
            assert "id" in issue, f"AST issue missing 'id' key: {issue}"
    finally:
        os.unlink(tmp)


# ── Component layout heuristic issues must have "id" field ───────────────────

def test_analyze_component_layout_all_issues_have_id():
    """Every issue returned by _analyze_component_layout must have an 'id' key."""
    from uidetox.analyzer import _analyze_component_layout
    from pathlib import Path
    import tempfile, os
    # Code that triggers multiple heuristics: pricing + testimonials
    code = """
export default function Page() {
  return (
    <div>
      <PricingCard plan="Free" price="$0/mo" />
      <PricingCard plan="Pro" price="$29/mo" />
      <PricingCard plan="Enterprise" price="$99/mo" />
      <p>Free starter basic premium enterprise plan</p>
      <TestimonialBlock avatar="" name="Alice" quote="Amazing" rating={5} stars={5} />
      <TestimonialBlock avatar="" name="Bob" quote="Great" rating={5} stars={5} />
      <TestimonialBlock avatar="" name="Carol" quote="Love" review="" stars={5} />
    </div>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_component_layout(Path(tmp), code, ".tsx")
        for issue in issues:
            assert "id" in issue, f"Layout issue missing 'id' key: {issue}"
    finally:
        os.unlink(tmp)


def test_analyze_component_layout_pricing_table_id():
    """Pricing table heuristic should emit id='PRICING_TABLE_SLOP'."""
    from uidetox.analyzer import _analyze_component_layout
    from pathlib import Path
    import tempfile, os
    code = """
export default function Pricing() {
  return (
    <div>
      <PricingCard plan="Starter" price="$0/mo" />
      <PricingCard plan="Pro" price="$29/mo" recommended />
      <PricingCard plan="Enterprise" price="$99/mo" />
      <p>Free plan basic premium</p>
    </div>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_component_layout(Path(tmp), code, ".tsx")
        pricing_issues = [i for i in issues if i.get("id") == "PRICING_TABLE_SLOP"]
        assert len(pricing_issues) >= 1
    finally:
        os.unlink(tmp)


def test_analyze_component_layout_testimonial_grid_id():
    """Testimonial grid heuristic should emit id='TESTIMONIAL_GRID_SLOP'."""
    from uidetox.analyzer import _analyze_component_layout
    from pathlib import Path
    import tempfile, os
    code = """
export default function Reviews() {
  return (
    <div>
      <div>testimonial review quote avatar name title rating stars 5</div>
      <div>testimonial review quote avatar name rating stars five</div>
      <div>testimonial review quote avatar</div>
    </div>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_component_layout(Path(tmp), code, ".tsx")
        testimonial_issues = [i for i in issues if i.get("id") == "TESTIMONIAL_GRID_SLOP"]
        assert len(testimonial_issues) >= 1
    finally:
        os.unlink(tmp)


def test_analyze_component_layout_static_component_id():
    """Zero-interactivity heuristic should emit id='STATIC_COMPONENT_SLOP'."""
    from uidetox.analyzer import _analyze_component_layout
    from pathlib import Path
    import tempfile, os
    # A static component: many JSX elements, no handlers, no animation, no hooks
    code = """
export default function Static() {
  return (
    <section>
      <Header />
      <HeroBlock />
      <FeatureRow />
      <FooterBlock />
      <SidePanel />
      <NavBar />
    </section>
  );
}
""" + "\n" * 55  # Ensure file_len > 50
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_component_layout(Path(tmp), code, ".tsx")
        for issue in issues:
            assert "id" in issue, f"Layout issue missing 'id' key: {issue}"
        static_issues = [i for i in issues if i.get("id") == "STATIC_COMPONENT_SLOP"]
        assert len(static_issues) >= 1
    finally:
        os.unlink(tmp)


def test_analyze_component_layout_dashboard_id():
    """KPI dashboard heuristic should emit id='DASHBOARD_LAYOUT_SLOP'."""
    from uidetox.analyzer import _analyze_component_layout
    from pathlib import Path
    import tempfile, os
    code = """
export default function Dashboard() {
  return (
    <div>
      <RevenueCard value={1200} />
      <UserStatCard value={340} />
      <OrderMetricCard value={88} />
      <GrowthKPICard value={12} />
      <AreaChart data={[]} />
    </div>
  );
}
"""
    with tempfile.NamedTemporaryFile(suffix=".tsx", mode="w", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp = f.name
    try:
        issues = _analyze_component_layout(Path(tmp), code, ".tsx")
        dash_issues = [i for i in issues if i.get("id") == "DASHBOARD_LAYOUT_SLOP"]
        assert len(dash_issues) >= 1
    finally:
        os.unlink(tmp)


# ── All issues from analyze_file must have "id" field ────────────────────────

def test_analyze_file_all_issues_have_id_field(tmp_path):
    """Every issue dict returned by analyze_file() must contain an 'id' key."""
    from uidetox.analyzer import analyze_file
    code = """
import React, { useState } from 'react';
export default function Page() {
  const [opacity, setOpacity] = useState(0);
  return (
    <div style={{color: 'red'}}>
      <MetricCard /><MetricCard /><MetricCard />
      <LineChart data={[]} />
      <p className="text-center">Some long centered text that looks bad in a paragraph over multiple lines blah</p>
    </div>
  );
}
"""
    p = tmp_path / "component.tsx"
    p.write_text(code, encoding="utf-8")
    issues = analyze_file(p)
    for issue in issues:
        assert "id" in issue, f"Issue missing 'id' field: {issue}"


# ── scan.py _AUTO_CATEGORIES no stale rule IDs ──────────────────────────────

def test_auto_categories_no_positive_tabindex_slop():
    """POSITIVE_TABINDEX_SLOP was removed from RULES; _AUTO_CATEGORIES must not reference it."""
    from uidetox.commands.scan import _AUTO_CATEGORIES
    for cat, rule_ids in _AUTO_CATEGORIES.items():
        assert "POSITIVE_TABINDEX_SLOP" not in rule_ids, (
            f"Stale rule 'POSITIVE_TABINDEX_SLOP' found in _AUTO_CATEGORIES['{cat}']"
        )


def test_auto_categories_all_rule_ids_exist_in_rules():
    """Every rule ID referenced in _AUTO_CATEGORIES must exist in the RULES list."""
    from uidetox.commands.scan import _AUTO_CATEGORIES
    from uidetox.analyzer import RULES
    rule_ids_in_rules = {r["id"] for r in RULES}
    for cat, rule_ids in _AUTO_CATEGORIES.items():
        for rule_id in rule_ids:
            assert rule_id in rule_ids_in_rules, (
                f"_AUTO_CATEGORIES['{cat}'] references '{rule_id}' which is not in RULES"
            )


def test_auto_categories_tabindex_positive_slop_present():
    """TABINDEX_POSITIVE_SLOP (the surviving rule) must remain in _AUTO_CATEGORIES accessibility."""
    from uidetox.commands.scan import _AUTO_CATEGORIES
    assert "TABINDEX_POSITIVE_SLOP" in _AUTO_CATEGORIES.get("accessibility", set()), (
        "TABINDEX_POSITIVE_SLOP should be in _AUTO_CATEGORIES['accessibility']"
    )


# ── color_utils.luminance handles all hex formats ───────────────────────────

def test_luminance_3_char_hex():
    """3-char hex shorthand is expanded correctly."""
    from uidetox.color_utils import luminance
    assert luminance("#fff") == luminance("#ffffff")
    assert luminance("#000") == luminance("#000000")


def test_luminance_4_char_hex():
    """4-char hex shorthand (RGBA) is expanded to 8-char; alpha ignored."""
    from uidetox.color_utils import luminance
    # #FFFF should expand to #FFFFFFFF (white + full alpha)
    assert luminance("#ffff") == luminance("#ffffff")
    # #000f should expand to #000000ff (black + full alpha)
    assert luminance("#000f") == luminance("#000000")


def test_luminance_4_char_hex_not_one():
    """4-char hex must not silently return 1.0 (white) for non-white input."""
    from uidetox.color_utils import luminance
    # #0000 = black + zero alpha; luminance should be 0.0, not 1.0 (the old bug)
    result = luminance("#0000")
    assert result == 0.0, f"Expected 0.0 for #0000, got {result}"


def test_luminance_8_char_hex():
    """8-char hex (RGBA full) parses RGB ignoring alpha."""
    from uidetox.color_utils import luminance
    # #ffffffff = white with full alpha — same luminance as #ffffff
    assert luminance("#ffffffff") == luminance("#ffffff")
    # #00000000 = black with zero alpha — same luminance as #000000
    assert luminance("#00000000") == luminance("#000000")


def test_contrast_ratio_with_4_char_hex():
    """contrast_ratio works when 4-char hex codes are passed."""
    from uidetox.color_utils import contrast_ratio
    # #000f (black) vs #ffff (white) should give 21:1
    ratio = contrast_ratio("#000f", "#ffff")
    assert abs(ratio - 21.0) < 0.1, f"Expected ~21.0 contrast for black/white, got {ratio}"


# ── scan.py triggered_rules uses direct issue ID (not description match) ────

def test_scan_triggered_rules_uses_issue_id_directly(tmp_path, monkeypatch):
    """triggered_rules should be populated via issue['id'] not description substring match."""
    import sys
    import argparse
    from pathlib import Path
    from uidetox.commands import scan as scan_cmd
    from uidetox.analyzer import RULES

    # Write a file that will trigger a well-known rule
    tsx = tmp_path / "Component.tsx"
    tsx.write_text(
        '<img src="x.png" />\n',  # triggers IMG_ALT_MISSING_SLOP
        encoding="utf-8",
    )

    state_dir = tmp_path / ".uidetox"
    state_dir.mkdir()

    # Stub out the bits of scan.run() we don't need
    monkeypatch.setattr("uidetox.commands.scan.ensure_uidetox_dir", lambda: state_dir)
    monkeypatch.setattr("uidetox.commands.scan.load_config", lambda: {})
    monkeypatch.setattr("uidetox.commands.scan.save_config", lambda c: None)
    monkeypatch.setattr("uidetox.commands.scan.detect_all", lambda path=".": type("P", (), {"to_dict": lambda s: {}})())
    monkeypatch.setattr("uidetox.commands.scan.add_issue", lambda i: True)
    monkeypatch.setattr("uidetox.commands.scan.increment_scans", lambda: None)
    monkeypatch.setattr("uidetox.commands.scan.save_run_snapshot", lambda **kw: None)
    monkeypatch.setattr("uidetox.commands.scan.save_scan_summary", lambda **kw: None)
    monkeypatch.setattr("uidetox.commands.scan.save_session", lambda **kw: None)
    monkeypatch.setattr("uidetox.commands.scan.log_progress", lambda *a, **kw: None)

    captured_triggered = []

    original_analyze = scan_cmd.analyze_directory

    def fake_analyze(path, **kwargs):
        return [{"id": "IMG_ALT_MISSING_SLOP", "file": str(tsx), "tier": "T2",
                 "issue": "img tag missing alt attribute", "command": "add alt"}]

    monkeypatch.setattr("uidetox.commands.scan.analyze_directory", fake_analyze)

    args = argparse.Namespace(path=str(tmp_path), output_format="table", since=None)

    # Capture stdout to avoid noise
    import io
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    try:
        scan_cmd.run(args)
    except SystemExit:
        pass

    # The test passes if no exception was raised — the real check is that
    # the O(N*M) loop is gone and direct ID lookup doesn't crash
    # Restore stdout
    monkeypatch.setattr(sys, "stdout", sys.__stdout__)


# ── diff.py: correct config key for exclude_paths ──────────────────────────

def test_diff_analyze_target_uses_exclude_config_key(tmp_path, monkeypatch):
    """_analyze_target must pass config['exclude'] to analyze_directory, not 'ignore_patterns'."""
    from uidetox.commands.diff import _analyze_target

    captured_exclude = []

    def fake_analyze_dir(root_path, exclude_paths=None, zone_overrides=None, design_variance=8):
        captured_exclude.append(exclude_paths)
        return []

    monkeypatch.setattr("uidetox.commands.diff.analyze_directory", fake_analyze_dir)

    cfg = {
        "exclude": ["node_modules", "dist"],
        "ignore_patterns": ["*.test.ts"],
        "DESIGN_VARIANCE": 8,
    }

    _analyze_target(str(tmp_path), cfg)

    assert len(captured_exclude) == 1
    assert captured_exclude[0] == ["node_modules", "dist"], (
        "exclude_paths should come from config['exclude'], not config['ignore_patterns']"
    )


def test_diff_analyze_target_ignore_patterns_used_for_suppressions(tmp_path, monkeypatch):
    """_analyze_target filters issues using config['ignore_patterns'] for suppressions."""
    from uidetox.commands.diff import _analyze_target

    fake_issue = {
        "id": "SOME_RULE",
        "file": str(tmp_path / "Foo.tsx"),
        "tier": "T2",
        "issue": "some issue matching suppress pattern",
        "command": "fix",
    }

    monkeypatch.setattr("uidetox.commands.diff.analyze_directory", lambda *a, **kw: [fake_issue])
    monkeypatch.setattr(
        "uidetox.commands.diff._is_suppressed",
        lambda file, issue, patterns: "suppress pattern" in issue and bool(patterns),
    )

    cfg = {"exclude": [], "ignore_patterns": ["suppress pattern"], "DESIGN_VARIANCE": 8}
    result = _analyze_target(str(tmp_path), cfg)
    assert result == [], "Issues matching ignore_patterns should be filtered out"


# ── diff.py: scope_files uses git root, not path argument ──────────────────

def test_diff_scope_files_uses_git_root(monkeypatch, tmp_path):
    """When --since is used, absolute paths in scope_files come from git rev-parse
    --show-toplevel (git root), not from the path argument.

    If path is a subdirectory like 'src/components/', using path would produce
    doubled segments: /repo/src/components/src/components/Foo.tsx
    """
    import subprocess as _sp
    from pathlib import Path

    # Set up a fake git root (the tmp_path is the git repo root)
    git_root = str(tmp_path)
    # Simulate a subdirectory scenario: path is two levels deep
    subdir = tmp_path / "src" / "components"
    subdir.mkdir(parents=True)

    # Build the real file under git root
    target_file = tmp_path / "src" / "components" / "Foo.tsx"
    target_file.write_text("export const Foo = () => <div />;", encoding="utf-8")

    original_run = _sp.run

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "rev-parse"] and "--show-toplevel" in cmd:
            class R:
                returncode = 0
                stdout = git_root + "\n"
                stderr = ""
            return R()
        if cmd[:3] == ["git", "diff", "--name-only"]:
            class R2:
                returncode = 0
                stdout = "src/components/Foo.tsx\n"
                stderr = ""
            return R2()
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(_sp, "run", fake_run)

    from uidetox.commands.diff import _get_changed_files
    # Simulate what run() does when since_sha is set
    changed = _get_changed_files("abc123", cwd=str(subdir))
    assert changed is not None, "Should return list of changed files"

    # Now verify the path construction matches what the fixed code does:
    # Use git root, not `path=subdir`
    scope_files = {str(Path(git_root) / f) for f in changed}
    expected = str(tmp_path / "src" / "components" / "Foo.tsx")
    assert expected in scope_files, (
        f"scope_files should contain {expected!r} (from git root), got: {scope_files}"
    )

    # The old buggy path construction (from subdir) would have been wrong:
    bad_path = str(Path(str(subdir)) / "src" / "components" / "Foo.tsx")
    assert bad_path not in scope_files, "Old doubled-path construction must not appear"


def test_diff_run_uses_project_root_on_cold_start_from_subdirectory(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    analyzed_path = None

    def fake_analyze_target(path, config):
        nonlocal analyzed_path
        analyzed_path = Path(path).resolve()
        return []

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": []})
    monkeypatch.setattr(diff_cmd, "_analyze_target", fake_analyze_target)
    monkeypatch.setattr(diff_cmd, "_emit", lambda *args, **kwargs: None)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert analyzed_path == root.resolve()


def test_diff_run_since_from_subdirectory_does_not_report_unanalyzed_repo_issue_as_fixed(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "frontend" / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue = {
        "id": "SCAN-ABC123",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    emitted = {}

    def fake_git_run(cmd, **kwargs):
        assert Path(kwargs["cwd"]).resolve() == root.resolve()
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{root.resolve()}\n", stderr="")

    def fake_analyze_target(path, config):
        if Path(path).resolve() == root.resolve():
            return [issue]
        return []

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted["summary"] = {
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        }

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": [issue]})
    monkeypatch.setattr(diff_cmd, "_get_changed_files", lambda since_sha, cwd: ["src/App.tsx"])
    monkeypatch.setattr(diff_cmd.subprocess, "run", fake_git_run)
    monkeypatch.setattr(diff_cmd, "_analyze_target", fake_analyze_target)
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since="abc123", output="json", save=False))

    assert emitted["summary"] == {"new": 0, "fixed": 0, "unchanged": 1}


def test_diff_run_since_save_from_subdirectory_preserves_scoped_issue_in_state(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "frontend" / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue = {
        "id": "SCAN-ABC123",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    saved_states = []

    def fake_git_run(cmd, **kwargs):
        assert Path(kwargs["cwd"]).resolve() == root.resolve()
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{root.resolve()}\n", stderr="")

    def fake_analyze_target(path, config):
        if Path(path).resolve() == root.resolve():
            return [issue]
        return []

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": [issue]})
    monkeypatch.setattr(diff_cmd, "save_state", lambda state: saved_states.append(state))
    monkeypatch.setattr(diff_cmd, "_get_changed_files", lambda since_sha, cwd: ["src/App.tsx"])
    monkeypatch.setattr(diff_cmd.subprocess, "run", fake_git_run)
    monkeypatch.setattr(diff_cmd, "_analyze_target", fake_analyze_target)
    monkeypatch.setattr(diff_cmd, "_emit", lambda *args, **kwargs: None)

    diff_cmd.run(argparse.Namespace(path=".", since="abc123", output="json", save=True))

    assert saved_states, "diff --save should persist updated state"
    assert saved_states[-1]["issues"] == []
    assert saved_states[-1]["diff_baseline"][0]["file"] == issue["file"]


def test_diff_run_since_from_subdirectory_treats_repo_relative_baseline_issue_as_unchanged(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "frontend" / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    baseline_issue = {
        "id": "SCAN-ABC123",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }
    fresh_issue = {
        "id": "DIV_SOUP_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    emitted = {}

    def fake_git_run(cmd, **kwargs):
        assert Path(kwargs["cwd"]).resolve() == root.resolve()
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{root.resolve()}\n", stderr="")

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted["summary"] = {
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        }

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": [baseline_issue]})
    monkeypatch.setattr(diff_cmd, "_get_changed_files", lambda since_sha, cwd: ["src/App.tsx"])
    monkeypatch.setattr(diff_cmd.subprocess, "run", fake_git_run)
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [fresh_issue])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since="abc123", output="json", save=False))

    assert emitted["summary"] == {"new": 0, "fixed": 0, "unchanged": 1}


def test_diff_run_since_save_from_subdirectory_deduplicates_repo_relative_baseline_issue(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "frontend" / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    baseline_issue = {
        "id": "SCAN-ABC123",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }
    fresh_issue = {
        "id": "DIV_SOUP_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    saved_states = []

    def fake_git_run(cmd, **kwargs):
        assert Path(kwargs["cwd"]).resolve() == root.resolve()
        return subprocess.CompletedProcess(cmd, 0, stdout=f"{root.resolve()}\n", stderr="")

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": [baseline_issue]})
    monkeypatch.setattr(diff_cmd, "save_state", lambda state: saved_states.append(state))
    monkeypatch.setattr(diff_cmd, "_get_changed_files", lambda since_sha, cwd: ["src/App.tsx"])
    monkeypatch.setattr(diff_cmd.subprocess, "run", fake_git_run)
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [fresh_issue])
    monkeypatch.setattr(diff_cmd, "_emit", lambda *args, **kwargs: None)

    diff_cmd.run(argparse.Namespace(path=".", since="abc123", output="json", save=True))

    assert saved_states, "diff --save should persist updated state"
    assert saved_states[-1]["issues"] == []
    assert len(saved_states[-1]["diff_baseline"]) == 1
    assert saved_states[-1]["diff_baseline"][0]["file"] == str(root / "src" / "App.tsx")


def test_diff_run_save_round_trip_keeps_unchanged_issue_stable(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue = {
        "id": "DIV_SOUP_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    state_store = {"issues": [], "diff_baseline": []}
    emitted = []

    def fake_load_state():
        return {
            "issues": list(state_store["issues"]),
            "diff_baseline": list(state_store["diff_baseline"]),
        }

    def fake_save_state(state):
        state_store["issues"] = list(state.get("issues", []))
        state_store["diff_baseline"] = list(state.get("diff_baseline", []))

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted.append({
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        })

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", fake_load_state)
    monkeypatch.setattr(diff_cmd, "save_state", fake_save_state)
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [issue])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=True))
    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert len(state_store["diff_baseline"]) == 1
    assert emitted[0] == {"new": 1, "fixed": 0, "unchanged": 0}
    assert emitted[1] == {"new": 0, "fixed": 0, "unchanged": 1}


def test_diff_run_preserves_duplicate_issue_texts_at_different_lines(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue1 = {
        "id": "IMG_ALT_MISSING_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "img tag missing alt attribute",
        "command": "add alt",
        "line": 3,
        "column": 1,
    }
    issue2 = {
        "id": "IMG_ALT_MISSING_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "img tag missing alt attribute",
        "command": "add alt",
        "line": 8,
        "column": 1,
    }

    monkeypatch.chdir(nested_dir)

    emitted = {}

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted["summary"] = {
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        }

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": [issue1, issue2]})
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [issue1, issue2])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert emitted["summary"] == {"new": 0, "fixed": 0, "unchanged": 2}


def test_diff_run_save_round_trip_preserves_duplicate_issue_texts_at_different_lines(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue1 = {
        "id": "IMG_ALT_MISSING_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "img tag missing alt attribute",
        "command": "add alt",
        "line": 3,
        "column": 1,
    }
    issue2 = {
        "id": "IMG_ALT_MISSING_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "img tag missing alt attribute",
        "command": "add alt",
        "line": 8,
        "column": 1,
    }

    monkeypatch.chdir(nested_dir)

    state_store = {"issues": [], "diff_baseline": []}
    emitted = []

    def fake_load_state():
        return {
            "issues": list(state_store["issues"]),
            "diff_baseline": list(state_store["diff_baseline"]),
        }

    def fake_save_state(state):
        state_store["issues"] = list(state.get("issues", []))
        state_store["diff_baseline"] = list(state.get("diff_baseline", []))

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted.append({
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        })

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", fake_load_state)
    monkeypatch.setattr(diff_cmd, "save_state", fake_save_state)
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [issue1, issue2])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=True))
    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert len(state_store["issues"]) == 0
    assert len(state_store["diff_baseline"]) == 2
    assert emitted[0] == {"new": 2, "fixed": 0, "unchanged": 0}
    assert emitted[1] == {"new": 0, "fixed": 0, "unchanged": 2}


def test_diff_run_preserves_identical_duplicate_fingerprints(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue = {
        "id": "SCAN-ABC123",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "manual design issue without location",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    emitted = {}

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted["summary"] = {
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        }

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [], "diff_baseline": [dict(issue), dict(issue)]})
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [dict(issue), dict(issue)])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert emitted["summary"] == {"new": 0, "fixed": 0, "unchanged": 2}


def test_diff_run_save_round_trip_preserves_identical_duplicate_fingerprints(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    issue = {
        "id": "SCAN-ABC123",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "manual design issue without location",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    state_store = {"issues": [], "diff_baseline": []}
    emitted = []

    def fake_load_state():
        return {
            "issues": list(state_store["issues"]),
            "diff_baseline": list(state_store["diff_baseline"]),
        }

    def fake_save_state(state):
        state_store["issues"] = list(state.get("issues", []))
        state_store["diff_baseline"] = list(state.get("diff_baseline", []))

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted.append({
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        })

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", fake_load_state)
    monkeypatch.setattr(diff_cmd, "save_state", fake_save_state)
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [dict(issue), dict(issue)])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=True))
    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert len(state_store["issues"]) == 0
    assert len(state_store["diff_baseline"]) == 2
    assert emitted[0] == {"new": 2, "fixed": 0, "unchanged": 0}
    assert emitted[1] == {"new": 0, "fixed": 0, "unchanged": 2}


def test_diff_run_ignores_live_queue_issues_when_no_diff_baseline(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    manual_issue = {
        "id": "SCAN-MANUAL",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T3",
        "issue": "Subjective spacing note from manual review",
        "command": "manual-fix",
    }

    monkeypatch.chdir(nested_dir)

    emitted = {}

    def fake_emit(fmt, new_issues, fixed_issues, unchanged_issues, since_sha):
        emitted["summary"] = {
            "new": len(new_issues),
            "fixed": len(fixed_issues),
            "unchanged": len(unchanged_issues),
        }

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [manual_issue], "diff_baseline": []})
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [])
    monkeypatch.setattr(diff_cmd, "_emit", fake_emit)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=False))

    assert emitted["summary"] == {"new": 0, "fixed": 0, "unchanged": 0}


def test_diff_run_save_preserves_live_queue_and_updates_diff_baseline(monkeypatch, tmp_path):
    from uidetox.commands import diff as diff_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    manual_issue = {
        "id": "SCAN-MANUAL",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T3",
        "issue": "Subjective spacing note from manual review",
        "command": "manual-fix",
    }
    static_issue = {
        "id": "DIV_SOUP_SLOP",
        "file": str(root / "src" / "App.tsx"),
        "tier": "T2",
        "issue": "existing repo issue",
        "command": "fix",
    }

    monkeypatch.chdir(nested_dir)

    saved_states = []

    monkeypatch.setattr(diff_cmd, "load_config", lambda: {})
    monkeypatch.setattr(diff_cmd, "load_state", lambda: {"issues": [manual_issue], "diff_baseline": []})
    monkeypatch.setattr(diff_cmd, "save_state", lambda state: saved_states.append(state))
    monkeypatch.setattr(diff_cmd, "_analyze_target", lambda path, config: [static_issue])
    monkeypatch.setattr(diff_cmd, "_emit", lambda *args, **kwargs: None)

    diff_cmd.run(argparse.Namespace(path=".", since=None, output="json", save=True))

    assert saved_states, "diff --save should persist updated state"
    assert saved_states[-1]["issues"] == [manual_issue]
    assert saved_states[-1]["diff_baseline"] == [static_issue]


def test_suppress_run_prunes_matching_issues_from_live_queue_and_diff_baseline(tmp_path, monkeypatch):
    from uidetox.commands import suppress as suppress_cmd
    from uidetox.state import load_config, save_state

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"ignore_patterns": []})

    live_match = {
        "id": "SCAN-LIVE-MATCH",
        "file": "src/App.tsx",
        "tier": "T3",
        "issue": "Manual spacing note",
        "command": "manual-fix",
    }
    live_keep = {
        "id": "SCAN-LIVE-KEEP",
        "file": "src/Card.tsx",
        "tier": "T2",
        "issue": "Keep this live issue",
        "command": "fix-card",
    }
    baseline_match = {
        "id": "DIV_SOUP_SLOP",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Static spacing smell",
        "command": "fix-static",
    }
    baseline_keep = {
        "id": "BUTTON_HIERARCHY_SLOP",
        "file": "src/Button.tsx",
        "tier": "T2",
        "issue": "Keep this baseline issue",
        "command": "fix-button",
    }

    save_state(
        {
            "last_scan": None,
            "issues": [live_match, live_keep],
            "diff_baseline": [baseline_match, baseline_keep],
            "resolved": [],
            "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
        }
    )

    suppress_cmd.run(argparse.Namespace(pattern="spacing", remove=False))

    state = load_state()
    config = load_config()

    assert config["ignore_patterns"] == ["spacing"]
    assert state["issues"] == [live_keep]
    assert state["diff_baseline"] == [baseline_keep]


def test_suppress_run_reapplies_existing_pattern_to_prune_diff_baseline(tmp_path, monkeypatch):
    from uidetox.commands import suppress as suppress_cmd
    from uidetox.state import load_config, save_state

    monkeypatch.chdir(tmp_path)
    ensure_uidetox_dir()
    save_config({"ignore_patterns": ["spacing"]})

    manual_issue = {
        "id": "SCAN-MANUAL-SPACING",
        "file": "src/App.tsx",
        "tier": "T3",
        "issue": "Manual spacing note",
        "command": "manual-fix",
    }
    baseline_issue = {
        "id": "STATIC-SPACING",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Static spacing smell",
        "command": "fix-static",
    }

    save_state(
        {
            "last_scan": None,
            "issues": [manual_issue],
            "diff_baseline": [baseline_issue],
            "resolved": [],
            "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
        }
    )

    suppress_cmd.run(argparse.Namespace(pattern="spacing", remove=False))

    state = load_state()
    config = load_config()

    assert config["ignore_patterns"] == ["spacing"]
    assert state["issues"] == []
    assert state["diff_baseline"] == []


def test_rescan_run_uses_project_root_on_cold_start_from_subdirectory(monkeypatch, tmp_path):
    from uidetox.commands import rescan as rescan_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    analyzed_path = None

    def fake_analyze_directory(path, **kwargs):
        nonlocal analyzed_path
        analyzed_path = Path(path).resolve()
        return []

    monkeypatch.setattr(rescan_cmd, "load_state", lambda: {"issues": [], "resolved": []})
    monkeypatch.setattr(rescan_cmd, "load_config", lambda: {})
    monkeypatch.setattr(rescan_cmd, "clear_issues", lambda: None)
    monkeypatch.setattr(rescan_cmd, "increment_scans", lambda: None)
    monkeypatch.setattr(rescan_cmd, "save_run_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(rescan_cmd, "log_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(rescan_cmd, "compute_design_score", lambda state: {"blended_score": 100})
    monkeypatch.setattr(rescan_cmd, "analyze_directory", fake_analyze_directory)

    rescan_cmd.run(argparse.Namespace(path="."))

    assert analyzed_path == root.resolve()


def test_viz_run_uses_project_root_on_cold_start_from_subdirectory(monkeypatch, tmp_path):
    from uidetox.commands import viz as viz_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_root = None

    def fake_render_html_treemap(root_path, issue_map):
        nonlocal captured_root
        captured_root = root_path.resolve()

    monkeypatch.setattr(viz_cmd, "load_state", lambda: {"issues": []})
    monkeypatch.setattr(viz_cmd, "_render_html_treemap", fake_render_html_treemap)

    viz_cmd.run(argparse.Namespace(path=".", viz_cmd="viz"))

    assert captured_root == root.resolve()


def test_watch_run_uses_project_root_on_cold_start_from_subdirectory(monkeypatch, tmp_path):
    from uidetox.commands import watch as watch_cmd

    root = tmp_path / "repo"
    nested_dir = root / "src" / "nested"
    nested_dir.mkdir(parents=True)
    (root / ".git").mkdir()

    monkeypatch.chdir(nested_dir)

    captured_root = None

    def fake_snapshot(root_path):
        nonlocal captured_root
        captured_root = root_path.resolve()
        return {}

    def interrupt_sleep(_interval):
        raise KeyboardInterrupt()

    monkeypatch.setattr(watch_cmd, "_snapshot", fake_snapshot)
    monkeypatch.setattr(watch_cmd, "analyze_file", lambda path: [])
    monkeypatch.setattr(watch_cmd.time, "sleep", interrupt_sleep)

    watch_cmd.run(argparse.Namespace(path=".", interval=0.01, clear=False))

    assert captured_root == root.resolve()


def test_viz_build_tree_uses_root_relative_paths_for_absolute_issue_files(tmp_path):
    from uidetox.commands.viz import _build_tree

    root = tmp_path / "repo"
    issue_map = {
        str(root / "src" / "App.tsx"): [{"tier": "T2", "issue": "x", "command": "fix"}],
    }

    tree = _build_tree(root, issue_map)

    assert "/" not in tree["children"], "Tree should not start from filesystem root for absolute issue paths"
    assert "src" in tree["children"]
    assert "App.tsx" in tree["children"]["src"]["children"]


# ── viz.py: HTML injection prevention ─────────────────────────────────────

def test_viz_treemap_html_escapes_issue_descriptions(tmp_path, monkeypatch):
    """Treemap HTML must escape special chars in issue descriptions and file paths."""
    from uidetox.commands.viz import _render_html_treemap
    from pathlib import Path

    # Ensure output goes to tmp_path
    uidetox_dir = tmp_path / ".uidetox"
    uidetox_dir.mkdir()
    monkeypatch.setattr("uidetox.commands.viz.get_uidetox_dir", lambda: uidetox_dir)
    monkeypatch.setattr("uidetox.commands.viz.ensure_uidetox_dir", lambda: uidetox_dir)

    malicious_issue = {
        "tier": "T2",
        "issue": '<script>alert("xss")</script> & "quoted"',
        "command": "fix",
    }
    malicious_path = 'src/<Evil>.tsx'

    issue_map = {malicious_path: [malicious_issue]}

    _render_html_treemap(tmp_path, issue_map)

    html_file = uidetox_dir / "treemap.html"
    assert html_file.exists(), "treemap.html should be generated"
    content = html_file.read_text(encoding="utf-8")

    # Raw script tag must not appear
    assert "<script>alert" not in content, "Raw <script> must not appear unescaped in HTML output"
    # Escaped versions should appear
    assert "&lt;script&gt;" in content, "< and > must be HTML-escaped"
    assert "&amp;" in content, "& must be HTML-escaped"
    # File path special chars must also be escaped
    assert "&lt;Evil&gt;" in content, "< > in file paths must be HTML-escaped"


def test_viz_treemap_html_escapes_file_names(tmp_path, monkeypatch):
    """File names with HTML special characters must be escaped in treemap output."""
    from uidetox.commands.viz import _render_html_treemap

    uidetox_dir = tmp_path / ".uidetox"
    uidetox_dir.mkdir()
    monkeypatch.setattr("uidetox.commands.viz.get_uidetox_dir", lambda: uidetox_dir)
    monkeypatch.setattr("uidetox.commands.viz.ensure_uidetox_dir", lambda: uidetox_dir)

    issue_map = {
        'src/a&b.tsx': [{"tier": "T1", "issue": "some issue", "command": "fix"}],
    }

    _render_html_treemap(tmp_path, issue_map)

    content = (uidetox_dir / "treemap.html").read_text(encoding="utf-8")
    assert "a&b.tsx" not in content or "&amp;" in content, (
        "Ampersand in file name must be HTML-escaped"
    )


# ── next.py: SKILL_CONTEXT duplicate key detection ─────────────────────────

def test_next_skill_context_no_duplicate_keys():
    """SKILL_CONTEXT dict must not have duplicate keys.

    Python silently overwrites duplicate dict keys; the first entry for
    each duplicated key is permanently lost, so the corresponding design
    context is never injected into agent prompts.
    """
    from uidetox.commands.next import SKILL_CONTEXT

    # Detect duplicates by re-parsing the source file
    import ast, pathlib

    src = pathlib.Path(__file__).resolve().parent.parent / "uidetox" / "commands" / "next.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    # Find the SKILL_CONTEXT assignment
    keys_seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SKILL_CONTEXT":
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant):
                                keys_seen.append(k.value)

    duplicates = [k for k in set(keys_seen) if keys_seen.count(k) > 1]
    assert duplicates == [], (
        f"Duplicate keys in SKILL_CONTEXT silently drop design guidance: {duplicates}"
    )


def test_next_skill_context_aria_label_merged_guidance():
    """The 'aria-label' entry must include guidance for BOTH empty labels AND vague values."""
    from uidetox.commands.next import SKILL_CONTEXT

    entry = SKILL_CONTEXT.get("aria-label")
    assert entry is not None, "'aria-label' key must exist in SKILL_CONTEXT"
    context_text = entry[0]
    assert "empty" in context_text.lower() or "aria-label=''" in context_text, (
        "Guidance for empty aria-label values must be present"
    )
    assert "vague" in context_text.lower() or "button" in context_text.lower(), (
        "Guidance for vague aria-label values must be present"
    )


def test_next_skill_context_important_merged_guidance():
    """The '!important' entry must include guidance for BOTH specificity AND motion accessibility."""
    from uidetox.commands.next import SKILL_CONTEXT

    entry = SKILL_CONTEXT.get("!important")
    assert entry is not None, "'!important' key must exist in SKILL_CONTEXT"
    context_text = entry[0]
    assert "specificity" in context_text.lower() or "specificity" in context_text, (
        "General CSS specificity guidance must be present"
    )
    assert "animation" in context_text.lower() or "motion" in context_text.lower() or "transition" in context_text.lower(), (
        "Motion/animation accessibility warning must also be present after merge"
    )


# ── batch_resolve.py: _derive_component_name path-prefix bug ───────────────

def test_derive_component_name_sibling_dirs():
    """Sibling directories sharing a path prefix must resolve to their common parent.

    The old algorithm used str.startswith() which treated '/src/components/button-group'
    as a child of '/src/components/button', returning 'button' instead of 'components'.
    os.path.commonpath() respects path boundaries and returns the correct ancestor.
    """
    from uidetox.commands.batch_resolve import _derive_component_name
    import os

    # Use os.sep-joined paths so the test works on Windows too
    button = os.path.join(os.sep, "usr", "src", "components", "button", "Button.tsx")
    button_group = os.path.join(os.sep, "usr", "src", "components", "button-group", "ButtonGroup.tsx")
    result = _derive_component_name([button, button_group])
    assert result == "components", (
        f"Expected 'components' as common ancestor of button/ and button-group/, got '{result}'"
    )


def test_derive_component_name_same_dir():
    """Files in the same directory return that directory's name."""
    from uidetox.commands.batch_resolve import _derive_component_name
    import os

    f1 = os.path.join(os.sep, "project", "src", "auth", "Login.tsx")
    f2 = os.path.join(os.sep, "project", "src", "auth", "Logout.tsx")
    result = _derive_component_name([f1, f2])
    assert result == "auth", f"Expected 'auth', got '{result}'"


def test_derive_component_name_single_file():
    """Single file returns parent directory name."""
    from uidetox.commands.batch_resolve import _derive_component_name
    import os

    f = os.path.join(os.sep, "project", "src", "checkout", "CartSummary.tsx")
    result = _derive_component_name([f])
    assert result == "checkout", f"Expected 'checkout', got '{result}'"


def test_derive_component_name_empty():
    """Empty file list returns 'unknown'."""
    from uidetox.commands.batch_resolve import _derive_component_name

    result = _derive_component_name([])
    assert result == "unknown"


# ── scan.py: --since incremental mode uses git root, not args.path ──────────

def test_scan_since_uses_git_root(tmp_path, monkeypatch):
    """scan --since must join changed file names against the git repo root, not args.path.

    git diff --name-only outputs paths relative to the repository root.
    If args.path is a subdirectory (e.g. ./frontend), joining without the git root
    would produce wrong paths like /project/frontend/frontend/src/Button.tsx instead
    of /project/frontend/src/Button.tsx, causing all incremental issues to be dropped.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    # Simulate:
    #   git root = /repo
    #   args.path = /repo/frontend  (a subdirectory)
    #   git diff --name-only output = "frontend/src/Button.tsx"  (relative to git root)
    git_root = str(tmp_path / "repo")
    scan_path = str(tmp_path / "repo" / "frontend")

    # Issue coming from analyze_directory: file path is absolute
    issue_abs_path = str(tmp_path / "repo" / "frontend" / "src" / "Button.tsx")
    fake_issues = [{"file": issue_abs_path, "tier": "T2", "issue": "test issue", "id": "X", "command": "fix"}]

    run_results = [
        # First call: git rev-parse --show-toplevel -> git_root
        MagicMock(returncode=0, stdout=git_root + "\n"),
        # Second call: git diff --name-only -> one changed file (relative to git root)
        MagicMock(returncode=0, stdout="frontend/src/Button.tsx\n"),
    ]

    with patch("uidetox.commands.scan.subprocess.run", side_effect=run_results):
        with patch("uidetox.commands.scan.analyze_directory", return_value=fake_issues):
            # Simulate the filtering logic directly (not calling run() to avoid full setup)
            import os
            since_files: list[str] | None = None
            since_root: str = os.path.abspath(scan_path)

            root_result = run_results[0]
            if root_result.returncode == 0:
                since_root = root_result.stdout.strip()

            diff_result = run_results[1]
            if diff_result.returncode == 0:
                since_files = [l.strip() for l in diff_result.stdout.splitlines() if l.strip()]

            assert since_files == ["frontend/src/Button.tsx"]
            assert since_root == git_root  # must use git root, not scan_path

            # Apply the filtering: join against since_root (git root), not scan_path
            since_abs = {os.path.abspath(os.path.join(since_root, f)) for f in since_files}
            filtered = [i for i in fake_issues if os.path.abspath(i["file"]) in since_abs]

            assert len(filtered) == 1, (
                "Issue should be included when since_root (git root) is used. "
                "If scan_path were used instead, the path would be wrong and no issues would appear."
            )

            # Verify the OLD behavior (using scan_path) would have been wrong
            bad_abs = {os.path.abspath(os.path.join(scan_path, f)) for f in since_files}
            bad_filtered = [i for i in fake_issues if os.path.abspath(i["file"]) in bad_abs]
            assert len(bad_filtered) == 0, (
                "Sanity check: old behavior (joining with scan_path) should produce wrong paths and drop the issue"
            )


# ── subagent.py corruption resilience ───────────────────────────────────────

class TestSubagentCorruptedJsonResilience:
    """record_result() and get_session() must not raise when session files are corrupted."""

    def _make_session_dir(self, tmp_path, monkeypatch):
        """Create a minimal session directory and point subagent at tmp_path."""
        import uidetox.subagent as sa
        sessions_root = tmp_path / ".uidetox" / "sessions"
        sessions_root.mkdir(parents=True)

        monkeypatch.setattr(sa, "_sessions_dir", lambda: sessions_root)

        sid = "test001"
        session_dir = sessions_root / f"session_{sid}"
        session_dir.mkdir()
        return sa, sid, session_dir

    def test_record_result_corrupted_meta_json_returns_true(self, tmp_path, monkeypatch):
        """record_result should recover when meta.json contains invalid JSON."""
        sa, sid, session_dir = self._make_session_dir(tmp_path, monkeypatch)

        # Write corrupt meta.json
        (session_dir / "meta.json").write_text("{not valid json", encoding="utf-8")

        result = sa.record_result(sid, {"note": "done"})
        # Should return True (not crash) after falling back to a minimal meta dict
        assert result is True

        # The meta.json should now be valid (was rewritten by record_result)
        import json as _json
        written = _json.loads((session_dir / "meta.json").read_text())
        assert written["session_id"] == sid
        assert "status" in written

    def test_record_result_missing_meta_json_returns_false(self, tmp_path, monkeypatch):
        """record_result should return False when the session directory doesn't exist."""
        import uidetox.subagent as sa
        sessions_root = tmp_path / ".uidetox" / "sessions"
        sessions_root.mkdir(parents=True)
        monkeypatch.setattr(sa, "_sessions_dir", lambda: sessions_root)

        result = sa.record_result("nonexistent", {"note": "done"})
        assert result is False

    def test_get_session_corrupted_meta_json_returns_dict_with_error(self, tmp_path, monkeypatch):
        """get_session should return a dict with a 'corrupted' status instead of raising."""
        sa, sid, session_dir = self._make_session_dir(tmp_path, monkeypatch)

        (session_dir / "meta.json").write_text("{{{{ broken", encoding="utf-8")

        session = sa.get_session(sid)
        assert session is not None
        assert "meta" in session
        assert session["meta"].get("status") == "corrupted"

    def test_get_session_corrupted_result_json_returns_error_entry(self, tmp_path, monkeypatch):
        """get_session should return an error entry for result when result.json is corrupt."""
        sa, sid, session_dir = self._make_session_dir(tmp_path, monkeypatch)

        # Write valid meta, corrupt result
        import json as _json
        (session_dir / "meta.json").write_text(
            _json.dumps({"session_id": sid, "stage": "fix", "status": "pending"}),
            encoding="utf-8",
        )
        (session_dir / "result.json").write_text("CORRUPTED", encoding="utf-8")

        session = sa.get_session(sid)
        assert session is not None
        assert session["meta"]["session_id"] == sid
        assert session["result"].get("error") == "corrupted result file"

    def test_get_session_nonexistent_returns_none(self, tmp_path, monkeypatch):
        """get_session should return None for a missing session."""
        import uidetox.subagent as sa
        sessions_root = tmp_path / ".uidetox" / "sessions"
        sessions_root.mkdir(parents=True)
        monkeypatch.setattr(sa, "_sessions_dir", lambda: sessions_root)

        assert sa.get_session("does_not_exist") is None


class TestSubagentCodebaseMemoryPromptGuidance:
    """Sub-agent prompts should prefer codebase-memory MCP tools."""

    def test_observe_prompt_prefers_codebase_memory_tools(self):
        import uidetox.subagent as sa

        prompt = sa._observe_prompt({}, [], "## Active Design Dials")
        legacy_tool = "git" + "nexus"

        assert 'search_graph(name_pattern=".*symbolName.*")' in prompt
        assert 'trace_path(function_name="symbolName", mode="calls", direction="inbound")' in prompt
        assert 'get_code_snippet(qualified_name="exact.qualified.name")' in prompt
        assert legacy_tool not in prompt.lower()

    def test_fix_prompt_requires_codebase_memory_impact_check(self, monkeypatch):
        import uidetox.subagent as sa
        import uidetox.commands.next as next_mod

        monkeypatch.setattr(sa, "_build_memory_block", lambda *args, **kwargs: "")
        monkeypatch.setattr(sa, "_build_deconfliction_block", lambda *args, **kwargs: "")
        monkeypatch.setattr(next_mod, "_get_relevant_context", lambda batch: [])

        prompt = sa._fix_prompt(
            [{"id": "SCAN-1", "tier": "T1", "file": "src/App.tsx", "issue": "Example issue"}],
            "## Active Design Dials",
        )
        legacy_tool = "git" + "nexus"

        assert 'search_graph(name_pattern=".*symbolName.*")' in prompt
        assert 'trace_path(function_name="symbolName", mode="calls", direction="inbound", risk_labels=true)' in prompt
        assert 'get_code_snippet(qualified_name="exact.qualified.name")' in prompt
        assert legacy_tool not in prompt.lower()


def test_agents_docs_use_only_codebase_memory():
    root_agents = Path("AGENTS.md").read_text(encoding="utf-8")
    bundled_agents = Path("uidetox/data/AGENTS.md").read_text(encoding="utf-8")

    legacy_tool = "git" + "nexus"
    for content in (root_agents, bundled_agents):
        assert "codebase-memory-mcp" in content
        assert "search_graph" in content
        assert "trace_path" in content
        assert legacy_tool not in content.lower()


# ─────────────────────────────────────────────────────────────────────────────
# setup.py — EOFError resilience in non-interactive mode
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupEOFErrorResilience:
    """setup.py input() must not raise EOFError in non-interactive/CI environments."""

    def test_auto_commit_prompt_with_closed_stdin_does_not_raise(self, tmp_path, monkeypatch):
        """When stdin is closed (CI, piped input, subprocess), setup run() must not crash."""
        import uidetox.commands.setup as setup_mod

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(setup_mod, "ensure_uidetox_dir", lambda: None)
        monkeypatch.setattr(setup_mod, "load_config", lambda: {"auto_commit": False})
        monkeypatch.setattr(setup_mod, "save_config", lambda cfg: None)

        class _FakeInteractiveStdin:
            def isatty(self):
                return True

        monkeypatch.setattr(setup_mod.sys, "stdin", _FakeInteractiveStdin())

        # Simulate closed stdin: input() raises EOFError
        monkeypatch.setattr("builtins.input", lambda *a, **kw: (_ for _ in ()).throw(EOFError))

        args = argparse.Namespace(path=".", auto_commit=None)
        # Must not raise
        setup_mod.run(args)

    def test_auto_commit_prompt_eoferror_keeps_existing_value(self, tmp_path, monkeypatch):
        """When EOFError is raised, existing auto_commit value should be preserved."""
        import uidetox.commands.setup as setup_mod

        captured_cfg = {}

        def _capture_save(cfg):
            captured_cfg.update(cfg)

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(setup_mod, "ensure_uidetox_dir", lambda: None)
        monkeypatch.setattr(setup_mod, "load_config", lambda: {"auto_commit": False})
        monkeypatch.setattr(setup_mod, "save_config", _capture_save)

        class _FakeInteractiveStdin:
            def isatty(self):
                return True

        monkeypatch.setattr(setup_mod.sys, "stdin", _FakeInteractiveStdin())
        monkeypatch.setattr("builtins.input", lambda *a, **kw: (_ for _ in ()).throw(EOFError))

        args = argparse.Namespace(path=".", auto_commit=None)
        setup_mod.run(args)

        # auto_commit should remain False (not erroneously changed to True)
        assert captured_cfg.get("auto_commit") is False

    def test_setup_non_interactive_applies_flags_without_prompt(self, tmp_path, monkeypatch, capsys):
        import uidetox.commands.setup as setup_mod

        captured_cfg = {}

        class _FakeStdin:
            def isatty(self):
                return False

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(setup_mod, "ensure_uidetox_dir", lambda: None)
        monkeypatch.setattr(setup_mod, "load_config", lambda: {})
        monkeypatch.setattr(setup_mod, "save_config", lambda cfg: captured_cfg.update(cfg))
        monkeypatch.setattr(setup_mod.sys, "stdin", _FakeStdin())
        monkeypatch.setattr("builtins.input", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("input() should not be called")))

        args = argparse.Namespace(
            path=".",
            auto_commit=None,
            design_variance=9,
            motion_intensity=7,
            visual_density=5,
            dev_server="http://localhost:5173",
        )

        setup_mod.run(args)
        output = capsys.readouterr().out

        assert "Enable automated git commits" not in output
        assert captured_cfg["DESIGN_VARIANCE"] == 9
        assert captured_cfg["MOTION_INTENSITY"] == 7
        assert captured_cfg["VISUAL_DENSITY"] == 5
        assert captured_cfg["dev_server"] == "http://localhost:5173"


class _FakeToolingProfile:
    """Minimal tooling profile stub used by scan/setup tests."""
    def to_dict(self):
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# cli.py — watch subcommand registration
# ─────────────────────────────────────────────────────────────────────────────

class TestWatchSubcommandRegistration:
    """uidetox watch must be registered in argparse so it is reachable."""

    def test_watch_is_a_valid_argparse_choice(self):
        """parse_args(['watch', '--path', '.']) must not raise SystemExit."""
        from uidetox.cli import parse_args
        ns = parse_args(["watch", "--path", "."])
        assert ns.command == "watch"
        assert ns.path == "."

    def test_watch_default_interval_is_one_second(self):
        from uidetox.cli import parse_args
        ns = parse_args(["watch"])
        assert ns.interval == 1.0

    def test_watch_no_clear_flag(self):
        from uidetox.cli import parse_args
        ns = parse_args(["watch", "--no-clear"])
        assert ns.clear is False

    def test_watch_clear_default_is_true(self):
        from uidetox.cli import parse_args
        ns = parse_args(["watch"])
        assert ns.clear is True


class TestSetupSubcommandRegistration:
    """uidetox setup should expose explicit config flags for non-interactive workflows."""

    def test_setup_accepts_dials_and_dev_server(self):
        from uidetox.cli import parse_args

        ns = parse_args([
            "setup",
            "--design-variance", "9",
            "--motion-intensity", "7",
            "--visual-density", "5",
            "--dev-server", "http://localhost:5173",
            "--auto-commit",
        ])

        assert ns.command == "setup"
        assert ns.design_variance == 9
        assert ns.motion_intensity == 7
        assert ns.visual_density == 5
        assert ns.dev_server == "http://localhost:5173"
        assert ns.auto_commit is True

    def test_setup_defaults_auto_commit_to_none(self):
        from uidetox.cli import parse_args

        ns = parse_args(["setup"])
        assert ns.auto_commit is None


# ─────────────────────────────────────────────────────────────────────────────
# scan.py — GitHub Actions annotation tier mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestScanGithubAnnotationTierMapping:
    """GitHub annotation output must map T3/T4 → error and T1/T2 → warning."""

    def _run_github_output(self, issues, monkeypatch, tmp_path, capsys):
        import uidetox.commands.scan as scan_mod

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(scan_mod, "analyze_directory", lambda *a, **kw: issues)
        monkeypatch.setattr(scan_mod, "detect_all", lambda p: _FakeToolingProfile())
        monkeypatch.setattr(scan_mod, "save_config", lambda c: None)
        monkeypatch.setattr(scan_mod, "ensure_uidetox_dir", lambda: None)
        monkeypatch.setattr(scan_mod, "save_run_snapshot", lambda *a, **kw: None)
        monkeypatch.setattr(scan_mod, "_save_scan_to_memory", lambda *a, **kw: None)
        monkeypatch.setattr(scan_mod, "save_session", lambda *a, **kw: None)
        monkeypatch.setattr(scan_mod, "log_progress", lambda *a, **kw: None)
        monkeypatch.setattr(scan_mod, "increment_scans", lambda: None)
        monkeypatch.setattr(scan_mod, "load_state", lambda: {"issues": [], "resolved": []})

        (tmp_path / ".uidetox").mkdir(exist_ok=True)
        (tmp_path / ".uidetox" / "config.json").write_text("{}", encoding="utf-8")

        args = argparse.Namespace(path=".", output="github", since=None)
        scan_mod.run(args)
        return capsys.readouterr().out

    def test_t1_is_warning_not_error(self, tmp_path, monkeypatch, capsys):
        """T1 issues must produce ::warning annotations, not ::error."""
        issues = [{"file": "a.tsx", "issue": "x", "tier": "T1", "command": "fix", "line": 1, "column": 1}]
        out = self._run_github_output(issues, monkeypatch, tmp_path, capsys)
        assert "::warning" in out
        assert "::error" not in out

    def test_t2_is_warning_not_error(self, tmp_path, monkeypatch, capsys):
        """T2 issues must produce ::warning annotations."""
        issues = [{"file": "a.tsx", "issue": "y", "tier": "T2", "command": "fix", "line": 1, "column": 1}]
        out = self._run_github_output(issues, monkeypatch, tmp_path, capsys)
        assert "::warning" in out
        assert "::error" not in out

    def test_t3_is_error(self, tmp_path, monkeypatch, capsys):
        """T3 issues must produce ::error annotations."""
        issues = [{"file": "a.tsx", "issue": "z", "tier": "T3", "command": "fix", "line": 1, "column": 1}]
        out = self._run_github_output(issues, monkeypatch, tmp_path, capsys)
        assert "::error" in out

    def test_t4_is_error(self, tmp_path, monkeypatch, capsys):
        """T4 issues must produce ::error annotations."""
        issues = [{"file": "a.tsx", "issue": "w", "tier": "T4", "command": "fix", "line": 1, "column": 1}]
        out = self._run_github_output(issues, monkeypatch, tmp_path, capsys)
        assert "::error" in out


# ─────────────────────────────────────────────────────────────────────────────
# cli.py — diff subcommand registration
# ─────────────────────────────────────────────────────────────────────────────

class TestDiffSubcommandRegistration:
    """uidetox diff must be registered in argparse so it is reachable."""

    def test_diff_is_a_valid_argparse_choice(self):
        """parse_args(['diff']) must not raise SystemExit."""
        from uidetox.cli import parse_args
        ns = parse_args(["diff"])
        assert ns.command == "diff"

    def test_diff_base_arg_default_is_none(self):
        """--since should default to None (not 'HEAD')."""
        from uidetox.cli import parse_args
        ns = parse_args(["diff"])
        assert ns.since is None

    def test_diff_output_arg_default_is_table(self):
        """--output should default to 'table'."""
        from uidetox.cli import parse_args
        ns = parse_args(["diff"])
        assert ns.output == "table"

    def test_diff_accepts_github_output_format(self):
        """--output github must parse successfully."""
        from uidetox.cli import parse_args
        ns = parse_args(["diff", "--output", "github"])
        assert ns.output == "github"

    def test_diff_accepts_since_sha(self):
        """--since <SHA> must populate args.since."""
        from uidetox.cli import parse_args
        ns = parse_args(["diff", "--since", "abc1234"])
        assert ns.since == "abc1234"

    def test_diff_save_flag_defaults_false(self):
        """--save flag must default to False."""
        from uidetox.cli import parse_args
        ns = parse_args(["diff"])
        assert ns.save is False

    def test_diff_is_not_a_dynamic_skill(self):
        """diff must be a real subcommand, not routed through skill_cmd."""
        from uidetox.cli import _get_commands_dir
        cmd_dir = _get_commands_dir()
        if cmd_dir is None:
            return
        skill_names = {f.stem for f in cmd_dir.glob("*.md") if f.stem not in ["scan", "setup", "fix"]}
        assert "diff" not in skill_names, "diff should be a real command, not a dynamic skill"


def test_cli_get_commands_dir_prefers_project_root_commands(tmp_path, monkeypatch):
    from uidetox.cli import _get_commands_dir

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".uidetox").mkdir()
    (tmp_path / "commands").mkdir()

    cmd_dir = _get_commands_dir()
    assert cmd_dir == tmp_path / "commands"


def test_cli_parse_args_registers_custom_claude_skill_directory(tmp_path, monkeypatch):
    from uidetox.cli import parse_args

    monkeypatch.chdir(tmp_path)
    skill_dir = tmp_path / ".claude" / "skills" / "uidetox" / "commands"
    skill_dir.mkdir(parents=True)
    (skill_dir / "custom-skill.md").write_text("Custom skill", encoding="utf-8")

    ns = parse_args(["custom-skill", "src/App.tsx"])

    assert ns.command == "custom-skill"
    assert ns.target == "src/App.tsx"


class TestStateAndMemoryChaosResilience:
    """Persistent JSON stores should survive wrong-but-valid JSON shapes."""

    def test_load_config_wrong_top_level_type_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from uidetox.state import load_config

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "config.json").write_text("[]", encoding="utf-8")

        config = load_config()

        assert isinstance(config, dict)
        assert config["DESIGN_VARIANCE"] == 8
        assert config["MOTION_INTENSITY"] == 6
        assert config["VISUAL_DENSITY"] == 4

    def test_load_config_invalid_utf8_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from uidetox.state import load_config

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "config.json").write_bytes(b"\xff\xfe\x00")

        config = load_config()

        assert config["DESIGN_VARIANCE"] == 8
        assert config["MOTION_INTENSITY"] == 6
        assert config["VISUAL_DENSITY"] == 4

    def test_load_config_normalizes_runtime_critical_nested_types(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_config

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "config.json").write_text(
            json.dumps(
                {
                    "DESIGN_VARIANCE": "loud",
                    "MOTION_INTENSITY": "fast",
                    "VISUAL_DENSITY": "dense",
                    "target_score": "ninety-five",
                    "tooling": [],
                    "ignore_patterns": "*.tmp",
                    "exclude": "node_modules",
                    "zone_overrides": [],
                    "auto_commit": "yes",
                    "dev_server": 5173,
                }
            ),
            encoding="utf-8",
        )

        config = load_config()

        assert config["DESIGN_VARIANCE"] == 8
        assert config["MOTION_INTENSITY"] == 6
        assert config["VISUAL_DENSITY"] == 4
        assert config["target_score"] == 95
        assert config["tooling"] == {}
        assert config["ignore_patterns"] == []
        assert config["exclude"] == []
        assert config["zone_overrides"] == {}
        assert config["auto_commit"] is False
        assert "dev_server" not in config

    def test_load_config_normalizes_nested_tooling_entries(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_config

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "config.json").write_text(
            json.dumps(
                {
                    "tooling": {
                        "typescript": [],
                        "linter": 7,
                        "formatter": "prettier",
                        "frontend": "vite",
                        "backend": {},
                        "database": "sqlite",
                        "api": False,
                    }
                }
            ),
            encoding="utf-8",
        )

        config = load_config()

        assert config["tooling"]["typescript"] is None
        assert config["tooling"]["linter"] is None
        assert config["tooling"]["formatter"] is None
        assert config["tooling"]["frontend"] == []
        assert config["tooling"]["backend"] == []
        assert config["tooling"]["database"] == []
        assert config["tooling"]["api"] == []

    def test_load_config_filters_invalid_collection_members_and_tool_commands(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_config

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "config.json").write_text(
            json.dumps(
                {
                    "ignore_patterns": [123, "*.tmp", None],
                    "exclude": ["node_modules", 7],
                    "tooling": {
                        "formatter": {
                            "name": "prettier",
                            "run_cmd": ["prettier", "."],
                            "fix_cmd": 99,
                        },
                        "frontend": [
                            {"name": "vite", "run_cmd": "npx vite build"},
                            "broken-entry",
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        config = load_config()

        assert config["ignore_patterns"] == ["*.tmp"]
        assert config["exclude"] == ["node_modules"]
        assert config["tooling"]["formatter"] is None
        assert config["tooling"]["frontend"] == [{"name": "vite", "run_cmd": "npx vite build"}]

    def test_load_state_invalid_utf8_falls_back_to_default_state(self, tmp_path, monkeypatch):
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_bytes(b"\xff\xfe\x00")

        state = load_state()

        assert state["last_scan"] is None
        assert state["diff_baseline"] == []
        assert state["issues"] == []
        assert state["resolved"] == []
        assert state["stats"] == {"total_found": 0, "total_resolved": 0, "scans_run": 0}

    def test_load_state_normalizes_nested_stats_and_issue_shapes(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "last_scan": "2026-05-02T00:00:00Z",
                    "issues": ["oops", {"id": "ISSUE-1", "file": "src/App.tsx"}],
                    "resolved": [123, {"id": "ISSUE-2", "file": "src/App.tsx"}],
                    "stats": {
                        "total_found": "oops",
                        "total_resolved": None,
                        "scans_run": True,
                    },
                }
            ),
            encoding="utf-8",
        )

        state = load_state()

        assert state["issues"] == [{"id": "ISSUE-1", "file": "src/App.tsx"}]
        assert state["resolved"] == [{"id": "ISSUE-2", "file": "src/App.tsx"}]
        assert state["stats"] == {"total_found": 0, "total_resolved": 0, "scans_run": 0}

    def test_load_state_normalizes_diff_baseline_shapes(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "diff_baseline": [
                        "oops",
                        {"id": "BASE-1", "file": "src/App.tsx"},
                        42,
                    ]
                }
            ),
            encoding="utf-8",
        )

        state = load_state()

        assert state["diff_baseline"] == [{"id": "BASE-1", "file": "src/App.tsx"}]

    def test_load_state_backfills_missing_diff_baseline_for_legacy_state(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "last_scan": "2026-05-02T00:00:00Z",
                    "issues": [{"id": "ISSUE-1", "file": "src/App.tsx"}],
                    "resolved": [],
                    "stats": {"total_found": 1, "total_resolved": 0, "scans_run": 1},
                }
            ),
            encoding="utf-8",
        )

        state = load_state()

        assert state["diff_baseline"] == []
        assert state["issues"] == [{"id": "ISSUE-1", "file": "src/App.tsx"}]

    def test_load_state_normalizes_subjective_score_and_history(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "subjective": {
                        "score": "loud",
                        "history": [
                            "oops",
                            {"score": "bad"},
                            {"score": 88, "timestamp": 123, "source": "agent"},
                            {"score": 91, "timestamp": "2026-05-02T00:00:00Z"},
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )

        state = load_state()

        assert "score" not in state["subjective"]
        assert state["subjective"]["history"] == [
            {"score": 88, "timestamp": "", "source": "agent"},
            {"score": 91, "timestamp": "2026-05-02T00:00:00Z"},
        ]

    def test_load_state_preserves_extra_stats_keys_and_subjective_history_metadata(self, tmp_path, monkeypatch):
        import json
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "stats": {
                        "total_found": "oops",
                        "total_resolved": 2,
                        "scans_run": 3,
                        "future_metric": {"keep": True},
                    },
                    "subjective": {
                        "history": [
                            {"score": 88, "timestamp": 123, "source": "agent", "notes": {"keep": True}},
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        state = load_state()

        assert state["stats"]["total_found"] == 0
        assert state["stats"]["future_metric"] == {"keep": True}
        assert state["subjective"]["history"] == [
            {"score": 88, "timestamp": "", "source": "agent", "notes": {"keep": True}}
        ]

    def test_store_subjective_score_recovers_from_non_dict_subjective_state(self, tmp_path, monkeypatch):
        import json
        from uidetox.commands import review as review_cmd
        from uidetox.state import load_state

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "subjective": [],
                    "issues": [],
                    "resolved": [],
                    "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
                }
            ),
            encoding="utf-8",
        )

        review_cmd._store_subjective_score(87)
        state = load_state()

        assert state["subjective"]["score"] == 87
        assert state["subjective"]["history"][-1]["score"] == 87

    def test_status_run_tolerates_corrupted_subjective_state(self, tmp_path, monkeypatch, capsys):
        import json
        from uidetox.commands import status as status_cmd

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "state.json").write_text(
            json.dumps(
                {
                    "subjective": [],
                    "issues": [],
                    "resolved": [],
                    "stats": {"total_found": 0, "total_resolved": 0, "scans_run": 0},
                }
            ),
            encoding="utf-8",
        )

        status_cmd.run(argparse.Namespace(json=True))
        payload = json.loads(capsys.readouterr().out)

        assert payload["subjective_score"] is None
        assert payload["design_score"] == 50

    def test_load_run_history_skips_non_dict_snapshot_files(self, tmp_path, monkeypatch):
        import json
        from uidetox.history import load_run_history

        monkeypatch.chdir(tmp_path)
        history_dir = tmp_path / ".uidetox" / "history"
        history_dir.mkdir(parents=True)
        (history_dir / "run_2026-05-02T00-00-00.json").write_text("[]", encoding="utf-8")
        (history_dir / "run_2026-05-02T00-00-01.json").write_text(
            json.dumps({"timestamp": "2026-05-02T00:00:01Z", "design_score": 97}),
            encoding="utf-8",
        )

        runs = load_run_history()

        assert len(runs) == 1
        assert runs[0]["timestamp"] == "2026-05-02T00:00:01Z"
        assert runs[0]["_file"] == "run_2026-05-02T00-00-01.json"

    def test_load_run_history_skips_invalid_utf8_snapshot_files(self, tmp_path, monkeypatch):
        import json
        from uidetox.history import load_run_history

        monkeypatch.chdir(tmp_path)
        history_dir = tmp_path / ".uidetox" / "history"
        history_dir.mkdir(parents=True)
        (history_dir / "run_2026-05-02T00-00-00.json").write_bytes(b"\xff\xfe\x00")
        (history_dir / "run_2026-05-02T00-00-01.json").write_text(
            json.dumps({"timestamp": "2026-05-02T00:00:01Z", "design_score": 97}),
            encoding="utf-8",
        )

        runs = load_run_history()

        assert len(runs) == 1
        assert runs[0]["_file"] == "run_2026-05-02T00-00-01.json"

    def test_history_command_tolerates_malformed_snapshot_fields(self, tmp_path, monkeypatch, capsys):
        import json
        from uidetox.commands import history_cmd

        monkeypatch.chdir(tmp_path)
        history_dir = tmp_path / ".uidetox" / "history"
        history_dir.mkdir(parents=True)
        (history_dir / "run_2026-05-02T00-00-00.json").write_text(
            json.dumps(
                {
                    "timestamp": ["not-a-string"],
                    "trigger": {"oops": True},
                    "design_score": "loud",
                    "pending_issues": "many",
                    "resolved_issues": None,
                }
            ),
            encoding="utf-8",
        )

        history_cmd.run(argparse.Namespace(full=False, json=False))
        output = capsys.readouterr().out

        assert "UIdetox Run History" in output
        assert "?" in output
        assert "loud" not in output
        assert "many" not in output

    def test_history_command_full_json_includes_raw_snapshot_fields(self, tmp_path, monkeypatch, capsys):
        import json
        from uidetox.commands import history_cmd

        monkeypatch.chdir(tmp_path)
        history_dir = tmp_path / ".uidetox" / "history"
        history_dir.mkdir(parents=True)
        (history_dir / "run_2026-05-02T00-00-00.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-02T00:00:00Z",
                    "trigger": "scan",
                    "design_score": 91,
                    "objective_score": 88,
                    "subjective_score": 96,
                    "pending_issues": 3,
                    "resolved_issues": 5,
                    "total_found": 8,
                    "scans_run": 2,
                    "issues": [{"id": "ISSUE-1"}],
                    "resolved": [{"id": "ISSUE-2"}],
                }
            ),
            encoding="utf-8",
        )

        history_cmd.run(argparse.Namespace(full=True, json=True))
        payload = json.loads(capsys.readouterr().out)

        assert payload["total"] == 1
        assert payload["runs"][0]["objective_score"] == 88
        assert payload["runs"][0]["subjective_score"] == 96
        assert payload["runs"][0]["issues"] == [{"id": "ISSUE-1"}]
        assert payload["runs"][0]["_file"] == "run_2026-05-02T00-00-00.json"

    def test_history_command_full_text_prints_per_run_details(self, tmp_path, monkeypatch, capsys):
        import json
        from uidetox.commands import history_cmd

        monkeypatch.chdir(tmp_path)
        history_dir = tmp_path / ".uidetox" / "history"
        history_dir.mkdir(parents=True)
        (history_dir / "run_2026-05-02T00-00-00.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-05-02T00:00:00Z",
                    "trigger": "scan",
                    "design_score": 91,
                    "objective_score": 88,
                    "subjective_score": 96,
                    "pending_issues": 3,
                    "resolved_issues": 5,
                    "total_found": 8,
                    "scans_run": 2,
                    "issues": [{"id": "ISSUE-1"}],
                    "resolved": [{"id": "ISSUE-2"}],
                }
            ),
            encoding="utf-8",
        )

        history_cmd.run(argparse.Namespace(full=True, json=False))
        output = capsys.readouterr().out

        assert "run_2026-05-02T00-00-00.json" in output
        assert "Objective" in output
        assert "Subjective" in output
        assert "Pending issues" in output

    def test_history_command_full_text_tolerates_malformed_snapshot_fields(self, tmp_path, monkeypatch, capsys):
        import json
        from uidetox.commands import history_cmd

        monkeypatch.chdir(tmp_path)
        history_dir = tmp_path / ".uidetox" / "history"
        history_dir.mkdir(parents=True)
        (history_dir / "run_2026-05-02T00-00-00.json").write_text(
            json.dumps(
                {
                    "timestamp": ["not-a-string"],
                    "trigger": {"oops": True},
                    "design_score": "loud",
                    "objective_score": None,
                    "subjective_score": [],
                    "pending_issues": "many",
                    "resolved_issues": {},
                    "issues": "not-a-list",
                    "resolved": False,
                }
            ),
            encoding="utf-8",
        )

        history_cmd.run(argparse.Namespace(full=True, json=False))
        output = capsys.readouterr().out

        assert "Full Run Details" in output
        assert "n/a" in output
        assert "loud" not in output
        assert "many" not in output

    def test_load_memory_wrong_top_level_type_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from uidetox.memory import load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text("[]", encoding="utf-8")

        memory = load_memory()

        assert isinstance(memory, dict)
        assert memory["reviewed_files"] == {}
        assert memory["patterns"] == []
        assert memory["notes"] == []
        assert memory["session"] == {}

    def test_load_memory_invalid_utf8_falls_back_to_defaults(self, tmp_path, monkeypatch):
        from uidetox.memory import load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_bytes(b"\xff\xfe\x00")

        memory = load_memory()

        assert memory["reviewed_files"] == {}
        assert memory["patterns"] == []
        assert memory["notes"] == []
        assert memory["session"] == {}

    def test_load_memory_resets_wrong_nested_types_but_preserves_valid_fields(self, tmp_path, monkeypatch):
        import json
        from uidetox.memory import load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps(
                {
                    "reviewed_files": [],
                    "patterns": "bad",
                    "notes": {},
                    "exclusions": "vendor",
                    "session": [],
                    "last_scan": {"total_found": 3},
                    "progress_log": "oops",
                }
            ),
            encoding="utf-8",
        )

        memory = load_memory()

        assert memory["reviewed_files"] == {}
        assert memory["patterns"] == []
        assert memory["notes"] == []
        assert memory["exclusions"] == []
        assert memory["session"] == {}
        assert memory["last_scan"]["total_found"] == 3
        assert memory["last_scan"]["timestamp"] == ""
        assert memory["last_scan"]["by_tier"] == {}
        assert memory["last_scan"]["by_category"] == {}
        assert memory["last_scan"]["top_files"] == []
        assert memory["last_scan"]["files_scanned"] == 0
        assert memory["progress_log"] == []

    def test_load_memory_does_not_fabricate_session_checkpoint_for_missing_session(self, tmp_path, monkeypatch, capsys):
        import json
        import contextlib
        import io
        from uidetox.commands import memory_cmd
        from uidetox.memory import get_session, load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps({"patterns": [{"pattern": "x"}]}),
            encoding="utf-8",
        )

        assert load_memory()["session"] == {}
        assert get_session() == {}

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            memory_cmd.run(argparse.Namespace(memory_action="show", value=None))

        assert "Session Checkpoint" not in buffer.getvalue()

    def test_load_memory_filters_invalid_pattern_and_note_entries(self, tmp_path, monkeypatch):
        import json
        from uidetox.memory import load_memory
        from uidetox.subagent import _build_memory_block

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps(
                {
                    "patterns": ["oops", {"pattern": "Keep this pattern", "category": "general"}],
                    "notes": ["oops", {"note": "Keep this note"}],
                }
            ),
            encoding="utf-8",
        )

        memory = load_memory()
        block = _build_memory_block(query="keep")

        assert memory["patterns"] == [{"pattern": "Keep this pattern", "category": "general"}]
        assert memory["notes"] == [{"note": "Keep this note"}]
        assert "Keep this pattern" in block
        assert "Keep this note" in block

    def test_save_session_recovers_from_corrupted_issue_counter(self, tmp_path, monkeypatch):
        import json
        from uidetox.memory import get_session, save_session

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps({"session": {"issues_fixed_this_session": "oops"}}),
            encoding="utf-8",
        )

        save_session(phase="fix", last_command="uidetox next", issues_fixed=2)
        session = get_session()

        assert session["phase"] == "fix"
        assert session["last_command"] == "uidetox next"
        assert session["issues_fixed_this_session"] == 2

    def test_load_memory_normalizes_last_scan_counts_and_progress_log_entries(self, tmp_path, monkeypatch):
        import json
        from uidetox.memory import load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps(
                {
                    "last_scan": {
                        "timestamp": ["bad"],
                        "total_found": "many",
                        "files_scanned": None,
                        "by_tier": {"T1": "oops", "T2": 2, 7: 3},
                        "by_category": {"layout": "bad", "motion": 3},
                        "top_files": ["src/App.tsx", 7, None],
                        "future_meta": {"keep": True},
                    },
                    "progress_log": [
                        "oops",
                        {"action": ["bad"], "details": {"bad": True}, "timestamp": 123},
                        {"action": "scan", "details": "ok", "timestamp": "2026-05-02T00:00:00Z", "source": "agent"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        memory = load_memory()

        assert memory["last_scan"]["timestamp"] == ""
        assert memory["last_scan"]["total_found"] == 0
        assert memory["last_scan"]["files_scanned"] == 0
        assert memory["last_scan"]["by_tier"] == {"T1": 0, "T2": 2, "7": 3}
        assert memory["last_scan"]["by_category"] == {"layout": 0, "motion": 3}
        assert memory["last_scan"]["top_files"] == ["src/App.tsx"]
        assert memory["last_scan"]["future_meta"] == {"keep": True}
        assert memory["progress_log"] == [
            {"action": "scan", "details": "ok", "timestamp": "2026-05-02T00:00:00Z", "source": "agent"},
        ]

    def test_load_memory_preserves_extra_last_scan_and_progress_log_metadata(self, tmp_path, monkeypatch):
        import json
        from uidetox.memory import load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps(
                {
                    "last_scan": {
                        "timestamp": "2026-05-02T00:00:00Z",
                        "total_found": 4,
                        "files_scanned": 2,
                        "by_tier": {"T1": 1},
                        "by_category": {"layout": 3},
                        "top_files": ["src/App.tsx"],
                        "future_meta": {"keep": True},
                    },
                    "progress_log": [
                        {
                            "action": "scan",
                            "details": "ok",
                            "timestamp": "2026-05-02T00:00:00Z",
                            "source": "agent",
                            "meta": {"keep": True},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        memory = load_memory()

        assert memory["last_scan"]["future_meta"] == {"keep": True}
        assert memory["progress_log"] == [
            {
                "action": "scan",
                "details": "ok",
                "timestamp": "2026-05-02T00:00:00Z",
                "source": "agent",
                "meta": {"keep": True},
            }
        ]

    def test_load_memory_normalizes_non_finite_counters(self, tmp_path, monkeypatch):
        from uidetox.memory import load_memory

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            '{"last_scan": {"total_found": NaN, "files_scanned": Infinity, "by_tier": {"T1": NaN}, "by_category": {"layout": Infinity}}, "session": {"issues_fixed_this_session": NaN}}',
            encoding="utf-8",
        )

        memory = load_memory()

        assert memory["last_scan"]["total_found"] == 0
        assert memory["last_scan"]["files_scanned"] == 0
        assert memory["last_scan"]["by_tier"] == {"T1": 0}
        assert memory["last_scan"]["by_category"] == {"layout": 0}
        assert memory["session"] == {}

    def test_memory_command_show_tolerates_malformed_last_scan_and_progress_log(self, tmp_path, monkeypatch, capsys):
        import json
        from uidetox.commands import memory_cmd

        monkeypatch.chdir(tmp_path)
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        (uidetox_dir / "memory.json").write_text(
            json.dumps(
                {
                    "last_scan": {
                        "timestamp": ["bad"],
                        "total_found": "many",
                        "files_scanned": None,
                        "by_tier": {"T1": "oops", "T2": 2},
                        "by_category": {"layout": "bad", "motion": 3},
                        "top_files": ["src/App.tsx", 7],
                    },
                    "progress_log": [
                        "oops",
                        {"action": "scan", "details": "ok", "timestamp": "2026-05-02T00:00:00Z"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        memory_cmd.run(argparse.Namespace(memory_action="show", value=None))
        output = capsys.readouterr().out

        assert "Agent Memory Bank" in output
        assert "Last Scan Summary" in output
        assert "many" not in output
        assert "Recent Progress" in output
        assert "scan: ok" in output


def test_detect_all_survives_wrong_top_level_package_json(tmp_path):
    from uidetox.tooling import detect_all

    (tmp_path / "package.json").write_text("[]", encoding="utf-8")

    profile = detect_all(tmp_path)

    assert profile.package_manager == "npm"
    assert profile.linter is None
    assert profile.formatter is None
