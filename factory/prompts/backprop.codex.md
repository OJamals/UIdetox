Backpropagate implementation learnings into living specs.

        Native adapter: `codex`

        Goal:
        - Scan current git diff.
        - Update only specs/docs whose claims became stale because of actual code changes.
        - Preserve product intent. Do not invent requirements from implementation accidents.
        - If change reveals missing decision, add explicit TODO or open question instead of deciding silently.
        - Keep updates minimal and reviewable.

        Diff stat:
        ```text
        AGENTS.md                      |  21 +-
 CLAUDE.md                      |  14 ++
 README.md                      |  12 +-
 tests/test_ast_capabilities.py |  14 ++
 tests/test_design_context.py   |  85 ++++++++
 tests/test_frontend_mapping.py |  37 ++++
 tests/test_regressions.py      |  37 ++++
 uidetox/analyzer_ast.py        | 440 ++++++++++++-----------------------------
 uidetox/analyzer_engine.py     |  11 +-
 uidetox/cli.py                 |   3 +
 uidetox/commands/loop.py       |  21 ++
 uidetox/commands/redesign.py   |  11 +-
 uidetox/commands/scan.py       |  19 +-
 uidetox/commands/setup.py      |  33 +++-
 uidetox/data/AGENTS.md         |  21 +-
 uidetox/design_context.py      | 110 ++++++++++-
 uidetox/frontend_map.py        |  94 +++++++--
 uidetox/frontend_semantics.py  | 259 +++++-------------------
 uidetox/prototype.py           |  75 ++++++-
 uidetox/redesign.py            | 385 ++++++++++++++++++++++++++++++++++--
 20 files changed, 1108 insertions(+), 594 deletions(-)
        ```

        Diff:
        ```diff
        diff --git a/AGENTS.md b/AGENTS.md
index 77ab437..b251b18 100644
--- a/AGENTS.md
+++ b/AGENTS.md
@@ -18,7 +18,7 @@ The goal is frontend code that makes someone ask "how was this made?" — not "w

 ## 2. The Autonomous Loop

-Run `uidetox loop` to bootstrap the full 5-phase protocol. The loop automatically orchestrates the following flow, guiding the agent step-by-step:
+Run `uidetox loop` to preview the full 5-phase protocol. Add `--execute` to run its deterministic phases in process with resumable state; the workflow pauses when agent work, proposal selection, subjective review, or fresh verification evidence is required:

 ### Phase 0: Mechanical Checks
 The loop triggers `uidetox check --fix` to execute tsc → lint → format in sequence. Errors are automatically queued as T1 issues and auto-fixed where possible.
@@ -75,9 +75,9 @@ Reference files in `reference/` provide deep-dive guidance for each design domai
 | Command | Purpose |
 |---------|---------|
 | `uidetox setup` | Initialize typed design dials and intent (`--audience`, `--primary-job`, `--tone`, `--genre`, `--page-kind`, `--brand`, repeatable `--preserve`/`--constraint`) plus preview/commit settings |
-| `uidetox scan` | Full audit: auto-detect tooling → static analyzer → design review |
-| `uidetox map [target]` | Build `.uidetox/frontend-map.json` with AST-aware source semantics, extraction provenance/confidence, source hashes, plus optional rendered DOM/a11y/layout evidence (`--runtime`, repeatable `--url`, `--screenshots`, `--timeout`, `--output`, `--json`) |
-| `uidetox redesign [target]` | Generate 1–5 topology-first redesign plans with pairwise structural-distance checks (`--variants`, `--refresh-map`, `--map-file`, `--output`, `--json`) |
+| `uidetox scan` | Full audit: auto-detect tooling → static analyzer → frontend/backend operation parity → design review |
+| `uidetox map [target]` | Build `.uidetox/frontend-map.json` with shared AST source facts, frontend ownership/import semantics, backend/API operation parity, provenance/confidence, source hashes, plus optional rendered DOM/a11y/layout evidence (`--runtime`, repeatable `--url`, `--screenshots`, `--timeout`, `--output`, `--json`) |
+| `uidetox redesign [target]` | Generate 1–5 source-aware, topology-first redesign plans with dependency-ordered migration steps, freshness/blocker evidence, and pairwise structural-distance checks (`--variants`, `--refresh-map`, `--map-file`, `--output`, `--json`) |
 | `uidetox compare` | Compare redesigns across seven structural dimensions and pairwise distance (`--file`, `--json`) |
 | `uidetox prototype <proposal-id>` | Write a disposable agent brief with evidence isolation, preserved contracts, migration steps, and acceptance checks (`--file`, `--output`, `--stdout`) |
 | `uidetox detect` | Auto-discover linters, formatters, tsc, backend, database, API |
@@ -90,7 +90,7 @@ Reference files in `reference/` provide deep-dive guidance for each design domai
 | `uidetox next` | Batch issues for top-priority component/directory with SKILL.md context injection |
 | `uidetox resolve <id> --note "..."` | Mark a single issue as fixed (note is mandatory) |
 | `uidetox batch-resolve ID1 ID2 ... --note "..."` | Resolve multiple issues with a single coherent commit |
-| `uidetox loop` | Enter autonomous self-propagation fix loop with LLM-dynamic analysis |
+| `uidetox loop` | Preview the autonomous protocol; add `--execute` for durable in-process phase execution (`--proposal-id`, `--review-score`) |
 | `uidetox loop --orchestrator` | Sub-agent mode with auto-parallel (1-5) and memory injection |
 | `uidetox subagent` | Manage sub-agent sessions and generate stage prompts |
 | `uidetox memory` | Read/write persistent agent memory (patterns, notes, reviewed files) |
@@ -194,10 +194,13 @@ UIdetox/
 │   ├── state.py                  # Issue queue + config in .uidetox/
 │   ├── tooling.py                # Auto-detection (tsc, biome, eslint, NestJS, etc.)
 │   ├── analyzer.py               # 218-rule static slop detector (deterministic anti-pattern scan)
-│   ├── frontend_map.py            # Semantic frontend graph + artifact persistence
-│   ├── redesign.py                # Divergent topology-first redesign planning
-│   ├── runtime_observer.py         # Playwright DOM/a11y/layout evidence adapter
-│   ├── prototype.py                # Disposable agent-ready prototype brief generation
+│   ├── source_facts.py           # Shared AST parse lifecycle + immutable source facts
+│   ├── frontend_map.py           # Semantic frontend graph + artifact persistence
+│   ├── project_map.py            # Backend/API discovery + operation parity
+│   ├── redesign.py              # Source-aware divergent redesign planning
+│   ├── runtime_observer.py      # Playwright DOM/a11y/layout evidence adapter
+│   ├── prototype.py             # Disposable agent-ready prototype brief generation
+│   ├── workflow.py              # Durable executable loop state machine
 │   ├── history.py                # Run snapshot storage and progression tracking
 │   ├── memory.py                 # Persistent agent memory (reviewed files, patterns, notes)
 │   ├── subagent.py               # Sub-agent session infrastructure (5-stage pipeline)
diff --git a/CLAUDE.md b/CLAUDE.md
index 0c3544d..8cf1cc7 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -16,3 +16,17 @@ If the project is not indexed, run `index_repository` before exploration. Before

 Fall back to grep or glob for string literals, error messages, config values, and non-code files when graph tools are insufficient.
 <!-- codebase-memory-mcp:end -->
+
+## Agent skills
+
+### Issue tracker
+
+Issues and PRDs live in GitHub Issues. External PRs are not a triage surface. See `docs/agents/issue-tracker.md`.
+
+### Triage labels
+
+Use canonical `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix` labels. See `docs/agents/triage-labels.md`.
+
+### Domain docs
+
+Use single-context domain documentation. See `docs/agents/domain.md`.
diff --git a/README.md b/README.md
index f8cd629..e59993d 100644
--- a/README.md
+++ b/README.md
@@ -117,7 +117,15 @@ RULES:

 ## The Autonomous Protocol

-`uidetox loop` drives a fully autonomous **scan → fix → verify** cycle. The loop continues until the Design Score meets the target (default 95) and the issue queue is empty.
+`uidetox loop` remains a safe preview: it prints the **scan → fix → verify** protocol for an agent to follow. Add `--execute` to run the deterministic phases in process and persist resumable state at `.uidetox/workflow-state.json`:
+
+```bash
+uidetox loop --execute
+uidetox loop --execute --proposal-id REDESIGN-01-task-flow
+uidetox loop --execute --proposal-id REDESIGN-01-task-flow --review-score 97
+```
+
+Execution never invokes an external agent CLI and never chooses a redesign proposal automatically. It stops explicitly when source fixes need an agent, proposal selection is missing, subjective scoring needs human/LLM input, or verification evidence is stale/blocked. Completed fresh phases are skipped on resume; source or input changes invalidate only dependent downstream phases. Failures are recorded once and retried only on a later invocation. Passing the score, queue, and freshness gates marks `uidetox finish` as eligible—it does not run finalization automatically.

 ### The Intelligence Layer
 UIdetox uses a multi-modal approach to detect slop and plan remediation. It combines static AST analysis with persistent semantic memory to ensure fixes are both correct and consistent with the project's identity.
@@ -158,7 +166,7 @@ Use `--refresh-map` to force a rebuild, `--map-file` or `--file` to consume a sp

 | Command | Purpose |
 | :--- | :--- |
-| `uidetox loop` | Start the autonomous workflow (scan → fix → verify cycle). |
+| `uidetox loop` | Preview the autonomous protocol; add `--execute` for durable in-process phase execution. |
 | `uidetox setup` | Persist typed design dials, design intent, `dev_server`, and auto-commit behavior. Intent flags include `--audience`, `--primary-job`, `--tone`, `--genre`, `--page-kind`, `--brand`, repeatable `--preserve`, and repeatable `--constraint`. |
 | `uidetox scan` | Run 218-rule static analysis + dynamic WCAG theme audit + subjective rubric injection. |
 | `uidetox map [target]` | Build a persistent semantic frontend graph; optionally merge rendered DOM evidence (`--runtime`, repeatable `--url`, `--screenshots`, `--timeout`, `--output`, `--json`). |
diff --git a/tests/test_ast_capabilities.py b/tests/test_ast_capabilities.py
index 9c8886b..59eec75 100644
--- a/tests/test_ast_capabilities.py
+++ b/tests/test_ast_capabilities.py
@@ -1,6 +1,9 @@
 """Per-language AST capability behavior."""

+from pathlib import Path
+
 import uidetox.analyzer_ast as analyzer_ast
+import uidetox.frontend_semantics as frontend_semantics


 def test_ast_capabilities_are_visible_and_extension_specific():
@@ -49,3 +52,14 @@ def test_missing_grammar_records_error_without_disabling_others(monkeypatch):
         analyzer_ast._AST_LANGUAGES.update(original_languages)
         analyzer_ast.AST_CAPABILITIES.clear()
         analyzer_ast.AST_CAPABILITIES.update(original_capabilities)
+
+
+def test_ast_parser_monkeypatch_compatibility_seams_remain_callable(monkeypatch):
+    source = Path("Component.tsx")
+    content = "export const Component = () => <main />;"
+
+    monkeypatch.setattr(analyzer_ast, "_get_parser", lambda _extension: None)
+    monkeypatch.setattr(frontend_semantics, "_get_parser", lambda _extension: None)
+
+    assert analyzer_ast._analyze_ast(source, content, ".tsx") == []
+    assert frontend_semantics.extract_script_semantics(source, content) is None
diff --git a/tests/test_design_context.py b/tests/test_design_context.py
index 0c3e00b..b3f26e5 100644
--- a/tests/test_design_context.py
+++ b/tests/test_design_context.py
@@ -52,6 +52,8 @@ def test_design_settings_merge_configured_preflight_with_map_inference(tmp_path)
     assert settings.intent.primary_job == "complete and submit the mapped workflow"
     assert settings.intent.genre == "task workflow"
     assert settings.intent.source == "configured+inferred"
+    assert settings.intent.provenance["audience"] == "explicit"
+    assert settings.intent.provenance["primary_job"] == "mapped"


 def test_dials_change_proposal_structure_and_fingerprint(tmp_path):
@@ -130,3 +132,86 @@ def test_setup_persists_typed_design_intent(monkeypatch):
     assert saved["design_intent"]["primary_job"] == "repair an asset"
     assert saved["design_intent"]["preserve"] == ("offline operation",)
     assert saved["design_intent"]["constraints"] == ("glove-friendly targets",)
+    assert saved["design_intent"]["provenance"]["primary_job"] == "explicit"
+
+
+def test_default_setup_preserves_mapped_intent_through_redesign(
+    monkeypatch, tmp_path
+):
+    saved = {}
+    monkeypatch.setattr(setup_command, "ensure_uidetox_dir", lambda: None)
+    monkeypatch.setattr(setup_command, "load_config", lambda: {})
+    monkeypatch.setattr(
+        setup_command, "save_config", lambda config: saved.update(config)
+    )
+
+    setup_command.run(parse_args(["setup", "--no-auto-commit"]))
+
+    assert "design_intent" not in saved
+
+    _write_frontend(tmp_path)
+    frontend_map = map_frontend(tmp_path)
+    settings = DesignSettings.from_config(saved, frontend_map)
+    redesign_set = propose_redesigns(
+        frontend_map,
+        RedesignBrief(variants=1, intent=settings.intent),
+    )
+
+    assert settings.intent.primary_job == "complete and submit the mapped workflow"
+    assert settings.intent.genre == "task workflow"
+    assert settings.intent.preserve == frontend_map.contracts.must_preserve
+    assert settings.intent.constraints == frontend_map.contracts.unknown
+    assert settings.intent.provenance["primary_job"] == "mapped"
+    assert redesign_set.brief.intent == settings.intent
+
+
+def test_legacy_defaults_do_not_mask_mapping_but_non_defaults_remain_explicit(
+    tmp_path,
+):
+    _write_frontend(tmp_path)
+    frontend_map = map_frontend(tmp_path)
+    settings = DesignSettings.from_config(
+        {
+            "design_intent": {
+                "audience": "warehouse operators",
+                "primary_job": "complete the mapped product task",
+                "genre": "product interface",
+                "preserve": [],
+                "constraints": [],
+                "source": "configured",
+            }
+        },
+        frontend_map,
+    )
+
+    assert settings.intent.audience == "warehouse operators"
+    assert settings.intent.primary_job == "complete and submit the mapped workflow"
+    assert settings.intent.genre == "task workflow"
+    assert settings.intent.preserve == frontend_map.contracts.must_preserve
+    assert settings.intent.constraints == frontend_map.contracts.unknown
+    assert settings.intent.provenance["audience"] == "explicit"
+    assert settings.intent.provenance["genre"] == "mapped"
+
+
+def test_empty_explicit_values_and_metadata_cannot_mask_mapping(tmp_path):
+    _write_frontend(tmp_path)
+    frontend_map = map_frontend(tmp_path)
+    settings = DesignSettings.from_config(
+        {
+            "design_intent": {
+                "primary_job": " ",
+                "preserve": [],
+                "source": "explicit",
+                "provenance": {
+                    "primary_job": "explicit",
+                    "preserve": "explicit",
+                    "source": "explicit",
+                },
+            }
+        },
+        frontend_map,
+    )
+
+    assert settings.intent.primary_job == "complete and submit the mapped workflow"
+    assert settings.intent.preserve == frontend_map.contracts.must_preserve
+    assert settings.intent.provenance["primary_job"] == "mapped"
diff --git a/tests/test_frontend_mapping.py b/tests/test_frontend_mapping.py
index 571af05..22ea9c3 100644
--- a/tests/test_frontend_mapping.py
+++ b/tests/test_frontend_mapping.py
@@ -137,6 +137,7 @@ def test_map_frontend_builds_semantic_graph_and_contracts(tmp_path):
     }
     assert {node.name for node in nodes if node.kind == "route"} == {"/dashboard"}
     assert {node.name for node in nodes if node.kind == "data"} == {"/api/items"}
+    assert next(node for node in nodes if node.kind == "data").metadata["method"] == "GET"
     assert {node.name for node in nodes if node.kind == "state"} == {"loading"}
     assert {node.name for node in nodes if node.kind == "token"} == {
         "--color-accent",
@@ -284,6 +285,42 @@ def test_frontend_map_freshness_tracks_add_change_and_delete(tmp_path):
     assert frontend_map_is_fresh(refreshed, tmp_path, "src") is False


+def test_frontend_map_freshness_tracks_backend_contract_edits(tmp_path):
+    _write_frontend(tmp_path)
+    api = tmp_path / "api.py"
+    api.write_text(
+        """
+from fastapi import FastAPI
+app = FastAPI()
+
+@app.get("/api/items")
+def items():
+    return []
+""".strip(),
+        encoding="utf-8",
+    )
+    frontend_map = map_frontend(tmp_path, "src")
+
+    assert frontend_map_is_fresh(frontend_map, tmp_path, "src") is True
+    assert {
+        operation["method"]
+        for operation in frontend_map.project_map["backend_operations"]
+    } == {"GET"}
+
+    api.write_text(
+        api.read_text(encoding="utf-8").replace("@app.get", "@app.post"),
+        encoding="utf-8",
+    )
+    assert frontend_map_is_fresh(frontend_map, tmp_path, "src") is False
+
+    refreshed = map_frontend(tmp_path, "src")
+    assert frontend_map_is_fresh(refreshed, tmp_path, "src") is True
+    assert {
+        operation["method"]
+        for operation in refreshed.project_map["backend_operations"]
+    } == {"POST"}
+
+
 def test_redesigns_are_structurally_divergent_and_preserve_contracts(tmp_path):
     _write_frontend(tmp_path)
     frontend_map = map_frontend(tmp_path)
diff --git a/tests/test_regressions.py b/tests/test_regressions.py
index cae171e..867baae 100644
--- a/tests/test_regressions.py
+++ b/tests/test_regressions.py
@@ -9158,6 +9158,43 @@ def test_analyzer_custom_issue_shape_and_order(tmp_path):
     ]


+def test_analyzer_css_and_unsupported_issue_output_contract(tmp_path):
+    css = tmp_path / "representative.css"
+    css.write_text(".thing { transition: all 300ms ease; }\n", encoding="utf-8")
+    unsupported = tmp_path / "representative.txt"
+    unsupported.write_text("transition: all\n", encoding="utf-8")
+
+    assert analyze_file(css) == [
+        {
+            "id": "TRANSITION_ALL_SLOP",
+            "file": str(css.resolve()),
+            "tier": "T1",
+            "issue": "transition: all — animates everything including layout properties.",
+            "command": (
+                "Specify only compositor-safe properties: transition: transform, "
+                "opacity, filter."
+            ),
+            "line": 1,
+            "column": 10,
+            "snippet": ".thing { transition: all 300ms ease; }",
+        },
+        {
+            "id": "EASE_DEFAULT_SLOP",
+            "file": str(css.resolve()),
+            "tier": "T2",
+            "issue": "CSS 'ease' easing — generic browser default, use intentional curves.",
+            "command": (
+                "Use cubic-bezier(0.16, 1, 0.3, 1) (expo-out) or linear() for "
+                "spring-like motion."
+            ),
+            "line": 1,
+            "column": 32,
+            "snippet": ".thing { transition: all 300ms ease; }",
+        },
+    ]
+    assert analyze_file(unsupported) == []
+
+
 def test_analyzer_ast_issue_shape_and_missing_parser_fallback(tmp_path):
     from uidetox.analyzer import HAS_AST, _analyze_ast, _get_parser

diff --git a/uidetox/analyzer_ast.py b/uidetox/analyzer_ast.py
index 5d40909..ae2a28e 100644
--- a/uidetox/analyzer_ast.py
+++ b/uidetox/analyzer_ast.py
@@ -1,18 +1,26 @@
-"""Tree-sitter parser setup and AST-based analyzer checks."""
+"""Compatibility facade and issue projection for shared source facts."""

-import importlib
-import re
+from __future__ import annotations
+
+from collections import Counter
 from pathlib import Path

-tree_sitter = None
-_CORE_AST_ERROR: str | None = None
-try:
-    import tree_sitter
-except ImportError as exc:
-    _CORE_AST_ERROR = f"{type(exc).__name__}: {exc}"
+from uidetox import source_facts as _source_facts
+from uidetox.source_facts import (
+    SourceFacts,
+    _extract_usestate_binding,
+    _identifier_tokens,
+    _is_animation_state_identifier,
+    extract_source_facts,
+)

-_AST_LANGUAGES: dict[str, object] = {}
-AST_CAPABILITIES: dict[str, dict[str, object]] = {}
+# Compatibility seams retained for callers and monkeypatch-based tests.
+importlib = _source_facts.importlib
+tree_sitter = _source_facts.tree_sitter
+_CORE_AST_ERROR = _source_facts._CORE_AST_ERROR
+_AST_LANGUAGES = _source_facts._AST_LANGUAGES
+AST_CAPABILITIES = _source_facts.AST_CAPABILITIES
+HAS_AST = _source_facts.HAS_AST


 def _load_grammar(
@@ -21,326 +29,140 @@ def _load_grammar(
     factory_name: str,
     extensions: tuple[str, ...],
 ) -> None:
-    """Register one grammar without disabling unrelated AST languages."""
-    error = _CORE_AST_ERROR
-    language = None
-    if tree_sitter is not None:
-        try:
-            module = importlib.import_module(module_name)
-            language = tree_sitter.Language(getattr(module, factory_name)())
-        except (ImportError, AttributeError, TypeError, ValueError, OSError) as exc:
-            error = f"{type(exc).__name__}: {exc}"
-    if language is not None:
-        for extension in extensions:
-            _AST_LANGUAGES[extension] = language
-    AST_CAPABILITIES[name] = {
-        "available": language is not None,
-        "extensions": extensions,
-        "error": error,
-    }
-
-
-_load_grammar(
-    "javascript", "tree_sitter_javascript", "language", (".js", ".jsx", ".mjs", ".cjs")
-)
-_load_grammar("typescript", "tree_sitter_typescript", "language_typescript", (".ts",))
-_load_grammar("tsx", "tree_sitter_typescript", "language_tsx", (".tsx",))
-_load_grammar("css", "tree_sitter_css", "language", (".css", ".scss", ".less"))
-
-HAS_AST = any(capability["available"] for capability in AST_CAPABILITIES.values())
+    """Register one grammar through the shared parser registry."""
+    _source_facts._load_grammar(name, module_name, factory_name, extensions)


 def ast_capabilities() -> dict[str, dict[str, object]]:
     """Return serializable per-language AST availability and failure details."""
-    return {
-        name: {
-            **capability,
-            "extensions": list(capability["extensions"]),
-        }
-        for name, capability in AST_CAPABILITIES.items()
-    }
+    return _source_facts.ast_capabilities()


 def has_ast_for(ext: str) -> bool:
     """Report whether an AST parser is available for one file extension."""
-    return ext.lower() in _AST_LANGUAGES
-
-
-_USESTATE_BINDING_RE = re.compile(
-    r"\b(?:const|let|var)\s+\[\s*(?P<state>[A-Za-z_$][\w$]*)\s*,"
-    r"\s*[A-Za-z_$][\w$]*\s*\]\s*=\s*(?:React\.)?useState\b"
-)
-_IDENTIFIER_TOKEN_RE = re.compile(
-    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
-)
-_ANIMATION_STATE_TOKENS = frozenset(
-    {
-        "x",
-        "y",
-        "top",
-        "left",
-        "right",
-        "bottom",
-        "opacity",
-        "scale",
-        "rotate",
-        "position",
-        "transform",
-    }
-)
-_ANIMATION_STATE_PREFIXES = ("animat", "transit", "translate")
-
-
-def _extract_usestate_binding(declaration_text: str) -> str | None:
-    """Return the first state binding from a standard destructured useState declaration."""
-    match = _USESTATE_BINDING_RE.search(declaration_text)
-    return match.group("state") if match else None
-
-
-def _identifier_tokens(identifier: str) -> tuple[str, ...]:
-    """Split an identifier across separators, digits, and camel/Pascal case."""
-    return tuple(token.lower() for token in _IDENTIFIER_TOKEN_RE.findall(identifier))
-
-
-def _is_animation_state_identifier(identifier: str) -> bool:
-    """Classify animation state from identifier tokens, never raw substrings."""
-    return any(
-        token in _ANIMATION_STATE_TOKENS or token.startswith(_ANIMATION_STATE_PREFIXES)
-        for token in _identifier_tokens(identifier)
-    )
+    return _source_facts.has_ast_for(ext)


 def _get_parser(ext: str):
-    language = _AST_LANGUAGES.get(ext.lower())
-    if tree_sitter is None or language is None:
-        return None
-    return tree_sitter.Parser(language)
-
-
-def _analyze_ast(filepath: Path, content: str, ext: str) -> list[dict]:
-    parser = _get_parser(ext)
-    if not parser:
+    """Compatibility wrapper around shared parser selection."""
+    return _source_facts.get_parser(ext)
+
+
+def _analyze_ast(
+    filepath: Path,
+    content: str,
+    ext: str,
+    facts: SourceFacts | None = None,
+) -> list[dict]:
+    """Project shared AST facts into legacy analyzer issue dictionaries."""
+    if facts is None:
+        facts = extract_source_facts(filepath, content, parser_factory=_get_parser)
+    if facts is None or ext not in {".tsx", ".jsx", ".js", ".ts"}:
         return []

-    try:
-        tree = parser.parse(content.encode("utf-8", errors="ignore"))
-    except Exception:
-        return []
-
-    issues = []
+    state = facts.analyzer
+    issues: list[dict] = []
     fpath = str(filepath.resolve())

-    if ext in {".tsx", ".jsx", ".js", ".ts"}:
-        state = {
-            "div_count": 0,
-            "semantic_count": 0,
-            "nested_ternaries": 0,
-            "cards": 0,
-            "charts": 0,
-            # Deep prop drilling detection
-            "prop_pass_depth": 0,  # max depth of a prop passed through components
-            "prop_names_seen": {},  # prop name -> list of component names where it appears
-            # useState for animation detection
-            "usestate_for_animation": False,
-            # Identical sibling components (e.g., 4 KPI cards in a row)
-            "sibling_components": {},  # parent_id -> list of child component names
-            # Styled-component nesting depth
-            "styled_nesting_depth": 0,
+    if state.div_count > 20 and state.semantic_count == 0:
+        issues.append(
+            {
+                "id": "DIV_SOUP_SLOP",
+                "file": fpath,
+                "tier": "T2",
+                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state.div_count} divs, 0 semantic elements)",
+                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>.",
+            }
+        )
+
+    if state.nested_ternaries >= 2:
+        issues.append(
+            {
+                "id": "NESTED_TERNARY_SLOP",
+                "file": fpath,
+                "tier": "T2",
+                "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state.nested_ternaries} nested ternaries found)",
+                "command": "Extract nested ternaries into named variables or early returns for clarity.",
+            }
+        )
+
+    if state.cards >= 3 and state.charts >= 1:
+        issues.append(
+            {
+                "id": "HERO_DASHBOARD_SLOP",
+                "file": fpath,
+                "tier": "T3",
+                "issue": f"Hero metric dashboard pattern detected via AST ({state.cards} cards, {state.charts} charts) — cliché AI layout.",
+                "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow.",
+            }
+        )
+
+    drilled_props = [
+        name
+        for name, components in state.prop_components
+        if len(components) >= 4
+        and name
+        not in {
+            "className",
+            "children",
+            "key",
+            "id",
+            "style",
+            "ref",
+            "onClick",
+            "onChange",
         }
-
-        def _node_text(node) -> str:
-            try:
-                return node.text.decode("utf-8", errors="ignore")
-            except AttributeError:
-                return str(node.text)
-
-        def walk(node, depth=0):
-            if node.type in ("jsx_element", "jsx_self_closing_element"):
-                open_tag = (
-                    node.child_by_field_name("open_tag")
-                    if node.type == "jsx_element"
-                    else node
-                )
-                if open_tag:
-                    name_node = open_tag.child_by_field_name("name")
-                    if name_node:
-                        tag_name = _node_text(name_node)
-
-                        if tag_name == "div":
-                            state["div_count"] += 1
-                        elif tag_name in {
-                            "nav",
-                            "main",
-                            "article",
-                            "section",
-                            "aside",
-                            "header",
-                            "footer",
-                        }:
-                            state["semantic_count"] += 1
-
-                        # Detect Dashboard Slop
-                        if (
-                            "Card" in tag_name
-                            or "Stat" in tag_name
-                            or "Metric" in tag_name
-                        ):
-                            state["cards"] += 1
-                        elif (
-                            "Chart" in tag_name
-                            or "Graph" in tag_name
-                            or "Activity" in tag_name
-                        ):
-                            state["charts"] += 1
-
-                        # Track sibling component repetition for layout-level slop
-                        parent_id = id(node.parent) if node.parent else 0
-                        if tag_name[0:1].isupper():  # React component (capitalized)
-                            state["sibling_components"].setdefault(
-                                parent_id, []
-                            ).append(tag_name)
-
-                        # Detect deep prop drilling: props passed through with same name
-                        for attr in open_tag.children or []:
-                            if attr.type == "jsx_attribute":
-                                attr_name_node = attr.child_by_field_name("name")
-                                if attr_name_node:
-                                    attr_name = _node_text(attr_name_node)
-                                    state["prop_names_seen"].setdefault(
-                                        attr_name, set()
-                                    ).add(tag_name)
-
-            elif node.type == "ternary_expression":
-                for child in node.children:
-                    if child.type == "ternary_expression":
-                        state["nested_ternaries"] += 1
-
-            # Detect useState used for animation values (bad pattern)
-            elif node.type == "lexical_declaration":
-                binding = _extract_usestate_binding(_node_text(node))
-                if binding and _is_animation_state_identifier(binding):
-                    state["usestate_for_animation"] = True
-
-            # Detect deeply nested styled-components tagged templates
-            elif node.type == "tagged_template_expression":
-                tag = node.child_by_field_name("function")
-                if tag:
-                    tag_text = _node_text(tag)
-                    if "styled" in tag_text or "css" in tag_text:
-                        # Count nesting depth of CSS selectors within
-                        tmpl = node.child_by_field_name("arguments") or node
-                        nesting = _node_text(tmpl).count("{")
-                        if nesting > state["styled_nesting_depth"]:
-                            state["styled_nesting_depth"] = nesting
-
-            for child in node.children:
-                walk(child, depth + 1)
-
-        walk(tree.root_node)
-
-        if state["div_count"] > 20 and state["semantic_count"] == 0:
-            issues.append(
-                {
-                    "id": "DIV_SOUP_SLOP",
-                    "file": fpath,
-                    "tier": "T2",
-                    "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state['div_count']} divs, 0 semantic elements)",
-                    "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>.",
-                }
-            )
-
-        if state["nested_ternaries"] >= 2:
-            issues.append(
-                {
-                    "id": "NESTED_TERNARY_SLOP",
-                    "file": fpath,
-                    "tier": "T2",
-                    "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state['nested_ternaries']} nested ternaries found)",
-                    "command": "Extract nested ternaries into named variables or early returns for clarity.",
-                }
-            )
-
-        if state["cards"] >= 3 and state["charts"] >= 1:
-            issues.append(
-                {
-                    "id": "HERO_DASHBOARD_SLOP",
-                    "file": fpath,
-                    "tier": "T3",
-                    "issue": f"Hero metric dashboard pattern detected via AST ({state['cards']} cards, {state['charts']} charts) — cliché AI layout.",
-                    "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow.",
-                }
-            )
-
-        # ── AST: Deep prop drilling ──
-        drilled_props = [
-            name
-            for name, components in state["prop_names_seen"].items()
-            if len(components) >= 4
-            and name
-            not in {
-                "className",
-                "children",
-                "key",
-                "id",
-                "style",
-                "ref",
-                "onClick",
-                "onChange",
+    ]
+    if drilled_props:
+        sample = ", ".join(sorted(drilled_props)[:5])
+        issues.append(
+            {
+                "id": "PROP_DRILLING_SLOP",
+                "file": fpath,
+                "tier": "T3",
+                "issue": f"Deep prop drilling detected via AST — prop(s) '{sample}' passed through 4+ components.",
+                "command": "Extract deeply drilled props into React Context, Zustand store, or composition pattern to reduce coupling.",
+            }
+        )
+
+    if state.animation_state:
+        issues.append(
+            {
+                "id": "ANIMATE_STATE_SLOP",
+                "file": fpath,
+                "tier": "T2",
+                "issue": "React useState used for animation values — causes re-renders on every frame.",
+                "command": "Use CSS transitions/animations, Framer Motion, or useRef for animation state. Never drive 60fps animations through React state.",
             }
-        ]
-        if drilled_props:
-            sample = ", ".join(sorted(drilled_props)[:5])
+        )
+
+    for children in state.sibling_component_groups:
+        if len(children) < 4:
+            continue
+        counts = Counter(children)
+        for component_name, count in counts.items():
+            if count < 4:
+                continue
             issues.append(
                 {
-                    "id": "PROP_DRILLING_SLOP",
+                    "id": "IDENTICAL_SIBLINGS_SLOP",
                     "file": fpath,
                     "tier": "T3",
-                    "issue": f"Deep prop drilling detected via AST — prop(s) '{sample}' passed through 4+ components.",
-                    "command": "Extract deeply drilled props into React Context, Zustand store, or composition pattern to reduce coupling.",
-                }
-            )
-
-        # ── AST: useState for animation values ──
-        if state["usestate_for_animation"]:
-            issues.append(
-                {
-                    "id": "ANIMATE_STATE_SLOP",
-                    "file": fpath,
-                    "tier": "T2",
-                    "issue": "React useState used for animation values — causes re-renders on every frame.",
-                    "command": "Use CSS transitions/animations, Framer Motion, or useRef for animation state. Never drive 60fps animations through React state.",
-                }
-            )
-
-        # ── AST: Identical sibling components (generic layout slop) ──
-        for parent_id, children in state["sibling_components"].items():
-            if len(children) >= 4:
-                from collections import Counter
-
-                counts = Counter(children)
-                for comp_name, count in counts.items():
-                    if count >= 4:
-                        issues.append(
-                            {
-                                "id": "IDENTICAL_SIBLINGS_SLOP",
-                                "file": fpath,
-                                "tier": "T3",
-                                "issue": f"Generic layout pattern detected via AST: {count} identical <{comp_name}/> siblings — dashboard/feature-grid slop.",
-                                "command": f"Vary the {comp_name} instances (different sizes, spans, emphasis) or replace with asymmetric layout. Identical cards = AI fingerprint.",
-                            }
-                        )
-                        break  # One issue per parent
-
-        # ── AST: Deeply nested styled-components ──
-        if state["styled_nesting_depth"] >= 5:
-            issues.append(
-                {
-                    "id": "STYLED_NESTING_SLOP",
-                    "file": fpath,
-                    "tier": "T2",
-                    "issue": f"Deeply nested styled-component selectors detected ({state['styled_nesting_depth']} levels) — specificity war.",
-                    "command": "Flatten CSS nesting. Use component composition instead of deeply nested selectors.",
+                    "issue": f"Generic layout pattern detected via AST: {count} identical <{component_name}/> siblings — dashboard/feature-grid slop.",
+                    "command": f"Vary the {component_name} instances (different sizes, spans, emphasis) or replace with asymmetric layout. Identical cards = AI fingerprint.",
                 }
             )
+            break
+
+    if state.styled_nesting_depth >= 5:
+        issues.append(
+            {
+                "id": "STYLED_NESTING_SLOP",
+                "file": fpath,
+                "tier": "T2",
+                "issue": f"Deeply nested styled-component selectors detected ({state.styled_nesting_depth} levels) — specificity war.",
+                "command": "Flatten CSS nesting. Use component composition instead of deeply nested selectors.",
+            }
+        )

     return issues
diff --git a/uidetox/analyzer_engine.py b/uidetox/analyzer_engine.py
index d6d4de0..9c98794 100644
--- a/uidetox/analyzer_engine.py
+++ b/uidetox/analyzer_engine.py
@@ -7,6 +7,7 @@ from uidetox.analyzer_ast import _analyze_ast, has_ast_for
 from uidetox.analyzer_custom import _CUSTOM_CHECK_HANDLERS, _analyze_component_layout
 from uidetox.fileset import ProjectFileSet, find_project_root
 from uidetox.rule_registry import ANALYZER_RULES as RULES
+from uidetox.source_facts import SourceFacts


 def _analyze_rule(
@@ -53,7 +54,13 @@ def _analyze_rule(
     return issues


-def analyze_file(filepath: Path, design_variance: int = 8, dynamic_colors: dict[str, str] | None = None) -> list[dict]:
+def analyze_file(
+    filepath: Path,
+    design_variance: int = 8,
+    dynamic_colors: dict[str, str] | None = None,
+    *,
+    facts: SourceFacts | None = None,
+) -> list[dict]:
     """Scan a single file against all slop rules.

     Args:
@@ -83,7 +90,7 @@ def analyze_file(filepath: Path, design_variance: int = 8, dynamic_colors: dict[
         return issues  # Skip binary or unreadable files

     if has_ast_for(ext):
-        ast_issues = _analyze_ast(filepath, content, ext)
+        ast_issues = _analyze_ast(filepath, content, ext, facts=facts)
         issues.extend(ast_issues)

     # Component-level layout heuristics (runs regardless of AST)
diff --git a/uidetox/cli.py b/uidetox/cli.py
index 2b8c234..9e1b431 100644
--- a/uidetox/cli.py
+++ b/uidetox/cli.py
@@ -191,6 +191,9 @@ def parse_args(args_list=None):
     loop_parser = subparsers.add_parser("loop", help="Instruct the AI agent to enter an autonomous fix loop")
     loop_parser.add_argument("--target", type=int, default=95, help="Target design score to reach (default 95)")
     loop_parser.add_argument("--orchestrator", action="store_true", help="Use sub-agent orchestrator mode (one agent per stage)")
+    loop_parser.add_argument("--execute", action="store_true", help="Execute resumable phases in process (preview remains the default)")
+    loop_parser.add_argument("--proposal-id", help="Explicit redesign proposal selected for prototype generation")
+    loop_parser.add_argument("--review-score", type=int, choices=range(0, 101), help="Human/LLM subjective review score used to resume the review gate")

     # Command: finish
     subparsers.add_parser("finish", help="Squash-merge and commit an active UIdetox session branch")
diff --git a/uidetox/commands/loop.py b/uidetox/commands/loop.py
index 36c3390..cc4dd21 100644
--- a/uidetox/commands/loop.py
+++ b/uidetox/commands/loop.py
@@ -23,12 +23,33 @@ from ..fileset import ProjectFileSet
 from ..tooling import detect_all
 from ..memory import get_patterns, get_notes, get_session, get_last_scan, save_session, log_progress
 from ..utils import compute_design_score
+from ..workflow import run_executable_workflow


 def run(args: argparse.Namespace):
     target = getattr(args, "target", 95)
     ensure_uidetox_dir()
     project_root = get_project_root()
+    if getattr(args, "execute", False):
+        config = load_config()
+        config["target_score"] = target
+        save_config(config)
+        if config.get("auto_commit"):
+            _ensure_session_branch()
+        result = run_executable_workflow(
+            project_root,
+            target_score=target,
+            proposal_id=getattr(args, "proposal_id", None),
+            subjective_score=getattr(args, "review_score", None),
+        )
+        print("UIdetox executable workflow")
+        print(f"  Status: {result.status}")
+        print(f"  Phase : {result.phase or 'none'}")
+        if result.waiting:
+            print(f"  Wait  : {result.waiting}")
+        print(f"  State : {result.state_path}")
+        print(f"  Next  : {result.message}")
+        return

     # ---- Auto-detect tooling ----
     config = load_config()
diff --git a/uidetox/commands/redesign.py b/uidetox/commands/redesign.py
index 666b441..46659eb 100644
--- a/uidetox/commands/redesign.py
+++ b/uidetox/commands/redesign.py
@@ -10,6 +10,7 @@ from uidetox.frontend_map import (
     frontend_map_is_fresh,
     load_frontend_map,
     map_frontend,
+    retain_runtime_evidence,
     save_frontend_map,
 )
 from uidetox.redesign import RedesignBrief, propose_redesigns, save_redesign_set
@@ -27,18 +28,22 @@ def run(args: argparse.Namespace) -> None:
     )
     refresh = getattr(args, "refresh_map", False)

-    if refresh or not map_path.exists():
+    previous_map = load_frontend_map(map_path) if map_path.exists() else None
+    if refresh or previous_map is None:
         frontend_map = map_frontend(root, target)
+        if previous_map is not None:
+            frontend_map = retain_runtime_evidence(previous_map, frontend_map)
         save_frontend_map(frontend_map, map_path)
     else:
-        frontend_map = load_frontend_map(map_path)
+        frontend_map = previous_map
         requested_target = _target_label(root, target)
         if (
             frontend_map.root != str(root.resolve())
             or frontend_map.target != requested_target
             or not frontend_map_is_fresh(frontend_map, root, target)
         ):
-            frontend_map = map_frontend(root, target)
+            refreshed_map = map_frontend(root, target)
+            frontend_map = retain_runtime_evidence(frontend_map, refreshed_map)
             save_frontend_map(frontend_map, map_path)

     config = load_config()
diff --git a/uidetox/commands/scan.py b/uidetox/commands/scan.py
index 9e5a071..0584504 100644
--- a/uidetox/commands/scan.py
+++ b/uidetox/commands/scan.py
@@ -14,6 +14,8 @@ import sys
 import uuid
 from uidetox.analyzer import analyze_directory, RULES
 from uidetox.commands.add_issue import _is_suppressed
+from uidetox.frontend_map import map_frontend
+from uidetox.project_map import ProjectMap
 from uidetox.state import (
     add_issues, ensure_uidetox_dir, get_project_root, load_config, load_state,
     save_config, increment_scans,
@@ -299,7 +301,22 @@ def run(args: argparse.Namespace):
     has_fullstack = bool(backends or databases or apis)
     if has_fullstack:
         print()
-        print("  Full-stack: check DTO alignment, type safety, error surfacing across layers.")
+        try:
+            parity = ProjectMap.from_dict(map_frontend(scan_path).project_map)
+            counts = parity.counts
+            print(
+                "  Full-stack operation parity: "
+                f"frontend-only={counts['frontend_only']}, "
+                f"backend-only={counts['backend_only']}, "
+                f"method-mismatch={counts['method_mismatch']}, "
+                f"unresolved={counts['unresolved']}."
+            )
+            print(
+                "  Evidence scope: static HTTP routes and schema references only; "
+                "auth, UI error states, and business equivalence remain unverified."
+            )
+        except (OSError, TypeError, ValueError) as error:
+            print(f"  Full-stack operation parity unavailable: {error}")

     # ===========================================================
     # PART 2: SUBJECTIVE ANALYSIS (LLM-driven design review)
diff --git a/uidetox/commands/setup.py b/uidetox/commands/setup.py
index 9495616..4b9f8e3 100644
--- a/uidetox/commands/setup.py
+++ b/uidetox/commands/setup.py
@@ -33,8 +33,13 @@ def run(args: argparse.Namespace):
     if getattr(args, "visual_density", None) is not None:
         config["VISUAL_DENSITY"] = args.visual_density

-    existing_intent = config.get("design_intent", {})
-    intent = dict(existing_intent) if isinstance(existing_intent, dict) else {}
+    existing_settings = DesignSettings.from_config(config)
+    intent = {
+        field_name: getattr(existing_settings.intent, field_name)
+        for field_name, source in existing_settings.intent.provenance.items()
+        if source == "explicit"
+    }
+    provenance = {field_name: "explicit" for field_name in intent}
     intent_fields = {
         "audience": "audience",
         "primary_job": "primary_job",
@@ -47,17 +52,37 @@ def run(args: argparse.Namespace):
         value = getattr(args, argument, None)
         if isinstance(value, str) and value.strip():
             intent[key] = value.strip()
+            provenance[key] = "explicit"
     for argument, key in (("preserve", "preserve"), ("constraint", "constraints")):
         values = getattr(args, argument, None)
         if values is not None:
-            intent[key] = [str(value).strip() for value in values if str(value).strip()]
+            cleaned = [str(value).strip() for value in values if str(value).strip()]
+            if cleaned:
+                intent[key] = cleaned
+                provenance[key] = "explicit"
     if intent:
         intent["source"] = "configured"
+        intent["provenance"] = provenance
         config["design_intent"] = intent
+    else:
+        config.pop("design_intent", None)

     settings = DesignSettings.from_config(config)
     config.update(settings.dials.to_config())
-    config["design_intent"] = settings.intent.to_dict()
+    serialized_intent = settings.intent.to_dict()
+    explicit_intent = {
+        field_name: serialized_intent[field_name]
+        for field_name, source in settings.intent.provenance.items()
+        if source == "explicit"
+    }
+    if explicit_intent:
+        explicit_intent["source"] = "configured"
+        explicit_intent["provenance"] = {
+            field_name: "explicit" for field_name in explicit_intent
+        }
+        config["design_intent"] = explicit_intent
+    else:
+        config.pop("design_intent", None)

     dev_server = getattr(args, "dev_server", None)
     if isinstance(dev_server, str) and dev_server.strip():
diff --git a/uidetox/data/AGENTS.md b/uidetox/data/AGENTS.md
index 77ab437..b251b18 100644
--- a/uidetox/data/AGENTS.md
+++ b/uidetox/data/AGENTS.md
@@ -18,7 +18,7 @@ The goal is frontend code that makes someone ask "how was this made?" — not "w

 ## 2. The Autonomous Loop

-Run `uidetox loop` to bootstrap the full 5-phase protocol. The loop automatically orchestrates the following flow, guiding the agent step-by-step:
+Run `uidetox loop` to preview the full 5-phase protocol. Add `--execute` to run its deterministic phases in process with resumable state; the workflow pauses when agent work, proposal selection, subjective review, or fresh verification evidence is required:

 ### Phase 0: Mechanical Checks
 The loop triggers `uidetox check --fix` to execute tsc → lint → format in sequence. Errors are automatically queued as T1 issues and auto-fixed where possible.
@@ -75,9 +75,9 @@ Reference files in `reference/` provide deep-dive guidance for each design domai
 | Command | Purpose |
 |---------|---------|
 | `uidetox setup` | Initialize typed design dials and intent (`--audience`, `--primary-job`, `--tone`, `--genre`, `--page-kind`, `--brand`, repeatable `--preserve`/`--constraint`) plus preview/commit settings |
-| `uidetox scan` | Full audit: auto-detect tooling → static analyzer → design review |
-| `uidetox map [target]` | Build `.uidetox/frontend-map.json` with AST-aware source semantics, extraction provenance/confidence, source hashes, plus optional rendered DOM/a11y/layout evidence (`--runtime`, repeatable `--url`, `--screenshots`, `--timeout`, `--output`, `--json`) |
-| `uidetox redesign [target]` | Generate 1–5 topology-first redesign plans with pairwise structural-distance checks (`--variants`, `--refresh-map`, `--map-file`, `--output`, `--json`) |
+| `uidetox scan` | Full audit: auto-detect tooling → static analyzer → frontend/backend operation parity → design review |
+| `uidetox map [target]` | Build `.uidetox/frontend-map.json` with shared AST source facts, frontend ownership/import semantics, backend/API operation parity, provenance/confidence, source hashes, plus optional rendered DOM/a11y/layout evidence (`--runtime`, repeatable `--url`, `--screenshots`, `--timeout`, `--output`, `--json`) |
+| `uidetox redesign [target]` | Generate 1–5 source-aware, topology-first redesign plans with dependency-ordered migration steps, freshness/blocker evidence, and pairwise structural-distance checks (`--variants`, `--refresh-map`, `--map-file`, `--output`, `--json`) |
 | `uidetox compare` | Compare redesigns across seven structural dimensions and pairwise distance (`--file`, `--json`) |
 | `uidetox prototype <proposal-id>` | Write a disposable agent brief with evidence isolation, preserved contracts, migration steps, and acceptance checks (`--file`, `--output`, `--stdout`) |
 | `uidetox detect` | Auto-discover linters, formatters, tsc, backend, database, API |
@@ -90,7 +90,7 @@ Reference files in `reference/` provide deep-dive guidance for each design domai
 | `uidetox next` | Batch issues for top-priority component/directory with SKILL.md context injection |
 | `uidetox resolve <id> --note "..."` | Mark a single issue as fixed (note is mandatory) |
 | `uidetox batch-resolve ID1 ID2 ... --note "..."` | Resolve multiple issues with a single coherent commit |
-| `uidetox loop` | Enter autonomous self-propagation fix loop with LLM-dynamic analysis |
+| `uidetox loop` | Preview the autonomous protocol; add `--execute` for durable in-process phase execution (`--proposal-id`, `--review-score`) |
 | `uidetox loop --orchestrator` | Sub-agent mode with auto-parallel (1-5) and memory injection |
 | `uidetox subagent` | Manage sub-agent sessions and generate stage prompts |
 | `uidetox memory` | Read/write persistent agent memory (patterns, notes, reviewed files) |
@@ -194,10 +194,13 @@ UIdetox/
 │   ├── state.py                  # Issue queue + config in .uidetox/
 │   ├── tooling.py                # Auto-detection (tsc, biome, eslint, NestJS, etc.)
 │   ├── analyzer.py               # 218-rule static slop detector (deterministic anti-pattern scan)
-│   ├── frontend_map.py            # Semantic frontend graph + artifact persistence
-│   ├── redesign.py                # Divergent topology-first redesign planning
-│   ├── runtime_observer.py         # Playwright DOM/a11y/layout evidence adapter
-│   ├── prototype.py                # Disposable agent-ready prototype brief generation
+│   ├── source_facts.py           # Shared AST parse lifecycle + immutable source facts
+│   ├── frontend_map.py           # Semantic frontend graph + artifact persistence
+│   ├── project_map.py            # Backend/API discovery + operation parity
+│   ├── redesign.py              # Source-aware divergent redesign planning
+│   ├── runtime_observer.py      # Playwright DOM/a11y/layout evidence adapter
+│   ├── prototype.py             # Disposable agent-ready prototype brief generation
+│   ├── workflow.py              # Durable executable loop state machine
 │   ├── history.py                # Run snapshot storage and progression tracking
 │   ├── memory.py                 # Persistent agent memory (reviewed files, patterns, notes)
 │   ├── subagent.py               # Sub-agent session infrastructure (5-stage pipeline)
diff --git a/uidetox/design_context.py b/uidetox/design_context.py
index 86ea16d..b791d53 100644
--- a/uidetox/design_context.py
+++ b/uidetox/design_context.py
@@ -2,13 +2,36 @@

 from __future__ import annotations

-from dataclasses import asdict, dataclass
+from dataclasses import asdict, dataclass, field
 from typing import TYPE_CHECKING, Any, Mapping

 if TYPE_CHECKING:
     from uidetox.frontend_map import FrontendMap


+_INTENT_DEFAULTS: dict[str, Any] = {
+    "scope": ".",
+    "audience": "product users",
+    "primary_job": "complete the mapped product task",
+    "tone": "purposeful and brand-specific",
+    "genre": "product interface",
+    "page_kind": "page",
+    "brand": "preserve existing brand signals",
+    "preserve": (),
+    "constraints": (),
+}
+_INTENT_FIELDS = tuple(_INTENT_DEFAULTS)
+_MAPPED_INTENT_FIELDS = (
+    "scope",
+    "primary_job",
+    "genre",
+    "page_kind",
+    "preserve",
+    "constraints",
+)
+_PROVENANCE_VALUES = frozenset({"explicit", "mapped", "fallback"})
+
+
 def _dial(name: str, value: Any, default: int) -> int:
     try:
         parsed = int(default if value is None else value)
@@ -66,6 +89,7 @@ class DesignIntent:
     preserve: tuple[str, ...] = ()
     constraints: tuple[str, ...] = ()
     source: str = "inferred"
+    provenance: dict[str, str] = field(default_factory=dict)

     @classmethod
     def from_dict(cls, value: Mapping[str, Any] | None) -> "DesignIntent":
@@ -83,6 +107,7 @@ class DesignIntent:
             preserve=_strings(data.get("preserve")),
             constraints=_strings(data.get("constraints")),
             source=_text(data.get("source"), "configured"),
+            provenance=_provenance(data.get("provenance")),
         )

     def to_dict(self) -> dict[str, Any]:
@@ -106,11 +131,24 @@ class DesignSettings:
         if not isinstance(configured, Mapping) or not configured:
             intent = inferred
         else:
-            merged = {
-                **inferred.to_dict(),
-                **configured,
-                "source": "configured+inferred",
-            }
+            explicit_fields = _explicit_fields(configured)
+            configured_intent = DesignIntent.from_dict(configured)
+            merged = inferred.to_dict()
+            provenance = dict(inferred.provenance)
+            for field_name in explicit_fields:
+                merged[field_name] = getattr(configured_intent, field_name)
+                provenance[field_name] = "explicit"
+            has_mapped_fields = any(
+                value == "mapped" for value in provenance.values()
+            )
+            merged["source"] = (
+                "configured+inferred"
+                if explicit_fields and has_mapped_fields
+                else "configured"
+                if explicit_fields
+                else inferred.source
+            )
+            merged["provenance"] = provenance
             intent = DesignIntent.from_dict(merged)
         return cls(dials=DesignDials.from_config(config), intent=intent)

@@ -121,7 +159,10 @@ def infer_design_intent(
 ) -> DesignIntent:
     """Infer a conservative preflight brief when PRODUCT/DESIGN context is absent."""
     if frontend_map is None:
-        return DesignIntent(scope=target)
+        return DesignIntent(
+            scope=target,
+            provenance={field_name: "fallback" for field_name in _INTENT_FIELDS},
+        )
     fingerprint = frontend_map.fingerprint
     topology = str(fingerprint.get("topology", "generic-page"))
     counts = fingerprint.get("node_counts", {})
@@ -144,6 +185,12 @@ def infer_design_intent(
         page_kind=page_kind,
         preserve=frontend_map.contracts.must_preserve,
         constraints=frontend_map.contracts.unknown,
+        provenance={
+            field_name: (
+                "mapped" if field_name in _MAPPED_INTENT_FIELDS else "fallback"
+            )
+            for field_name in _INTENT_FIELDS
+        },
     )


@@ -159,3 +206,52 @@ def _strings(value: Any) -> tuple[str, ...]:
     if not isinstance(value, (list, tuple)):
         return ()
     return tuple(str(item).strip() for item in value if str(item).strip())
+
+
+def _provenance(value: Any) -> dict[str, str]:
+    if not isinstance(value, Mapping):
+        return {}
+    return {
+        field_name: source
+        for field_name, source in value.items()
+        if field_name in _INTENT_FIELDS
+        and isinstance(source, str)
+        and source in _PROVENANCE_VALUES
+    }
+
+
+def _explicit_fields(configured: Mapping[str, Any]) -> tuple[str, ...]:
+    provenance_value = configured.get("provenance")
+    if isinstance(provenance_value, Mapping):
+        provenance = _provenance(provenance_value)
+        return tuple(
+            field_name
+            for field_name in _INTENT_FIELDS
+            if provenance.get(field_name) == "explicit"
+            and _has_configured_value(field_name, configured.get(field_name))
+        )
+
+    explicit_fields = []
+    for field_name, default in _INTENT_DEFAULTS.items():
+        if field_name not in configured:
+            continue
+        value = _normalized_intent_value(field_name, configured.get(field_name))
+        if (
+            _has_configured_value(field_name, configured.get(field_name))
+            and value != default
+        ):
+            explicit_fields.append(field_name)
+    return tuple(explicit_fields)
+
+
+def _normalized_intent_value(field_name: str, value: Any) -> Any:
+    default = _INTENT_DEFAULTS[field_name]
+    if field_name in {"preserve", "constraints"}:
+        return _strings(value)
+    return _text(value, default)
+
+
+def _has_configured_value(field_name: str, value: Any) -> bool:
+    if field_name in {"preserve", "constraints"}:
+        return bool(_strings(value))
+    return isinstance(value, str) and bool(value.strip())
diff --git a/uidetox/frontend_map.py b/uidetox/frontend_map.py
index 4d6e45f..caa6abf 100644
--- a/uidetox/frontend_map.py
+++ b/uidetox/frontend_map.py
@@ -14,14 +14,16 @@ import os
 import re
 import tempfile
 from collections import Counter, defaultdict
-from dataclasses import asdict, dataclass, field
+from dataclasses import asdict, dataclass, field, replace
 from pathlib import Path
 from typing import Any, Iterable
 from urllib.parse import urlsplit

 from uidetox.analyzer_ast import ast_capabilities
 from uidetox.frontend_semantics import ScriptSemantics, extract_script_semantics
+from uidetox.project_map import build_project_map, project_source_manifest
 from uidetox.runtime_observer import RuntimeObservation
+from uidetox.source_facts import extract_source_facts
 from uidetox.state import ensure_uidetox_dir, get_uidetox_dir
 from uidetox.utils import now_iso

@@ -175,6 +177,7 @@ class FrontendMap:
     contracts: ExperienceContract
     fingerprint: dict[str, Any]
     evidence: dict[str, Any]
+    project_map: dict[str, Any] = field(default_factory=dict)

     def to_dict(self) -> dict[str, Any]:
         return asdict(self)
@@ -200,6 +203,7 @@ class FrontendMap:
             contracts=ExperienceContract.from_dict(dict(value.get("contracts", {}))),
             fingerprint=dict(value.get("fingerprint", {})),
             evidence=dict(value.get("evidence", {})),
+            project_map=dict(value.get("project_map", {})),
         )


@@ -260,7 +264,8 @@ def map_frontend(
         source_hashes[relative_path] = hashlib.sha256(
             content.encode("utf-8")
         ).hexdigest()
-        semantics = extract_script_semantics(path, content)
+        source_facts = extract_source_facts(path, content)
+        semantics = extract_script_semantics(path, content, facts=source_facts)
         extractor = semantics.extractor if semantics is not None else "regex-fallback"
         confidence = semantics.confidence if semantics is not None else 0.55
         extractor_counts[extractor] += 1
@@ -421,22 +426,38 @@ def map_frontend(
             edges.append(FrontendEdge(owner_id, state_id, "owns"))

         endpoint_occurrences = (
-            [(item.name, item.line) for item in semantics.endpoints]
+            [(item.name, item.line, item.method) for item in semantics.endpoints]
             if semantics is not None
             else [
                 *(
-                    (match.group(1), _line_number(content, match.start()))
+                    (match.group(1), _line_number(content, match.start()), "GET")
                     for match in _FETCH_PATTERN.finditer(content)
                 ),
                 *(
-                    (match.group(1), _line_number(content, match.start()))
+                    (match.group(1), _line_number(content, match.start()), None)
                     for match in _AXIOS_PATTERN.finditer(content)
                 ),
             ]
         )
-        endpoints = dict(endpoint_occurrences)
-        for endpoint, line in endpoints.items():
-            data_id = _node_id("data", relative_path, endpoint)
+        endpoints = {
+            (endpoint, method): line
+            for endpoint, line, method in endpoint_occurrences
+        }
+        endpoint_path_counts = Counter(endpoint for endpoint, _method in endpoints)
+        for (endpoint, method), line in endpoints.items():
+            identity = (
+                endpoint
+                if endpoint_path_counts[endpoint] == 1
+                else f"{method or '?'}:{endpoint}"
+            )
+            data_id = _node_id("data", relative_path, identity)
+            metadata = {
+                "transport": "http",
+                "extractor": extractor,
+                "confidence": confidence,
+            }
+            if method is not None:
+                metadata["method"] = method
             nodes.append(
                 FrontendNode(
                     id=data_id,
@@ -444,11 +465,7 @@ def map_frontend(
                     name=endpoint,
                     file=relative_path,
                     line=line,
-                    metadata={
-                        "transport": "http",
-                        "extractor": extractor,
-                        "confidence": confidence,
-                    },
+                    metadata=metadata,
                 )
             )
             edges.append(FrontendEdge(owner_id, data_id, "reads"))
@@ -573,6 +590,7 @@ def map_frontend(
     runtime_screenshots = [
         page.screenshot for page in runtime_pages if page.screenshot is not None
     ]
+    project_map = build_project_map(root_path, nodes)

     return FrontendMap(
         schema_version=SCHEMA_VERSION,
@@ -595,8 +613,11 @@ def map_frontend(
             "source_manifest": {
                 "target": target_label,
                 "files": dict(sorted(source_hashes.items())),
+                "project_files": project_map.evidence.get("source_manifest", {}),
             },
+            "source_status": "current",
             "runtime_observed": bool(runtime_pages),
+            "runtime_status": "current" if runtime_pages else "absent",
             "runtime_generated_at": runtime.generated_at
             if runtime is not None
             else None,
@@ -606,6 +627,7 @@ def map_frontend(
             "runtime_screenshots": runtime_screenshots,
             "runtime_errors": list(runtime.errors) if runtime is not None else [],
         },
+        project_map=project_map.to_dict(),
     )


@@ -642,6 +664,41 @@ def load_frontend_map(path: str | Path | None = None) -> FrontendMap:
     return FrontendMap.from_dict(value)


+def retain_runtime_evidence(
+    previous: FrontendMap,
+    refreshed: FrontendMap,
+) -> FrontendMap:
+    """Retain prior runtime provenance and label it stale after source changes."""
+
+    if (
+        previous.root != refreshed.root
+        or previous.target != refreshed.target
+        or not previous.evidence.get("runtime_observed")
+    ):
+        return refreshed
+    previous_manifest = previous.evidence.get("source_manifest", {})
+    refreshed_manifest = refreshed.evidence.get("source_manifest", {})
+    previous_status = str(previous.evidence.get("runtime_status", "current"))
+    same_source = previous_manifest == refreshed_manifest
+    runtime_status = (
+        "current"
+        if same_source and previous_status == "current"
+        else "stale"
+    )
+    evidence = dict(refreshed.evidence)
+    for key, value in previous.evidence.items():
+        if key.startswith("runtime_"):
+            evidence[key] = value
+    evidence["runtime_status"] = runtime_status
+    evidence["runtime_observed"] = True
+    evidence["runtime_stale_reason"] = (
+        None
+        if runtime_status == "current"
+        else "Source manifest changed after the recorded runtime observation."
+    )
+    return replace(refreshed, evidence=evidence)
+
+
 def frontend_map_is_fresh(
     frontend_map: FrontendMap,
     root: str | Path | None = None,
@@ -651,7 +708,11 @@ def frontend_map_is_fresh(
     if frontend_map.evidence.get("extractor_version") != EXTRACTOR_VERSION:
         return False
     expected = frontend_map.evidence.get("source_manifest")
-    if not isinstance(expected, dict) or not isinstance(expected.get("files"), dict):
+    if (
+        not isinstance(expected, dict)
+        or not isinstance(expected.get("files"), dict)
+        or not isinstance(expected.get("project_files"), dict)
+    ):
         return False

     root_path = Path(root or frontend_map.root).expanduser().resolve()
@@ -665,7 +726,10 @@ def frontend_map_is_fresh(
     )
     if expected.get("target") != target_label:
         return False
-    return expected["files"] == _build_source_manifest(root_path, scope)
+    return (
+        expected["files"] == _build_source_manifest(root_path, scope)
+        and expected["project_files"] == project_source_manifest(root_path)
+    )


 def _resolve_scope(root: Path, target: str | Path | None) -> Path:
diff --git a/uidetox/frontend_semantics.py b/uidetox/frontend_semantics.py
index 4e9af08..cd3c9db 100644
--- a/uidetox/frontend_semantics.py
+++ b/uidetox/frontend_semantics.py
@@ -1,22 +1,22 @@
-"""AST-backed source semantics for frontend mapping.
-
-Regex remains a deliberate fallback for languages whose tree-sitter grammar is
-unavailable. Consumers get provenance and confidence with every extraction.
-"""
+"""Compatibility projection from shared source facts to frontend semantics."""

 from __future__ import annotations

-import re
 from dataclasses import dataclass
 from pathlib import Path

 from uidetox.analyzer_ast import _get_parser
+from uidetox.source_facts import SourceFacts, extract_source_facts
+
+_UNSET_FACTS = object()


 @dataclass(frozen=True)
 class SemanticOccurrence:
     name: str
     line: int
+    method: str | None = None
+    dynamic: bool = False


 @dataclass(frozen=True)
@@ -34,212 +34,47 @@ class ScriptSemantics:
     parse_errors: bool


-_ROUTE_ATTRIBUTE_RE = re.compile(r"^path\s*=\s*[\"']([^\"']+)[\"']$")
-_ACTION_ATTRIBUTE_RE = re.compile(r"^on([A-Z][A-Za-z0-9_]*)\b")
-_ROUTER_IDENTIFIERS = frozenset(
-    {"createBrowserRouter", "createRoutesFromElements", "router", "routes"}
-)
-_REGION_TAGS = frozenset(
-    {
-        "header",
-        "nav",
-        "main",
-        "aside",
-        "section",
-        "article",
-        "footer",
-        "form",
-        "table",
-        "dialog",
-    }
-)
-
-
-def extract_script_semantics(path: Path, content: str) -> ScriptSemantics | None:
-    """Extract script semantics from syntax nodes; return ``None`` for fallback."""
-    parser = _get_parser(path.suffix.lower())
-    if parser is None:
-        return None
-    try:
-        tree = parser.parse(content.encode("utf-8", errors="ignore"))
-    except (TypeError, ValueError, RuntimeError):
+def extract_script_semantics(
+    path: Path,
+    content: str,
+    facts: SourceFacts | None | object = _UNSET_FACTS,
+) -> ScriptSemantics | None:
+    """Return the legacy semantic view, reusing precomputed facts when supplied."""
+    if facts is _UNSET_FACTS:
+        facts = extract_source_facts(path, content, parser_factory=_get_parser)
+    if facts is None:
         return None
-
-    nodes = list(_walk(tree.root_node))
-    imported_aliases: dict[str, str] = {}
-    use_state_names = {"useState", "React.useState"}
-    imports: list[str] = []
-
-    for node in nodes:
-        if node.type not in {"import_statement", "export_statement"}:
-            continue
-        source = node.child_by_field_name("source")
-        if source is not None:
-            imports.append(_literal(source))
-        if node.type != "import_statement" or _literal(source) != "react":
-            react_import = False
-        else:
-            react_import = True
-        for child in node.named_children:
-            if child.type != "import_clause":
-                continue
-            for specifier in _walk(child):
-                if specifier.type != "import_specifier":
-                    continue
-                identifiers = [
-                    _text(item)
-                    for item in specifier.named_children
-                    if item.type == "identifier"
-                ]
-                if not identifiers:
-                    continue
-                imported = identifiers[0]
-                local = identifiers[-1]
-                imported_aliases[local] = imported
-                if react_import and imported == "useState":
-                    use_state_names.add(local)
-
-    components: list[SemanticOccurrence] = []
-    rendered_tags: list[str] = []
-    regions: list[SemanticOccurrence] = []
-    actions: list[SemanticOccurrence] = []
-    states: list[SemanticOccurrence] = []
-    endpoints: list[SemanticOccurrence] = []
-    routes: list[SemanticOccurrence] = []
-    config_routes: list[SemanticOccurrence] = []
-    has_router_signal = False
-
-    for node in nodes:
-        if node.type in {"function_declaration", "class_declaration"}:
-            name_node = node.child_by_field_name("name")
-            name = _text(name_node)
-            if name[:1].isupper():
-                components.append(SemanticOccurrence(name, _line(node)))
-        elif node.type == "variable_declarator":
-            name_node = node.child_by_field_name("name")
-            value_node = node.child_by_field_name("value")
-            name = _text(name_node)
-            if (
-                name[:1].isupper()
-                and value_node is not None
-                and value_node.type
-                in {
-                    "arrow_function",
-                    "function_expression",
-                }
-            ):
-                components.append(SemanticOccurrence(name, _line(node)))
-            if value_node is not None and value_node.type == "call_expression":
-                call_name = _text(value_node.child_by_field_name("function"))
-                if call_name in use_state_names and name_node is not None:
-                    identifiers = [
-                        _text(item)
-                        for item in _walk(name_node)
-                        if item.type == "identifier"
-                    ]
-                    if identifiers:
-                        states.append(SemanticOccurrence(identifiers[0], _line(node)))
-        elif node.type in {"jsx_opening_element", "jsx_self_closing_element"}:
-            tag = _text(node.child_by_field_name("name"))
-            if not tag:
-                continue
-            rendered = imported_aliases.get(tag, tag)
-            if rendered[:1].isupper():
-                rendered_tags.append(rendered)
-            if tag.lower() in _REGION_TAGS:
-                regions.append(SemanticOccurrence(tag.lower(), _line(node)))
-            for child in node.named_children:
-                if child.type != "jsx_attribute":
-                    continue
-                attribute = _text(child)
-                action_match = _ACTION_ATTRIBUTE_RE.match(attribute)
-                if action_match:
-                    actions.append(
-                        SemanticOccurrence(action_match.group(1), _line(child))
-                    )
-                if tag.rsplit(".", 1)[-1] == "Route":
-                    route_match = _ROUTE_ATTRIBUTE_RE.match(attribute)
-                    if route_match:
-                        routes.append(
-                            SemanticOccurrence(route_match.group(1), _line(child))
-                        )
-        elif node.type == "call_expression":
-            call_name = _text(node.child_by_field_name("function"))
-            if call_name == "fetch" or call_name.lower() in {
-                "axios.get",
-                "axios.post",
-                "axios.put",
-                "axios.patch",
-                "axios.delete",
-            }:
-                arguments = node.child_by_field_name("arguments")
-                literal = _first_literal(arguments)
-                if literal:
-                    endpoints.append(SemanticOccurrence(literal, _line(node)))
-        elif node.type == "pair":
-            key = _text(node.child_by_field_name("key")).strip("\"'")
-            if key == "path":
-                value = node.child_by_field_name("value")
-                literal = _literal(value)
-                if literal:
-                    config_routes.append(SemanticOccurrence(literal, _line(node)))
-        elif node.type == "identifier" and _text(node) in _ROUTER_IDENTIFIERS:
-            has_router_signal = True
-
-    if has_router_signal:
-        routes.extend(config_routes)
-    parse_errors = bool(tree.root_node.has_error)
+    assert isinstance(facts, SourceFacts)
     return ScriptSemantics(
-        components=_unique_occurrences(components),
-        imports=tuple(dict.fromkeys(item for item in imports if item)),
-        rendered_tags=tuple(dict.fromkeys(rendered_tags)),
-        regions=tuple(regions),
-        actions=tuple(actions),
-        states=_unique_occurrences(states),
-        endpoints=_unique_occurrences(endpoints),
-        routes=_unique_occurrences(routes),
-        extractor="tree-sitter",
-        confidence=0.85 if parse_errors else 1.0,
-        parse_errors=parse_errors,
+        components=tuple(
+            SemanticOccurrence(item.name, item.line)
+            for item in facts.declared_ui_modules
+        ),
+        imports=facts.imports,
+        rendered_tags=facts.rendered_modules,
+        regions=tuple(
+            SemanticOccurrence(item.name, item.line) for item in facts.regions
+        ),
+        actions=tuple(
+            SemanticOccurrence(item.name, item.line) for item in facts.actions
+        ),
+        states=tuple(
+            SemanticOccurrence(item.name, item.line) for item in facts.states
+        ),
+        endpoints=tuple(
+            SemanticOccurrence(
+                item.url,
+                item.line,
+                method=item.method,
+                dynamic=item.dynamic,
+            )
+            for item in facts.endpoints
+            if item.url is not None
+        ),
+        routes=tuple(
+            SemanticOccurrence(item.name, item.line) for item in facts.routes
+        ),
+        extractor=facts.extractor,
+        confidence=facts.confidence,
+        parse_errors=facts.parse_errors,
     )
-
-
-def _walk(node):
-    yield node
-    for child in node.named_children:
-        yield from _walk(child)
-
-
-def _text(node) -> str:
-    if node is None:
-        return ""
-    return node.text.decode("utf-8", errors="ignore")
-
-
-def _literal(node) -> str:
-    value = _text(node).strip()
-    if len(value) >= 2 and value[0] in {'"', "'", "`"} and value[-1] == value[0]:
-        return value[1:-1]
-    return ""
-
-
-def _first_literal(node) -> str:
-    if node is None:
-        return ""
-    for candidate in _walk(node):
-        if candidate.type in {"string", "template_string"}:
-            return _literal(candidate)
-    return ""
-
-
-def _line(node) -> int:
-    return int(node.start_point.row) + 1
-
-
-def _unique_occurrences(
-    items: list[SemanticOccurrence],
-) -> tuple[SemanticOccurrence, ...]:
-    unique: dict[str, SemanticOccurrence] = {}
-    for item in items:
-        unique.setdefault(item.name, item)
-    return tuple(unique.values())
diff --git a/uidetox/prototype.py b/uidetox/prototype.py
index 157cd60..ffce93e 100644
--- a/uidetox/prototype.py
+++ b/uidetox/prototype.py
@@ -26,6 +26,37 @@ def build_prototype_brief(redesign_set: RedesignSet, proposal_id: str) -> str:
         if sibling_distances
         else None
     )
