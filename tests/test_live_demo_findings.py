from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

from uidetox.analyzer import analyze_directory
from uidetox.analyzer_engine import analyze_file
from uidetox.commands import scan as scan_command
from uidetox.frontend_map import (
    load_frontend_map,
    map_frontend,
    save_frontend_map,
)
from uidetox.project_map import ProjectMap
from uidetox.redesign import RedesignBrief, propose_redesigns
from uidetox.workflow import (
    PhaseDefinition,
    WorkflowContext,
    WorkflowInputs,
    in_process_adapters,
)


def _issue_ids(issues: list[dict]) -> set[str]:
    return {str(issue["id"]) for issue in issues}


def _write_full_stack_demo(tmp_path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text(
        """
<!doctype html>
<html lang="en">
  <head>
    <link rel="stylesheet" href="/styles.css">
    <script src="/app.js" defer></script>
  </head>
  <body>
    <form id="task-form">
      <label for="task-title">Task title</label>
      <input id="task-title" name="title" type="text">
      <button type="submit">Add task</button>
    </form>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )
    (frontend / "app.js").write_text(
        """
const form = document.getElementById("task-form");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Test task" }),
  });
});
fetch("/api/tasks");
""".strip(),
        encoding="utf-8",
    )
    (frontend / "styles.css").write_text(
        """
