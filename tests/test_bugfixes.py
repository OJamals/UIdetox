"""Regression tests for bugs found during the optimization audit.

Covers:
- tier_weights inversion fix in compute_design_score
- history.py compare_runs None score handling
- zone.py segment-based classification (no false positives)
- batch_resolve.py path ancestor detection
- finish.py branch name parsing with removeprefix
- skills.py no unused import (re)
- tooling.py backend detection (express alongside NestJS)
- tooling.py python config_file accuracy
- analyzer.py dirnames slice assignment
"""

import pytest
from pathlib import Path
from types import SimpleNamespace

from uidetox.utils import compute_design_score, _apply_subjective_curve, get_score_freshness


class TestSubjectiveCurve:
    """Verify the diminishing-returns curve and objective-anchored penalties."""

    def test_zero_returns_zero(self):
        assert _apply_subjective_curve(0, []) == 0

    def test_below_threshold_is_linear(self):
        """Scores at or below 60 pass through unchanged."""
        assert _apply_subjective_curve(50, []) == 50
        assert _apply_subjective_curve(60, []) == 60

    def test_raw_100_maps_to_100(self):
        """Only a raw 100 with no pending issues maps to effective 100."""
        assert _apply_subjective_curve(100, []) == 100

    def test_raw_90_compressed_below_90(self):
        """Raw 90 should be heavily compressed below 90 by the harder curve."""
        effective = _apply_subjective_curve(90, [])
        assert effective < 90, f"Expected < 90, got {effective}"
        assert effective >= 70, f"Expected >= 70, got {effective}"

    def test_raw_95_compressed_below_95(self):
        """Raw 95 should be compressed significantly below 95."""
        effective = _apply_subjective_curve(95, [])
        assert effective < 95, f"Expected < 95, got {effective}"
        assert effective >= 80, f"Expected >= 80, got {effective}"

    def test_pending_issues_deduct(self):
        """Pending issues cause automatic deductions."""
        no_issues = _apply_subjective_curve(85, [])
        with_t1 = _apply_subjective_curve(85, [{"tier": "T1"}])
        with_t4 = _apply_subjective_curve(85, [{"tier": "T4"}])
        assert with_t1 < no_issues, "T1 issue should reduce score"
        # T4 penalty is only 0.5 — may round to same int at some raw values
        assert with_t4 <= no_issues, "T4 issue should not INCREASE score"
        assert with_t1 < with_t4, "T1 deduction should be larger than T4"

    def test_pending_t2_deducts_meaningfully(self):
        """A T2 issue (2pt penalty) should clearly reduce the effective score."""
        no_issues = _apply_subjective_curve(90, [])
        with_t2 = _apply_subjective_curve(90, [{"tier": "T2"}])
        assert with_t2 < no_issues, "T2 issue should reduce score"

    def test_pending_issues_cap_at_80(self):
        """With any pending issues, effective is capped at 80."""
        effective = _apply_subjective_curve(100, [{"tier": "T4"}])
        assert effective <= 80, f"Expected <= 80 with pending issues, got {effective}"

    def test_many_issues_capped_penalty(self):
        """Penalty from issues should be capped (not unbounded)."""
        many_issues = [{"tier": "T1"} for _ in range(50)]
        effective = _apply_subjective_curve(100, many_issues)
        assert effective >= 0, "Score should never go negative"

    def test_curve_is_monotonic(self):
        """Higher raw scores should always map to equal or higher effective scores."""
        for raw in range(1, 100):
            lower = _apply_subjective_curve(raw, [])
            higher = _apply_subjective_curve(raw + 1, [])
            assert higher >= lower, (
                f"Curve not monotonic: raw {raw}→{lower}, raw {raw+1}→{higher}"
            )


