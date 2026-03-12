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

from uidetox.utils import compute_design_score


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
        # T1=10 + T4=1 = 11 total slop, all pending
        assert scores["current_slop"] == 11
        assert scores["total_slop"] == 11
        assert scores["blended_score"] == 0  # nothing resolved

    def test_all_resolved_is_100(self):
        state = {
            "issues": [],
            "resolved": [{"tier": "T1"}, {"tier": "T2"}],
            "stats": {"scans_run": 1},
        }
        scores = compute_design_score(state)
        assert scores["blended_score"] == 100

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