form { width: 100%; }
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
  }
}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/api/tasks": {
                        "get": {"responses": {"200": {"description": "ok"}}},
                        "post": {"responses": {"201": {"description": "created"}}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_native_html_label_for_is_not_treated_as_react_html_for(tmp_path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<label for="email">Email</label><input id="email" type="email">',
        encoding="utf-8",
    )

    assert "ORPHANED_LABEL_SLOP" not in _issue_ids(analyze_file(html))


def test_jsx_label_for_does_not_mask_missing_html_for(tmp_path) -> None:
    jsx = tmp_path / "Form.jsx"
    jsx.write_text(
        '<label for="email">Email</label><input id="email" type="email" />',
        encoding="utf-8",
    )

    assert "ORPHANED_LABEL_SLOP" in _issue_ids(analyze_file(jsx))


def test_external_submit_listener_satisfies_native_html_form(tmp_path) -> None:
    _write_full_stack_demo(tmp_path)

    issues = analyze_directory(str(tmp_path / "frontend"))

    assert "FORM_NO_SUBMIT_SLOP" not in _issue_ids(issues)


def test_unbound_native_html_form_remains_actionable(tmp_path) -> None:
    _write_full_stack_demo(tmp_path)
    (tmp_path / "frontend" / "app.js").write_text(
        'fetch("/api/tasks");',
        encoding="utf-8",
    )

    issues = analyze_directory(str(tmp_path / "frontend"))

    assert "FORM_NO_SUBMIT_SLOP" in _issue_ids(issues)


def test_reduced_motion_important_overrides_are_not_specificity_abuse(
    tmp_path,
) -> None:
    css = tmp_path / "styles.css"
    css.write_text(
        """
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; }
}
""".strip(),
        encoding="utf-8",
    )

    assert "IMPORTANT_ABUSE_SLOP" not in _issue_ids(analyze_file(css))


def test_reduced_motion_non_motion_important_remains_actionable(tmp_path) -> None:
    css = tmp_path / "styles.css"
    css.write_text(
        """
@media (prefers-reduced-motion: reduce) {
  .warning { color: red !important; }
}
""".strip(),
        encoding="utf-8",
    )

    assert "IMPORTANT_ABUSE_SLOP" in _issue_ids(analyze_file(css))


def test_reduced_motion_animation_override_is_not_self_contradictory(
    tmp_path,
) -> None:
    css = tmp_path / "styles.css"
    css.write_text(
        """
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; }
}
""".strip(),
        encoding="utf-8",
    )

    assert "CSS_IMPORTANT_ANIMATION_SLOP" not in _issue_ids(analyze_file(css))


def test_css_percentages_are_not_treated_as_fabricated_metrics(tmp_path) -> None:
    css = tmp_path / "styles.css"
    css.write_text("form { width: 100%; }", encoding="utf-8")

    assert "ROUND_NUMBER_SLOP" not in _issue_ids(analyze_file(css))


def test_scoped_frontend_map_reconciles_against_project_wide_backend(
    tmp_path,
) -> None:
    _write_full_stack_demo(tmp_path)

    frontend_map = map_frontend(tmp_path, "frontend")
    project_map = ProjectMap.from_dict(frontend_map.project_map)

    assert len(project_map.frontend_operations) == 2
    assert len(project_map.backend_operations) == 2
    assert project_map.counts == {
        "frontend_only": 0,
        "backend_only": 0,
        "method_mismatch": 0,
        "unresolved": 0,
    }


def test_scoped_scan_reconciles_against_project_wide_backend(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _write_full_stack_demo(tmp_path)
    monkeypatch.chdir(tmp_path)
    config = {
        "tooling": {
            "package_manager": None,
            "typescript": None,
            "linter": None,
            "formatter": None,
            "frontend": [],
            "backend": [],
            "database": [],
            "api": [{"name": "OpenAPI"}],
        }
    }
    monkeypatch.setattr(scan_command, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scan_command, "load_config", lambda: config)
    monkeypatch.setattr(scan_command, "analyze_directory", lambda *args, **kwargs: [])

    scan_command.run(Namespace(path="frontend", since=None, output="table"))

    output = capsys.readouterr().out
    parity_line = next(
        line.strip()
        for line in output.splitlines()
        if "Full-stack operation parity:" in line
    )
    assert parity_line == (
        "Full-stack operation parity: frontend-only=0, backend-only=0, "
        "method-mismatch=0, unresolved=0."
    )


def test_fresh_scoped_scan_detects_tooling_from_project_root(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _write_full_stack_demo(tmp_path)
    monkeypatch.chdir(tmp_path)
    config: dict = {}
    detected_paths: list[Path] = []

    class DetectedProfile:
        def to_dict(self) -> dict:
            return {
                "package_manager": None,
                "typescript": None,
                "linter": None,
                "formatter": None,
                "frontend": [],
                "backend": [],
                "database": [],
                "api": [{"name": "OpenAPI"}],
            }

    def detect(path) -> DetectedProfile:
        detected_paths.append(Path(path).resolve())
        return DetectedProfile()

    monkeypatch.setattr(scan_command, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scan_command, "load_config", lambda: config)
    monkeypatch.setattr(scan_command, "detect_all", detect)
    monkeypatch.setattr(scan_command, "save_config", lambda _config: None)
    monkeypatch.setattr(scan_command, "analyze_directory", lambda *args, **kwargs: [])

    scan_command.run(Namespace(path="frontend", since=None, output="table"))

    output = capsys.readouterr().out
    assert detected_paths == [tmp_path.resolve()]
    assert "Full-stack operation parity: frontend-only=0, backend-only=0" in output


def test_html_asset_dependencies_reach_redesign_source_targets(tmp_path) -> None:
    _write_full_stack_demo(tmp_path)

    frontend_map = map_frontend(tmp_path, "frontend")
    proposal = propose_redesigns(
        frontend_map,
        RedesignBrief(target="frontend", variants=1),
    ).proposals[0]

    assert {
        "frontend/index.html",
        "frontend/app.js",
        "frontend/styles.css",
    }.issubset(proposal.source_targets)


def test_project_root_map_resolves_web_root_assets_beside_html(tmp_path) -> None:
    _write_full_stack_demo(tmp_path)

    frontend_map = map_frontend(tmp_path)
    proposal = propose_redesigns(
        frontend_map,
        RedesignBrief(target=".", variants=1),
    ).proposals[0]

    assert {
        "frontend/index.html",
        "frontend/app.js",
        "frontend/styles.css",
    }.issubset(proposal.source_targets)


def test_workflow_semantic_map_preserves_scoped_runtime_map(tmp_path) -> None:
    _write_full_stack_demo(tmp_path)
    map_path = tmp_path / ".uidetox" / "frontend-map.json"
    scoped = map_frontend(tmp_path, "frontend")
    scoped = replace(
        scoped,
        evidence={
            **scoped.evidence,
            "runtime_observed": True,
            "runtime_status": "current",
            "runtime_views": [{"viewport": "desktop"}],
        },
    )
    save_frontend_map(scoped, map_path)

    phase = PhaseDefinition(
        id="semantic_map",
        adapter="semantic_map",
        dependencies=(),
        input_keys=(),
        artifact_kinds=("frontend_map", "project_map"),
    )
    context = WorkflowContext(
        root=tmp_path,
        inputs=WorkflowInputs("source", "queue", "design", "verification"),
        state={},
        phase=phase,
    )
    in_process_adapters().run(phase, context)

    refreshed = load_frontend_map(map_path)
    assert refreshed.target == "frontend"
    assert refreshed.evidence["runtime_observed"] is True
    assert refreshed.evidence["runtime_status"] == "current"
    assert refreshed.evidence["runtime_views"] == [{"viewport": "desktop"}]
