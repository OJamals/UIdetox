"""Tests for risk-aware auto-commit policy (git_policy module)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uidetox.git_policy import (
    CommitPolicy,
    CommitResult,
    classify_modifications,
    safe_commit,
    safe_stage,
)


class TestCommitPolicy:
    def test_defaults(self):
        p = CommitPolicy()
        assert p.run_hooks is True
        assert p.abort_on_unrelated is True
        assert p.max_unrelated_files == 3
        assert p.allow_untracked is False

    def test_from_config(self):
        config = {
            "commit_policy": {
                "run_hooks": False,
                "abort_on_unrelated": False,
                "max_unrelated_files": 10,
                "allow_untracked": True,
            }
        }
        p = CommitPolicy.from_config(config)
        assert p.run_hooks is False
        assert p.abort_on_unrelated is False
        assert p.max_unrelated_files == 10
        assert p.allow_untracked is True

    def test_from_empty_config(self):
        p = CommitPolicy.from_config({})
        assert p.run_hooks is True  # defaults


class TestCommitResult:
    def test_success_result(self):
        r = CommitResult(success=True, message="test commit")
        assert r.success
        assert r.aborted_reason == ""

    def test_aborted_result(self):
        r = CommitResult(
            success=False,
            message="",
            aborted_reason="too many unrelated modifications",
        )
        assert not r.success
        assert "unrelated" in r.aborted_reason


class TestClassifyModifications:
    @patch("uidetox.git_policy.get_tracked_modified_files")
    @patch("uidetox.git_policy.get_staged_files")
    def test_separates_related_and_unrelated(self, mock_staged, mock_modified):
        mock_modified.return_value = ["src/App.tsx", "README.md", "package.json"]
        mock_staged.return_value = [".uidetox/state.json"]

        related, unrelated = classify_modifications(
            touched_files=["src/App.tsx"],
            cwd="/project",
        )
        assert "src/App.tsx" in related
        assert ".uidetox/state.json" in related  # .uidetox is always related
        assert "README.md" in unrelated
        assert "package.json" in unrelated

    @patch("uidetox.git_policy.get_tracked_modified_files")
    @patch("uidetox.git_policy.get_staged_files")
    def test_uidetox_dir_always_related(self, mock_staged, mock_modified):
        mock_modified.return_value = [".uidetox/config.json"]
        mock_staged.return_value = []

        related, unrelated = classify_modifications(
            touched_files=[],
            cwd="/project",
        )
        assert ".uidetox/config.json" in related
        assert len(unrelated) == 0


class TestSafeCommit:
    @patch("uidetox.git_policy.classify_modifications")
    @patch("uidetox.git_policy.safe_stage")
    @patch("uidetox.git_policy._git_run")
    def test_aborts_on_too_many_unrelated(self, mock_git, mock_stage, mock_classify):
        mock_classify.return_value = (
            ["src/App.tsx"],
            ["file1.txt", "file2.txt", "file3.txt", "file4.txt"],
        )
        policy = CommitPolicy(abort_on_unrelated=True, max_unrelated_files=3)
        result = safe_commit(
            touched_files=["src/App.tsx"],
            message="test",
            policy=policy,
        )
        assert not result.success
        assert "unrelated" in result.aborted_reason.lower()
        mock_stage.assert_not_called()

    @patch("uidetox.git_policy.classify_modifications")
    @patch("uidetox.git_policy.safe_stage")
    @patch("uidetox.git_policy._git_run")
    def test_successful_commit(self, mock_git, mock_stage, mock_classify):
        mock_classify.return_value = (["src/App.tsx"], [])
        mock_stage.return_value = (["src/App.tsx"], "")
        mock_git.return_value = MagicMock(returncode=0, stdout="1 file changed", stderr="")

        result = safe_commit(
            touched_files=["src/App.tsx"],
            message="fix: resolve issue",
            policy=CommitPolicy(),
        )
        assert result.success

    @patch("uidetox.git_policy.classify_modifications")
    @patch("uidetox.git_policy.safe_stage")
    @patch("uidetox.git_policy._git_run")
    def test_hook_failure_aborts(self, mock_git, mock_stage, mock_classify):
        mock_classify.return_value = (["src/App.tsx"], [])
        mock_stage.return_value = (["src/App.tsx"], "")
        mock_git.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="pre-commit hook rejected",
        )

        result = safe_commit(
            touched_files=["src/App.tsx"],
            message="fix",
            policy=CommitPolicy(run_hooks=True),
        )
        assert not result.success
        assert "hook" in result.aborted_reason.lower()

    @patch("uidetox.git_policy.classify_modifications")
    @patch("uidetox.git_policy.safe_stage")
    def test_no_files_staged(self, mock_stage, mock_classify):
        mock_classify.return_value = ([], [])
        mock_stage.return_value = ([], "No files to stage")

        result = safe_commit(
            touched_files=["nonexistent.tsx"],
            message="fix",
        )
        assert not result.success
        assert result.aborted_reason

    @patch("uidetox.git_policy.classify_modifications")
    @patch("uidetox.git_policy.safe_stage")
    @patch("uidetox.git_policy._git_run")
    def test_allows_unrelated_below_threshold(self, mock_git, mock_stage, mock_classify):
        mock_classify.return_value = (
            ["src/App.tsx"],
            ["unrelated.md"],  # only 1, threshold is 3
        )
        mock_stage.return_value = (["src/App.tsx"], "")
        mock_git.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        result = safe_commit(
            touched_files=["src/App.tsx"],
            message="fix",
            policy=CommitPolicy(abort_on_unrelated=True, max_unrelated_files=3),
        )
        assert result.success
