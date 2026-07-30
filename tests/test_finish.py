import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from uidetox.commands import finish
from uidetox.visual_evidence import VisualEvidenceStatus

_REAL_RUN = subprocess.run
_SESSION_BRANCH = "uidetox-session-test"
_COMMIT_MESSAGE = (
    "[UIdetox] Detoxing complete: Resolved issues and improved Design Score."
)


@dataclass(frozen=True)
class _Repository:
    path: Path
    target_head: str
    session_head: str


def _git(
    repository: Path,
    *arguments: str,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return _REAL_RUN(
        ["git", *arguments],
        cwd=repository,
        check=check,
        capture_output=True,
        text=True,
        input=input_text,
    )


def _create_repository(tmp_path: Path) -> _Repository:
    repository = tmp_path / "repository with ünicode"
    repository.mkdir()
    _git(repository, "init", "-b", "master")
    _git(repository, "config", "user.email", "uidetox@example.test")
    _git(repository, "config", "user.name", "UIdetox Test")

    (repository / "base.txt").write_text("base\n")
    _git(repository, "add", "base.txt")
    _git(repository, "commit", "-m", "base")
    target_head = _git(repository, "rev-parse", "HEAD").stdout.strip()

    _git(repository, "checkout", "-b", _SESSION_BRANCH)
    (repository / "base.txt").write_text("session\n")
    (repository / "feature ü.txt").write_text("feature\n")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-m", "session work")
    session_head = _git(repository, "rev-parse", "HEAD").stdout.strip()

    return _Repository(repository, target_head, session_head)


def _allow_finish(
    monkeypatch: pytest.MonkeyPatch,
    repository: _Repository,
) -> None:
    monkeypatch.chdir(repository.path)
    monkeypatch.setattr(finish, "load_config", lambda: {"target_score": 95})
    monkeypatch.setattr(finish, "load_state", lambda: {})
    monkeypatch.setattr(
        finish,
        "evaluate_eligibility",
        lambda state, context: SimpleNamespace(eligible=True, blockers=()),
    )
    monkeypatch.setattr(finish, "current_verification_fresh", lambda: True)
    monkeypatch.setattr(finish, "current_evidence_hashes", lambda: {})
    monkeypatch.setattr(
        finish,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="fresh",
            ready=True,
            required=False,
            manifest_path=repository.path / "visual-evidence.json",
        ),
    )


def _run_finish() -> None:
    finish.run(
        argparse.Namespace(
            require_visual_evidence=False,
            visual_evidence_file=None,
        )
    )