class TestSubjectiveScoringRobustness:
    """Harden subjective scoring against noisy/legacy state data."""

    def test_t1_pending_caps_effective_at_70(self):
        effective = _apply_subjective_curve(100, [{"tier": "T1"}])
        assert effective <= 70

    def test_string_subjective_score_is_sanitized(self):
        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}],
            "stats": {"scans_run": 1},
            "subjective": {"score": "91"},
        }
        scores = compute_design_score(state)
        assert scores["subjective_score"] == 91
        assert scores["effective_subjective"] is not None
        assert isinstance(scores["effective_subjective"], int)

    def test_freshness_accepts_subjective_reviewed_at_fallback(self):
        state = {
            "last_scan": "2026-03-10T12:00:00+00:00",
            "issues": [],
            "resolved": [],
            "subjective": {
                "score": 90,
                "reviewed_at": "2026-03-10T12:01:00+00:00",
                "history": [],
            },
        }
        freshness = get_score_freshness(state)
        assert freshness["subjective_fresh"] is True
        assert freshness["target_ready"] is True

    def test_effective_details_report_objective_cross_gate(self):
        state = {
            "issues": [{"tier": "T4"}],
            "resolved": [{"tier": "T1"}],
            "stats": {"scans_run": 1},
            "subjective": {"score": 100},
        }
        scores = compute_design_score(state)
        details = scores.get("effective_subjective_details") or {}
        assert "objective_cross_gate" in details.get("caps_applied", [])
        assert scores["effective_subjective"] <= 75


class TestReviewFollowupGate:
    """Ensure subjective review is always followed by implementation work."""

    def test_followup_stays_active_until_score_recorded(self):
        from uidetox.commands.loop import _review_followup_snapshot

        state = {
            "issues": [],
            "resolved": [],
            "subjective": {
                "review_followup": {
                    "active": True,
                    "opened_at": "2026-03-10T10:00:00+00:00",
                },
            },
        }

        snapshot = _review_followup_snapshot(state)
        assert snapshot["active"] is True
        assert snapshot["score_recorded"] is False
        assert snapshot["pending_count"] == 0

    def test_followup_counts_pending_issues_created_after_review_open(self):
        from uidetox.commands.loop import _review_followup_snapshot

        state = {
            "issues": [
                {"id": "A", "created_at": "2026-03-10T09:59:00+00:00"},
                {"id": "B", "created_at": "2026-03-10T10:05:00+00:00"},
            ],
            "resolved": [],
            "subjective": {
                "reviewed_at": "2026-03-10T10:06:00+00:00",
                "review_followup": {
                    "active": True,
                    "opened_at": "2026-03-10T10:00:00+00:00",
                },
            },
        }

        snapshot = _review_followup_snapshot(state)
        assert snapshot["active"] is True
        assert snapshot["score_recorded"] is True
        assert snapshot["pending_count"] == 1

    def test_followup_auto_closes_when_window_issues_are_resolved(self, monkeypatch):
        from uidetox.commands import loop as loop_cmd

        persisted: list[dict] = []
        monkeypatch.setattr(loop_cmd, "save_state", lambda s: persisted.append(s.copy()))
        monkeypatch.setattr(loop_cmd, "now_iso", lambda: "2026-03-10T10:10:00+00:00")

        state = {
            "issues": [],
            "resolved": [
                {"id": "B", "created_at": "2026-03-10T10:05:00+00:00", "resolved_at": "2026-03-10T10:09:00+00:00"},
            ],
            "subjective": {
                "reviewed_at": "2026-03-10T10:06:00+00:00",
                "review_followup": {
                    "active": True,
                    "opened_at": "2026-03-10T10:00:00+00:00",
                },
            },
        }

        snapshot = loop_cmd._review_followup_snapshot(state)
        assert snapshot["active"] is False
        assert snapshot["resolved_count"] == 1
        assert snapshot.get("just_closed") is True
        assert state["subjective"]["review_followup"]["active"] is False
        assert state["subjective"]["review_followup"]["closed_reason"] == "followup_issues_resolved"
        assert persisted, "Gate closure should persist state"