+    parity_counts = dict(redesign_set.parity.get("counts", {}))
+    parity_findings = list(redesign_set.parity.get("findings", []))
+    source_evidence = [
+        (
+            f"- {item.get('file', 'unknown')}: "
+            + "; ".join(str(reason) for reason in item.get("reasons", []))
+        )
+        for item in proposal.source_evidence
+    ]
+    migration_evidence = [
+        (
+            f"{item.get('order', '?')}. [{item.get('kind', 'step')}] "
+            f"{item.get('instruction', '')}"
+        )
+        for item in proposal.migration_plan
+    ]
+    trusted_migration_steps = [
+        str(item.get("instruction", ""))
+        for item in proposal.migration_plan
+        if item.get("kind") == "strategy"
+    ]
+    contract_evidence = [
+        (
+            f"- {item.get('contract', 'unknown')}: "
+            f"source={', '.join(item.get('source_modules', [])) or 'unknown'}; "
+            f"runtime={item.get('runtime_status', 'unknown')}"
+        )
+        for item in proposal.preserved_contract_evidence
+    ]
+    source_freshness = proposal.evidence_freshness.get("source", {})
+    runtime_freshness = proposal.evidence_freshness.get("runtime", {})

     lines = [
         f"# UIdetox Prototype Brief: {proposal.name}",
@@ -78,7 +109,7 @@ def build_prototype_brief(redesign_set: RedesignSet, proposal_id: str) -> str:
             "",
             "## Migration sequence",
             "",
-            *_numbered(proposal.migration_steps),
+            *_numbered(trusted_migration_steps),
             "",
             "## Prototype operating rules",
             "",
@@ -98,15 +129,55 @@ def build_prototype_brief(redesign_set: RedesignSet, proposal_id: str) -> str:
             f"Target: {redesign_set.target}",
             "Source targets:",
             *_bullets(proposal.source_targets),
+            "Affected source modules with evidence:",
+            *(source_evidence or ["- None mapped."]),
+            "Dependency-aware migration plan:",
+            *(migration_evidence or ["- None mapped."]),
             "Contracts to preserve:",
             *_bullets(proposal.preserved_contracts),
+            "Preserved contract evidence:",
+            *(contract_evidence or ["- None mapped."]),
+            "Evidence freshness:",
+            f"- Source: {source_freshness.get('status', 'unknown')}",
+            f"- Runtime: {runtime_freshness.get('status', 'unknown')}",
+            (
+                "- Runtime stale reason: "
+                + str(runtime_freshness.get("stale_reason"))
+                if runtime_freshness.get("stale_reason")
+                else "- Runtime stale reason: none"
+            ),
+            "Feasi

[diff truncated]
        ```