def _install_git_failure(
    monkeypatch: pytest.MonkeyPatch,
    repository: _Repository,
    stage: str | None,
) -> dict[str, object]:
    observed: dict[str, object] = {
        "advanced_session": None,
        "candidate": None,
        "advanced_target": None,
        "normal_cleanup_failed": False,
        "target_worktree": None,
        "temporary_paths": [],
        "worktree_list_count": 0,
    }

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        cwd = Path(kwargs.get("cwd") or Path.cwd()).resolve()

        if command[:4] == ["git", "worktree", "add", "--detach"]:
            temporary_paths = observed["temporary_paths"]
            assert isinstance(temporary_paths, list)
            temporary_paths.append(Path(command[4]).resolve())

        if command == ["git", "worktree", "list", "--porcelain"]:
            worktree_list_count = observed["worktree_list_count"]
            assert isinstance(worktree_list_count, int)
            worktree_list_count += 1
            observed["worktree_list_count"] = worktree_list_count
            if (
                stage == "target_worktree_post_update_window"
                and worktree_list_count == 3
            ):
                target_worktree = repository.path.parent / "post update worktree"
                _REAL_RUN(
                    ["git", "worktree", "add", str(target_worktree), "master"],
                    cwd=repository.path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                observed["target_worktree"] = target_worktree

        if command[:3] == ["git", "update-ref", "refs/heads/master"]:
            if observed["candidate"] is None:
                observed["candidate"] = command[3]
            if (
                stage == "target_worktree_update_window"
                and observed["target_worktree"] is None
            ):
                target_worktree = repository.path.parent / "update window worktree"
                _REAL_RUN(
                    ["git", "worktree", "add", str(target_worktree), "master"],
                    cwd=repository.path,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                observed["target_worktree"] = target_worktree
            if stage == "compare_and_swap":
                old_target = command[4]
                tree = _git(
                    repository.path, "rev-parse", f"{old_target}^{{tree}}"
                ).stdout.strip()
                advanced_target = _git(
                    repository.path,
                    "commit-tree",
                    tree,
                    "-p",
                    old_target,
                    input_text="external advance\n",
                ).stdout.strip()
                _git(
                    repository.path,
                    "update-ref",
                    "refs/heads/master",
                    advanced_target,
                    old_target,
                )
                observed["advanced_target"] = advanced_target

        if (
            stage == "target_worktree_race"
            and command == ["git", "rev-parse", "HEAD"]
            and cwd != repository.path.resolve()
        ):
            result = _REAL_RUN(command, **kwargs)
            target_worktree = repository.path.parent / "late target worktree"
            _REAL_RUN(
                ["git", "worktree", "add", str(target_worktree), "master"],
                cwd=repository.path,
                check=True,
                capture_output=True,
                text=True,
            )
            observed["target_worktree"] = target_worktree
            return result

        session_delete_commands = (
            ["git", "branch", "-D", _SESSION_BRANCH],
            [
                "git",
                "update-ref",
                "-d",
                f"refs/heads/{_SESSION_BRANCH}",
                repository.session_head,
            ],
        )
        if stage == "delete" and command in session_delete_commands:
            tree = _git(
                repository.path,
                "rev-parse",
                f"{repository.session_head}^{{tree}}",
            ).stdout.strip()
            advanced_session = _git(
                repository.path,
                "commit-tree",
                tree,
                "-p",
                repository.session_head,
                input_text="external session advance\n",
            ).stdout.strip()
            _git(
                repository.path,
                "update-ref",
                f"refs/heads/{_SESSION_BRANCH}",
                advanced_session,
                repository.session_head,
            )
            observed["advanced_session"] = advanced_session

        should_fail = (
            (stage == "merge" and command[:3] == ["git", "merge", "--squash"])
            or (
                stage == "commit"
                and command[:2] == ["git", "commit"]
                and cwd != repository.path.resolve()
            )
            or (
                stage == "checkout"
                and command == ["git", "checkout", "master"]
            )
        )
        if should_fail:
            raise subprocess.CalledProcessError(1, command)

        if (
            stage == "cleanup"
            and command[:3] == ["git", "worktree", "remove"]
            and "--force" not in command
        ):
            observed["normal_cleanup_failed"] = True
            raise subprocess.CalledProcessError(1, command)

        return _REAL_RUN(command, **kwargs)

    monkeypatch.setattr(finish.subprocess, "run", fake_run)
    return observed


def _current_branch(repository: _Repository) -> str:
    return _git(repository.path, "branch", "--show-current").stdout.strip()


def _ref(repository: _Repository, name: str) -> str:
    return _git(repository.path, "rev-parse", name).stdout.strip()


def _status(repository: _Repository) -> str:
    return _git(repository.path, "status", "--porcelain").stdout


def _ref_exists(repository: _Repository, name: str) -> bool:
    return (
        _git(
            repository.path,
            "show-ref",
            "--verify",
            "--quiet",
            name,
            check=False,
        ).returncode
        == 0
    )


def _assert_temporary_worktree_cleaned(
    repository: _Repository,
    observed: dict[str, object],
) -> None:
    listing = _git(repository.path, "worktree", "list", "--porcelain").stdout
    temporary_paths = observed["temporary_paths"]
    assert isinstance(temporary_paths, list)
    assert temporary_paths
    assert all(not path.exists() and str(path) not in listing for path in temporary_paths)


def test_finish_stops_before_git_mutation_when_required_evidence_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(stdout="uidetox-session-test\n")

    monkeypatch.setattr(finish.subprocess, "run", fake_run)
    monkeypatch.setattr(finish, "load_config", lambda: {})
    monkeypatch.setattr(finish, "load_state", lambda: {})
    monkeypatch.setattr(finish, "_workspace_dirty", lambda: False)
    monkeypatch.setattr(finish, "current_verification_fresh", lambda: True)
    monkeypatch.setattr(
        finish,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="stale",
            ready=False,
            required=True,
            manifest_path=tmp_path / "visual-evidence.json",
            reasons=("after source hash changed",),
        ),
    )
    monkeypatch.setattr(
        finish,
        "_detect_main_branch",
        lambda: pytest.fail("finish must stop before branch detection"),
    )

    with pytest.raises(SystemExit) as exc_info:
        finish.run(
            argparse.Namespace(
                require_visual_evidence=True,
                visual_evidence_file=None,
            )
        )

    assert exc_info.value.code == 1
    assert calls == [["git", "branch", "--show-current"]]


def test_finish_uses_canonical_pending_finding_gate_before_git_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finding = {
        "id": "manual-1",
        "file": "src/App.tsx",
        "tier": "T2",
        "issue": "Hierarchy defect",
        "command": "Fix hierarchy",
    }
    monkeypatch.setattr(
        finish.subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(stdout="uidetox-session-test\n"),
    )
    monkeypatch.setattr(finish, "load_config", lambda: {"target_score": 95})
    monkeypatch.setattr(
        finish,
        "load_state",
        lambda: {
            "issues": [finding],
            "current_snapshot": {"qualified_coverage": 1.0},
            "subjective": {},
        },
    )
    monkeypatch.setattr(finish, "_workspace_dirty", lambda: False)
    monkeypatch.setattr(finish, "current_verification_fresh", lambda: True)
    monkeypatch.setattr(
        finish,
        "project_visual_evidence_status",
        lambda *_args, **_kwargs: VisualEvidenceStatus(
            state="fresh", ready=True, required=False, manifest_path=tmp_path / "v.json"
        ),
    )
    monkeypatch.setattr(
        finish,
        "_detect_main_branch",
        lambda: pytest.fail("eligibility must block before branch mutation"),
    )
    with pytest.raises(SystemExit):
        finish.run(argparse.Namespace(require_visual_evidence=False, visual_evidence_file=None))


@pytest.mark.parametrize("stage", ["merge", "commit"])
def test_finish_prepublication_failure_leaves_original_worktree_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(monkeypatch, repository, stage)

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == repository.target_head
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_compare_and_swap_preserves_externally_advanced_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(
        monkeypatch,
        repository,
        "compare_and_swap",
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    advanced_target = observed["advanced_target"]
    assert isinstance(advanced_target, str)
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == advanced_target
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_checkout_failure_occurs_only_after_target_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(monkeypatch, repository, "checkout")

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    candidate = observed["candidate"]
    assert isinstance(candidate, str)
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == candidate
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_rejects_target_checked_out_in_another_worktree_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    target_worktree = tmp_path / "target worktree"
    _git(repository.path, "worktree", "add", str(target_worktree), "master")
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(monkeypatch, repository, None)

    assert finish._detect_main_branch() == "master"

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == repository.target_head
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _git(target_worktree, "status", "--porcelain").stdout == ""
    assert _git(target_worktree, "rev-parse", "HEAD").stdout.strip() == (
        repository.target_head
    )
    assert _status(repository) == ""
    assert observed["candidate"] is None


def test_finish_rechecks_target_worktree_ownership_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(
        monkeypatch,
        repository,
        "target_worktree_race",
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    target_worktree = observed["target_worktree"]
    assert isinstance(target_worktree, Path)
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == repository.target_head
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _git(target_worktree, "status", "--porcelain").stdout == ""
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_rolls_back_cas_when_target_is_checked_out_in_update_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(
        monkeypatch,
        repository,
        "target_worktree_update_window",
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    target_worktree = observed["target_worktree"]
    assert isinstance(target_worktree, Path)
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == repository.target_head
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _git(target_worktree, "rev-parse", "HEAD").stdout.strip() == (
        repository.target_head
    )
    assert _git(target_worktree, "status", "--porcelain").stdout == ""
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_retains_clean_target_checked_out_after_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(
        monkeypatch,
        repository,
        "target_worktree_post_update_window",
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    candidate = observed["candidate"]
    assert isinstance(candidate, str)
    target_worktree = observed["target_worktree"]
    assert isinstance(target_worktree, Path)
    assert _current_branch(repository) == _SESSION_BRANCH
    assert _ref(repository, "refs/heads/master") == candidate
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == repository.session_head
    assert _git(target_worktree, "rev-parse", "HEAD").stdout.strip() == candidate
    assert _git(target_worktree, "status", "--porcelain").stdout == ""
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_session_delete_cas_retains_concurrently_advanced_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(monkeypatch, repository, "delete")

    with pytest.raises(SystemExit) as exc_info:
        _run_finish()

    assert exc_info.value.code == 1
    candidate = observed["candidate"]
    assert isinstance(candidate, str)
    advanced_session = observed["advanced_session"]
    assert isinstance(advanced_session, str)
    assert _current_branch(repository) == "master"
    assert _ref(repository, "refs/heads/master") == candidate
    assert _ref(repository, f"refs/heads/{_SESSION_BRANCH}") == advanced_session
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_forces_cleanup_only_for_command_owned_temporary_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(monkeypatch, repository, "cleanup")

    _run_finish()

    assert observed["normal_cleanup_failed"] is True
    assert _current_branch(repository) == "master"
    assert not _ref_exists(repository, f"refs/heads/{_SESSION_BRANCH}")
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)


def test_finish_success_publishes_one_exact_squash_commit_then_deletes_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _create_repository(tmp_path)
    _allow_finish(monkeypatch, repository)
    observed = _install_git_failure(monkeypatch, repository, None)

    _run_finish()

    candidate = observed["candidate"]
    assert isinstance(candidate, str)
    assert _current_branch(repository) == "master"
    assert _ref(repository, "HEAD") == candidate
    assert _ref(repository, "HEAD^") == repository.target_head
    assert _git(
        repository.path,
        "rev-list",
        "--count",
        f"{repository.target_head}..HEAD",
    ).stdout.strip() == "1"
    assert _git(repository.path, "show", "-s", "--format=%s", "HEAD").stdout.strip() == (
        _COMMIT_MESSAGE
    )
    assert (repository.path / "base.txt").read_text() == "session\n"
    assert (repository.path / "feature ü.txt").read_text() == "feature\n"
    assert not _ref_exists(repository, f"refs/heads/{_SESSION_BRANCH}")
    assert _status(repository) == ""
    _assert_temporary_worktree_cleaned(repository, observed)