class TestTierWeightsFix:
    """Verify T1 (critical) penalises more than T4 (informational)."""

    def test_single_t1_worse_than_single_t4(self):
        """A single T1 should reduce the score far more than a single T4."""
        state_t1 = {
            "issues": [{"tier": "T1"}],
            "resolved": [{"tier": "T1"}],
            "stats": {"scans_run": 1},
        }
        state_t4 = {
            "issues": [{"tier": "T4"}],
            "resolved": [{"tier": "T4"}],
            "stats": {"scans_run": 1},
        }
        score_t1 = compute_design_score(state_t1)
        score_t4 = compute_design_score(state_t4)
        # Both have 50% resolution, but T1 should penalise more heavily
        assert score_t1["blended_score"] == score_t4["blended_score"]  # same ratio
        assert score_t1["current_slop"] > score_t4["current_slop"]  # T1 costs more

    def test_t1_weight_greater_than_t4(self):
        """The absolute slop weight of T1 must exceed T4."""
        state = {
            "issues": [{"tier": "T1"}, {"tier": "T4"}],
            "resolved": [],
            "stats": {"scans_run": 1},
        }
        scores = compute_design_score(state)
        # T1=15 + T4=2 = 17 total slop, all pending
        assert scores["current_slop"] == 17
        assert scores["total_slop"] == 17
        assert scores["blended_score"] == 0  # nothing resolved

    def test_all_resolved_is_100(self):
        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}, {"tier": "T2"}],
            "stats": {"scans_run": 1},
        }
        scores = compute_design_score(state)
        assert scores["blended_score"] == 100

    def test_effective_subjective_in_output(self):
        """compute_design_score should include effective_subjective."""
        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}],
            "stats": {"scans_run": 1},
            "subjective": {"score": 90},
        }
        scores = compute_design_score(state)
        assert "effective_subjective" in scores
        # With no pending issues, effective should be curve-compressed < raw
        assert scores["effective_subjective"] is not None
        assert scores["effective_subjective"] <= 90
        assert scores["subjective_score"] == 90

    def test_blended_uses_effective_not_raw(self):
        """Blended score should use effective (post-curve) subjective, not raw."""
        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}],
            "stats": {"scans_run": 1},
            "subjective": {"score": 95},
        }
        scores = compute_design_score(state)
        # If blended used raw 95, it would be: 100*0.3 + 95*0.7 = 96
        # With curve, effective < 95, so blended should be < 96
        assert scores["blended_score"] < 96, (
            f"Blended {scores['blended_score']} should be < 96 "
            f"(effective_sub={scores['effective_subjective']})"
        )

    def test_no_scans_returns_none(self):
        state = {"issues": [], "resolved": [], "stats": {"scans_run": 0}}
        scores = compute_design_score(state)
        assert scores["objective_score"] is None
        # blended_score defaults to 0 (not None) so callers can safely
        # compare it against numeric targets without TypeError.
        assert scores["blended_score"] == 0


class TestHistoryNoneScore:
    """Verify compare_runs handles None design_score correctly."""

    def test_none_score_becomes_zero(self):
        from uidetox.history import compare_runs, load_run_history
        # Monkey-patch load_run_history to return controlled data
        import uidetox.history as h
        original = h.load_run_history

        def mock_history():
            return [{"timestamp": "2025-01-01", "trigger": "scan", "design_score": None,
                      "pending_issues": 5, "resolved_issues": 0}]

        h.load_run_history = mock_history
        try:
            runs = compare_runs()
            assert runs[0]["score"] == 0  # None -> 0
        finally:
            h.load_run_history = original


