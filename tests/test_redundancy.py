"""Regression tests for redundancy elimination refactoring.

Covers:
- _now_iso() wrapper removal — now_iso() used directly
- _categorize_issue/_infer_category wrapper removal — categorize_issue() used directly
- recommend_skills_for_batch wrapper removal
- now_iso_filename() utility function
- run_tool() utility function
- get_current_scores() utility function
- _run_verification -> run_verification (public API rename)
- _CATEGORIES -> _CATEGORY_GUIDANCE (guidance-only dict)
- ensure_uidetox_dir centralization in cli.main()
"""

import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch


# ── Verify _now_iso() wrappers are removed ──

class TestNowIsoWrappersRemoved:
    """Ensure no module defines a private _now_iso() wrapper anymore."""

    def test_state_no_now_iso_wrapper(self):
        source = Path("uidetox/state.py").read_text()
        assert "def _now_iso" not in source

    def test_memory_no_now_iso_wrapper(self):
        source = Path("uidetox/memory.py").read_text()
        assert "def _now_iso" not in source

    def test_subagent_no_now_iso_wrapper(self):
        source = Path("uidetox/subagent.py").read_text()
        assert "def _now_iso" not in source


# ── Verify _categorize_issue wrappers are removed ──

class TestCategorizeIssueWrappersRemoved:
    """Ensure no module defines a local _categorize_issue or _infer_category wrapper."""

    def test_autofix_no_wrapper(self):
        source = Path("uidetox/commands/autofix.py").read_text()
        assert "def _categorize_issue" not in source

    def test_plan_no_wrapper(self):
        source = Path("uidetox/commands/plan.py").read_text()
        assert "def _categorize_issue" not in source

    def test_scan_no_infer_wrapper(self):
        source = Path("uidetox/commands/scan.py").read_text()
        assert "def _infer_category" not in source


# ── Verify recommend_skills_for_batch wrapper is removed ──

class TestSkillsBatchWrapperRemoved:
    """Ensure recommend_skills_for_batch delegate is removed from skills.py."""

    def test_no_batch_wrapper(self):
        source = Path("uidetox/skills.py").read_text()
        assert "def recommend_skills_for_batch" not in source

    def test_next_uses_direct_import(self):
        source = Path("uidetox/commands/next.py").read_text()
        assert "recommend_skills_for_issues" in source
        assert "recommend_skills_for_batch" not in source


# ── New utility functions ──

class TestNowIsoFilename:
    """Test the new now_iso_filename() utility."""

    def test_format_has_no_colons(self):
        from uidetox.utils import now_iso_filename
        result = now_iso_filename()
        assert ":" not in result
        assert "T" in result  # ISO separator present
        assert "-" in result

    def test_format_is_filesystem_safe(self):
        from uidetox.utils import now_iso_filename
        result = now_iso_filename()
        # No characters that would be invalid in filenames
        bad_chars = set('/:*?"<>|')
        assert not bad_chars.intersection(result)


class TestRunTool:
    """Test the new run_tool() utility."""

    def test_returns_completed_process(self):
        from uidetox.utils import run_tool
        result = run_tool("echo hello")
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_captures_stderr(self):
        from uidetox.utils import run_tool
        result = run_tool("echo error >&2", cwd=".")
        # stderr should be captured
        assert isinstance(result.stderr, str)

    def test_raises_on_missing_command(self):
        from uidetox.utils import run_tool
        with pytest.raises(FileNotFoundError):
            run_tool("this_command_does_not_exist_12345")


class TestGetCurrentScores:
    """Test the new get_current_scores() convenience function."""

    def test_returns_state_and_scores(self, tmp_path, monkeypatch):
        import json
        uidetox_dir = tmp_path / ".uidetox"
        uidetox_dir.mkdir()
        state = {
            "issues": [{"tier": "T1"}],
            "resolved": [],
            "stats": {"scans_run": 1},
        }
        (uidetox_dir / "state.json").write_text(json.dumps(state))
        monkeypatch.setattr("uidetox.state._project_root_cache", tmp_path)

        from uidetox.utils import get_current_scores
        st, sc = get_current_scores()
        assert "issues" in st
        assert "blended_score" in sc


# ── run_verification is now public ──

class TestRunVerificationPublic:
    """Ensure _run_verification was promoted to a public name."""

    def test_importable_as_public(self):
        from uidetox.commands.batch_resolve import run_verification
        assert callable(run_verification)

    def test_resolve_uses_public_name(self):
        source = Path("uidetox/commands/resolve.py").read_text()
        assert "from uidetox.commands.batch_resolve import run_verification" in source
        assert "_run_verification" not in source


# ── _CATEGORY_GUIDANCE replaces _CATEGORIES ──

class TestCategoryGuidance:
    """Ensure _CATEGORIES was replaced with guidance-only dict."""

    def test_no_categories_dict(self):
        source = Path("uidetox/commands/autofix.py").read_text()
        assert "_CATEGORIES" not in source
        assert "_CATEGORY_GUIDANCE" in source

    def test_no_keywords_in_guidance(self):
        from uidetox.commands.autofix import _CATEGORY_GUIDANCE
        # Each value should be a string (guidance), not a dict with keywords
        for cat, val in _CATEGORY_GUIDANCE.items():
            assert isinstance(val, str), f"{cat} guidance should be a string"


# ── ensure_uidetox_dir centralized ──

class TestEnsureUidetoxDirCentralized:
    """Ensure ensure_uidetox_dir() is called once in cli.main() and removed from commands."""

    def test_cli_calls_ensure(self):
        source = Path("uidetox/cli.py").read_text()
        assert "ensure_uidetox_dir()" in source

    def test_scan_does_not_call_ensure(self):
        source = Path("uidetox/commands/scan.py").read_text()
        assert "ensure_uidetox_dir()" not in source

    def test_loop_does_not_call_ensure(self):
        source = Path("uidetox/commands/loop.py").read_text()
        assert "ensure_uidetox_dir()" not in source

    def test_setup_does_not_call_ensure(self):
        source = Path("uidetox/commands/setup.py").read_text()
        assert "ensure_uidetox_dir()" not in source


# ── history.py uses centralized timestamp functions ──

class TestHistoryTimestampCentralized:
    """Ensure history.py uses now_iso and now_iso_filename from utils."""

    def test_no_datetime_import(self):
        source = Path("uidetox/history.py").read_text()
        assert "from datetime import" not in source

    def test_no_stamp_function(self):
        source = Path("uidetox/history.py").read_text()
        assert "def _stamp" not in source

    def test_uses_now_iso_filename(self):
        source = Path("uidetox/history.py").read_text()
        assert "now_iso_filename" in source

    def test_uses_now_iso(self):
        source = Path("uidetox/history.py").read_text()
        assert "now_iso" in source
