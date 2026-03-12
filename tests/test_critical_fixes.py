"""Regression tests for the 7 critical/high-severity bug fixes."""

import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── Issue 1: lint.py indentation fix ────────────────────────────

class TestLintIndentation:
    """lint.py must be valid Python (no IndentationError)."""

    def test_lint_module_compiles(self):
        source = (ROOT / "uidetox" / "commands" / "lint.py").read_text()
        # compile() raises SyntaxError (including IndentationError) if broken
        compile(source, "lint.py", "exec")

    def test_lint_module_parses_ast(self):
        source = (ROOT / "uidetox" / "commands" / "lint.py").read_text()
        tree = ast.parse(source)
        assert tree is not None


# ── Issue 2: batch_resolve.py infinite loop guard ───────────────

class TestBatchResolveNoInfiniteLoop:
    """_derive_component_name must not loop forever on divergent paths."""

    def test_common_ancestor_cross_drive(self):
        """Paths with no common prefix should not hang."""
        from uidetox.commands.batch_resolve import _derive_component_name
        # Completely unrelated paths
        result = _derive_component_name(["/a/b/c.tsx", "/a/d/e.tsx"])
        assert isinstance(result, str)
        assert result  # non-empty

    def test_common_ancestor_same_dir(self):
        from uidetox.commands.batch_resolve import _derive_component_name
        result = _derive_component_name(["src/Card.tsx", "src/Button.tsx"])
        assert result == "src"

    def test_common_ancestor_nested(self):
        from uidetox.commands.batch_resolve import _derive_component_name
        result = _derive_component_name(["src/ui/Card.tsx", "src/ui/sub/Button.tsx"])
        assert result == "ui"

    def test_common_ancestor_single_file(self):
        from uidetox.commands.batch_resolve import _derive_component_name
        result = _derive_component_name(["components/Header.tsx"])
        assert result == "components"


# ── Issue 3: subagent.py default confidence ─────────────────────

class TestSubagentDefaultConfidence:
    """_extract_confidence should default to 0.5 (uncertain), never 1.0."""

    def test_empty_result_returns_uncertain(self):
        from uidetox.subagent import _extract_confidence
        assert _extract_confidence({}) == 0.5

    def test_no_confidence_field_returns_uncertain(self):
        from uidetox.subagent import _extract_confidence
        result = {"note": "Fixed some things", "files_changed": 2}
        conf = _extract_confidence(result)
        assert conf <= 0.85, f"Default confidence {conf} should not auto-resolve"

    def test_explicit_confidence_respected(self):
        from uidetox.subagent import _extract_confidence
        result = {"note": "CONFIDENCE: 0.95", "files_changed": 1}
        assert _extract_confidence(result) == 0.95

    def test_warning_signals_lower_confidence(self):
        from uidetox.subagent import _extract_confidence
        result = {"note": "unsure about this, might not work, could break things"}
        conf = _extract_confidence(result)
        assert conf < 0.85


# ── Issue 4: analyzer.py catastrophic backtracking ──────────────

class TestAnalyzerRegexSafety:
    """Regex patterns must not use DOTALL with unbounded lazy quantifiers."""

    def test_no_dotall_with_lazy_star(self):
        """No rule should combine re.DOTALL with .*? — risks catastrophic backtracking."""
        from uidetox.analyzer import RULES
        for rule in RULES:
            pat = rule.get("pattern")
            if pat is None:
                continue
            has_dotall = bool(pat.flags & re.DOTALL)
            has_lazy = ".*?" in pat.pattern
            assert not (has_dotall and has_lazy), (
                f"Rule {rule['id']} uses re.DOTALL with .*? — catastrophic backtracking risk"
            )

    def test_gradient_text_regex_bounded(self):
        """GRADIENT_TEXT_SLOP regex must match within a single line."""
        from uidetox.analyzer import RULES
        rules_by_id = {r["id"]: r for r in RULES}
        pat = rules_by_id["GRADIENT_TEXT_SLOP"]["pattern"]
        # Must NOT have DOTALL flag
        assert not (pat.flags & re.DOTALL), "GRADIENT_TEXT_SLOP should be line-bounded"

    def test_regex_completes_on_adversarial_input(self):
        """All regex rules must complete in reasonable time on a large input."""
        import time
        from uidetox.analyzer import RULES
        # Adversarial input: lots of partial matches without completion
        adversarial = ("bg-clip-text " * 500 + "class='card " * 500 +
                        "text-center " * 500 + "mx-auto " * 500)
        for rule in RULES:
            pat = rule.get("pattern")
            if pat is None:
                continue
            start = time.monotonic()
            pat.findall(adversarial)
            elapsed = time.monotonic() - start
            assert elapsed < 2.0, (
                f"Rule {rule['id']} took {elapsed:.1f}s on adversarial input — regex too slow"
            )


# ── Issue 5: memory.py ChromaDB resource management ────────────