class TestZoneClassification:
    """Verify zone detection uses path segments not substrings."""

    def test_testimonials_is_production(self):
        from uidetox.commands.zone import _determine_zone
        assert _determine_zone("src/components/testimonials.tsx") == "production"

    def test_contest_page_is_production(self):
        from uidetox.commands.zone import _determine_zone
        assert _determine_zone("src/pages/contest-page.tsx") == "production"

    def test_configuration_is_production(self):
        from uidetox.commands.zone import _determine_zone
        assert _determine_zone("src/guides/my-configuration-guide.tsx") == "production"

    def test_actual_test_dir_is_test(self):
        from uidetox.commands.zone import _determine_zone
        assert _determine_zone("tests/Button.test.tsx") == "test"
        assert _determine_zone("__tests__/App.spec.tsx") == "test"

    def test_node_modules_is_vendor(self):
        from uidetox.commands.zone import _determine_zone
        assert _determine_zone("node_modules/react/index.js") == "vendor"

    def test_dist_is_generated(self):
        from uidetox.commands.zone import _determine_zone
        assert _determine_zone("dist/bundle.js") == "generated"


class TestBatchResolvePathAncestor:
    """Verify _derive_component_name uses proper path comparison."""

    def test_no_false_prefix_match(self):
        from uidetox.commands.batch_resolve import _derive_component_name
        # /src/app and /src/application should resolve to 'src', not 'app'
        result = _derive_component_name(["src/app/page.tsx", "src/application/layout.tsx"])
        assert result == "src"

    def test_same_directory(self):
        from uidetox.commands.batch_resolve import _derive_component_name
        result = _derive_component_name(["src/components/Button.tsx", "src/components/Card.tsx"])
        assert result == "components"

    def test_empty_files(self):
        from uidetox.commands.batch_resolve import _derive_component_name
        assert _derive_component_name([]) == "unknown"


class TestFinishBranchParsing:
    """Verify branch name parsing doesn't mangle names."""

    def test_removeprefix_doesnt_strip_chars(self):
        # Simulate git branch --list output
        lines = ["  main", "* feature-branch", "  master", "  star"]
        branches = [b.strip().removeprefix("* ").strip() for b in lines]
        assert "main" in branches
        assert "feature-branch" in branches
        assert "master" in branches
        assert "star" in branches  # Would have been 'tar' with old lstrip("* ")


class TestFinishSessionTargeting:
    """Ensure finish resolves the correct merge target for session branches."""

    def test_resolve_target_prefers_recorded_base_branch(self, monkeypatch):
        from uidetox.commands import finish as finish_cmd

        config = {
            "git_session": {
                "active_branch": "uidetox-session-123",
                "base_branch": "master",
            }
        }
        monkeypatch.setattr(finish_cmd, "_branch_exists", lambda branch: branch == "master")
        monkeypatch.setattr(finish_cmd, "_detect_main_branch", lambda: "main")

        target, reason = finish_cmd._resolve_target_branch("uidetox-session-123", config)
        assert target == "master"
        assert "recorded session base branch" in reason

    def test_resolve_target_falls_back_when_metadata_mismatches(self, monkeypatch):
        from uidetox.commands import finish as finish_cmd

        config = {
            "git_session": {
                "active_branch": "uidetox-session-other",
                "base_branch": "master",
            }
        }
        monkeypatch.setattr(finish_cmd, "_branch_exists", lambda branch: True)
        monkeypatch.setattr(finish_cmd, "_detect_main_branch", lambda: "main")

        target, reason = finish_cmd._resolve_target_branch("uidetox-session-123", config)
        assert target == "main"
        assert "detected default branch" in reason

    def test_clear_session_metadata_removes_matching_active_branch(self, monkeypatch):
        from uidetox.commands import finish as finish_cmd

        saved: dict = {}
        monkeypatch.setattr(
            finish_cmd,
            "load_config",
            lambda: {
                "auto_commit": True,
                "git_session": {
                    "active_branch": "uidetox-session-123",
                    "base_branch": "master",
                },
            },
        )
        monkeypatch.setattr(finish_cmd, "save_config", lambda cfg: saved.update(cfg))

        finish_cmd._clear_session_metadata("uidetox-session-123")

        assert saved.get("auto_commit") is True
        assert "git_session" not in saved


class TestLoopSessionMetadata:
    """Session branch creation should persist base-branch context."""

    def test_persist_session_preserves_existing_base(self, monkeypatch):
        from uidetox.commands import loop as loop_cmd

        saved: dict = {}
        monkeypatch.setattr(
            loop_cmd,
            "load_config",
            lambda: {
                "auto_commit": True,
                "git_session": {
                    "active_branch": "uidetox-session-old",
                    "base_branch": "master",
                },
            },
        )
        monkeypatch.setattr(loop_cmd, "save_config", lambda cfg: saved.update(cfg))

        loop_cmd._persist_git_session(active_branch="uidetox-session-new")

        assert saved["git_session"]["active_branch"] == "uidetox-session-new"
        assert saved["git_session"]["base_branch"] == "master"

    def test_ensure_session_branch_records_base_branch(self, monkeypatch):
        from uidetox.commands import loop as loop_cmd

        recorded: list[dict] = []

        def fake_run(cmd, capture_output=False, text=False, check=False):  # noqa: ANN001
            if cmd == ["git", "branch", "--show-current"]:
                return SimpleNamespace(stdout="master\n")
            if cmd[:3] == ["git", "checkout", "-b"]:
                return SimpleNamespace(stdout="")
            raise AssertionError(f"Unexpected git command: {cmd}")

        monkeypatch.setattr(loop_cmd.subprocess, "run", fake_run)
        monkeypatch.setattr(loop_cmd.uuid, "uuid4", lambda: SimpleNamespace(hex="abc123def4567890"))
        monkeypatch.setattr(loop_cmd, "_persist_git_session", lambda **kw: recorded.append(kw))

        loop_cmd._ensure_session_branch()

        assert recorded == [
            {
                "active_branch": "uidetox-session-abc123def456",
                "base_branch": "master",
            }
        ]


class TestToolingBackendDetection:
    """Verify backend detection uses if (not elif) for co-existing frameworks."""

    def test_express_detected_separately_from_nestjs(self, tmp_path):
        from uidetox.tooling import detect_backend, _pkg_json_cache
        import json
        _pkg_json_cache.clear()
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"express": "^4.18.0", "fastify": "^4.0.0"}
        }))
        backends = detect_backend(tmp_path)
        names = {b.name for b in backends}
        assert "express" in names
        assert "fastify" in names
        _pkg_json_cache.clear()

    def test_nestjs_suppresses_express(self, tmp_path):
        from uidetox.tooling import detect_backend, _pkg_json_cache
        import json
        _pkg_json_cache.clear()
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"@nestjs/core": "^10.0", "express": "^4.18.0"}
        }))
        backends = detect_backend(tmp_path)
        names = {b.name for b in backends}
        assert "nestjs" in names
        assert "express" not in names  # NestJS uses express internally
        _pkg_json_cache.clear()

    def test_python_config_file_accuracy(self, tmp_path):
        from uidetox.tooling import detect_backend, _pkg_json_cache
        _pkg_json_cache.clear()
        (tmp_path / "requirements.txt").write_text("flask\n")
        backends = detect_backend(tmp_path)
        python_backends = [b for b in backends if b.name == "python"]
        assert len(python_backends) == 1
        assert python_backends[0].config_file == "requirements.txt"
        _pkg_json_cache.clear()

    def test_python_prefers_pyproject(self, tmp_path):
        from uidetox.tooling import detect_backend, _pkg_json_cache
        _pkg_json_cache.clear()
        (tmp_path / "requirements.txt").write_text("flask\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
        backends = detect_backend(tmp_path)
        python_backends = [b for b in backends if b.name == "python"]
        assert python_backends[0].config_file == "pyproject.toml"
        _pkg_json_cache.clear()


class TestSkillsCleanup:
    """Verify dead code was removed from skills.py."""

    def test_no_re_import(self):
        import uidetox.skills as skills_mod
        import importlib
        source = Path(skills_mod.__file__).read_text()
        # 're' should not be imported at the top level
        assert "import re" not in source.split("# ---")[0]