class TestChromaClientManagement:
    """ChromaDB clients must be properly managed, not leaked via @lru_cache."""

    def test_no_lru_cache_import(self):
        """memory.py must not use @lru_cache for ChromaDB clients."""
        source = (ROOT / "uidetox" / "memory.py").read_text()
        assert "lru_cache" not in source, (
            "memory.py still uses lru_cache — ChromaDB clients should be managed explicitly"
        )

    def test_atexit_registered(self):
        """memory.py must register an atexit handler to close clients."""
        source = (ROOT / "uidetox" / "memory.py").read_text()
        assert "atexit" in source

    def test_close_function_exists(self):
        """close_chroma_clients must be importable."""
        from uidetox.memory import close_chroma_clients
        assert callable(close_chroma_clients)


# ── Issue 6: memory.py unbounded embedding growth ───────────────

class TestEmbeddingCompaction:
    """compact_embeddings() must exist and be callable."""

    def test_compact_function_exists(self):
        from uidetox.memory import compact_embeddings
        assert callable(compact_embeddings)

    def test_compact_returns_dict_when_no_client(self):
        """compact_embeddings() should gracefully handle missing ChromaDB."""
        from uidetox.memory import compact_embeddings
        result = compact_embeddings()
        assert isinstance(result, dict)

    def test_finish_invokes_compact(self):
        """finish.py must call compact_embeddings somewhere."""
        source = (ROOT / "uidetox" / "commands" / "finish.py").read_text()
        assert "compact_embeddings" in source


# ── Issue 7: color_utils.py exception logging ──────────────────

class TestColorUtilsExceptionLogging:
    """File I/O errors in color_utils.py must be logged, not silently swallowed."""

    def test_no_bare_pass_after_os_error(self):
        """OSError handlers must log, not just 'pass'."""
        source = (ROOT / "uidetox" / "color_utils.py").read_text()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "except" in stripped and "OSError" in stripped:
                # The next non-blank line after the except should NOT be just 'pass'
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    if next_line:
                        assert next_line != "pass", (
                            f"Line {j+1}: bare 'pass' after OSError catch — "
                            f"should log the error for debugging"
                        )
                        break

    def test_logging_present_in_handlers(self):
        """color_utils.py should use logging in its exception handlers."""
        source = (ROOT / "uidetox" / "color_utils.py").read_text()
        assert "logging.getLogger" in source or "logger." in source


# ── Issue 8: git auto-commit safety in harness commands ─────────

class TestGitCommitSafety:
    """Automation commit paths should not bypass git hooks by default."""

    def test_no_no_verify_in_autonomous_commit_paths(self):
        for rel in [
            "uidetox/commands/autofix.py",
            "uidetox/commands/check.py",
            "uidetox/commands/resolve.py",
            "uidetox/commands/batch_resolve.py",
        ]:
            source = (ROOT / rel).read_text()
            assert "--no-verify" not in source, f"{rel} should not bypass git hooks by default"

    def test_check_uses_changed_file_delta_for_autocommit(self):
        source = (ROOT / "uidetox/commands/check.py").read_text()
        assert "_git_changed_paths" in source
        assert "post_fix_changed - pre_fix_changed" in source


# ── Issue 9: loop Stage-2 queue-empty transition gate ───────────

class TestLoopQueueEmptyTransition:
    """Stage-2 subjective review transition should be queue-empty gated at runtime."""

    def test_queue_empty_tag_is_defined(self):
        source = (ROOT / "uidetox/commands/loop.py").read_text()
        assert "_QUEUE_EMPTY_ONLY_TAG" in source

    def test_runtime_skip_guard_exists(self):
        source = (ROOT / "uidetox/commands/loop.py").read_text()
        assert "reason.startswith(_QUEUE_EMPTY_ONLY_TAG)" in source
        assert "Skipping queue-empty-only step" in source


# ── Issue 10: autofix phase resolution correctness ───────────────

class TestAutofixPhaseResolution:
    """Autofix should not resolve lint/format issues when fix commands fail."""

    def test_autofix_uses_phase_stats_for_resolution(self):
        source = (ROOT / "uidetox/commands/autofix.py").read_text()
        assert "if stats.clean" in source
        assert "Lint fix phase had failures" in source
        assert "Format fix phase had failures" in source

    def test_autofix_no_global_dedupe_set(self):
        source = (ROOT / "uidetox/commands/autofix.py").read_text()
        assert "_executed_cmds" not in source
        assert "phase_dedupe" in source


# ── Issue 11: loop autopilot failure telemetry ───────────────────

class TestLoopAutopilotTelemetry:
    """Autopilot should record command failures for circuit-breaker visibility."""

    def test_autopilot_logs_timeout_exception_and_failures(self):
        source = (ROOT / "uidetox/commands/loop.py").read_text()
        assert "loop_autopilot_cmd_timeout" in source
        assert "loop_autopilot_cmd_exception" in source
        assert "loop_autopilot_cmd_failed" in source
