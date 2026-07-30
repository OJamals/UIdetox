"""Invocation-scoped analyzer semantic-fact performance contracts."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from uidetox import analyzer_engine, analyzer_interactions
from uidetox.analyzer import analyze_directory, analyze_file
from uidetox.analyzer_interactions import class_list_has_interaction_state
from uidetox.findings import Finding

_EXPECTED_STATIC_ANALYSIS_FINDING_COUNT = 37
_EXPECTED_STATIC_ANALYSIS_SEMANTIC_SHA256 = (
    "ffbcbbcd56db9e1ecad3dbc26f231091fa2b721b86e7aa01b980fb6e7c3acd07"
)


def _write_static_analysis_fixture(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    package_specs = (("package-a", 15), ("package-b", 16))
    for package_name, component_count in package_specs:
        package = root / package_name
        package.mkdir()
        package_json = package / "package.json"
        package_json.write_text("{}", encoding="utf-8")
        files.append(package_json)
        stylesheet = package / "styles.css"
        stylesheet.write_text(
            """
.primary:hover,
.primary:is(:focus, :focus-visible),
button:hover,
button:focus-visible {
  color: navy;
}
.action {
  &:hover { color: blue; }
  &:focus-visible { outline: 2px solid; }
}
mybutton:hover { color: red; }
/* .comment-state:hover { color: green; } */
.literal::before { content: ".string-state:hover"; }
""".strip(),
            encoding="utf-8",
        )
        files.append(stylesheet)
        for index in range(component_count):
            class_name = ("primary", "action", "missing")[index % 3]
            component = package / f"Button{index:02d}.tsx"
            component.write_text(
                (
                    f"export function Button{index}() {{\n"
                    f'  return <button className="{class_name}">Save {index}</button>;\n'
                    "}\n"
                ),
                encoding="utf-8",
            )
            files.append(component)
        extra = (
            package / "vite.config.ts"
            if package_name == "package-a"
            else package / "Broken.tsx"
        )
        extra.write_text(
            (
                "export default { server: { proxy: { '/api': "
                "{ target: 'http://localhost:4000' } } } };"
                if package_name == "package-a"
                else "export function Broken( { return <main>;"
            ),
            encoding="utf-8",
        )
        files.append(extra)
    assert len(files) == 37
    return tuple(files)


def _normalize_fixture_value(value: object, root: Path) -> object:
    if isinstance(value, str):
        return value.replace(str(root.resolve()), "<ROOT>")
    if isinstance(value, dict):
        return {
            key: _normalize_fixture_value(item, root) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_fixture_value(item, root) for item in value]
    return value


def _ordered_projection(
    findings: list[Finding],
    root: Path,
) -> tuple[tuple[object, ...], ...]:
    projection = []
    for finding in findings:
        source = dict(finding.source_anchor)
        path = Path(str(source.get("path", "")))
        relative = path.relative_to(root).as_posix()
        projection.append(
            (
                finding.fingerprint,
                finding.detector_id,
                finding.code,
                relative,
                int(source.get("line", 0)),
                int(source.get("column", 0)),
                finding.message,
                _normalize_fixture_value(dict(finding.evidence), root),
            )
        )
    return tuple(projection)


def _semantic_projection_sha256(
    projection: tuple[tuple[object, ...], ...],
) -> str:
    normalized = tuple(row[1:] for row in projection)
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_static_analysis_ordered_projection_is_exact_and_repeatable(
    tmp_path: Path,
) -> None:
    _write_static_analysis_fixture(tmp_path)

    first = _ordered_projection(analyze_directory(str(tmp_path)), tmp_path)
    second = _ordered_projection(analyze_directory(str(tmp_path)), tmp_path)

    assert first == second
    assert len(first) == _EXPECTED_STATIC_ANALYSIS_FINDING_COUNT
    assert (
        _semantic_projection_sha256(first) == _EXPECTED_STATIC_ANALYSIS_SEMANTIC_SHA256
    )


def test_directory_scan_inventories_stylesheets_once_per_package_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_static_analysis_fixture(tmp_path)
    path_type = type(tmp_path)
    original_rglob = path_type.rglob
    lock = threading.Lock()
    inventories: list[Path] = []

    def count_rglob(path: Path, pattern: str):
        if pattern == "*.css":
            with lock:
                inventories.append(path.resolve())
        return original_rglob(path, pattern)

    monkeypatch.setattr(path_type, "rglob", count_rglob)

    analyze_directory(str(tmp_path))

    assert inventories == [
        (tmp_path / "package-a").resolve(),
        (tmp_path / "package-b").resolve(),
    ]


def test_standalone_file_scan_builds_one_local_stylesheet_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "app"
    package.mkdir()
    (package / "package.json").write_text("{}", encoding="utf-8")
    (package / "styles.css").write_text(
        ".primary:hover { color: navy; }",
        encoding="utf-8",
    )
    component = package / "Button.tsx"
    component.write_text(
        'export const Button = () => <button className="primary">Save</button>;',
        encoding="utf-8",
    )
    path_type = type(tmp_path)
    original_rglob = path_type.rglob
    inventories = 0

    def count_rglob(path: Path, pattern: str):
        nonlocal inventories
        if pattern == "*.css":
            inventories += 1
        return original_rglob(path, pattern)

    monkeypatch.setattr(path_type, "rglob", count_rglob)

    analyze_file(component)

    assert inventories == 1


def test_stylesheet_fact_build_scans_full_source_constant_times(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    source = "\n".join(
        f".state-{index}:hover {{ color: navy; }}" for index in range(200)
    )
    (tmp_path / "styles.css").write_text(source, encoding="utf-8")
    original_regex_functions = {
        name: getattr(analyzer_interactions.re, name)
        for name in ("search", "findall", "finditer")
    }
    full_source_scans = 0

    def count_full_source_scans(function):
        def wrapped(pattern: str, string: str, flags: int = 0):
            nonlocal full_source_scans
            if string == source:
                full_source_scans += 1
            return function(pattern, string, flags)

        return wrapped

    for name, function in original_regex_functions.items():
        monkeypatch.setattr(
            analyzer_interactions.re,
            name,
            count_full_source_scans(function),
        )

    facts = analyzer_interactions._build_stylesheet_facts(tmp_path)

    assert len(facts.class_states) == 200
    assert full_source_scans <= 1 + len(analyzer_interactions._INTERACTION_STATE_GROUPS)


def test_stylesheet_facts_preserve_selector_state_semantics(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    component = tmp_path / "Button.tsx"
    component.write_text("", encoding="utf-8")
    (tmp_path / "styles.css").write_text(
        """
.direct[data-kind="primary"]:hover { color: navy; }
.nested { &:focus-visible { outline: 2px solid; } }
.comma:is(.one, .two):hover, .other:hover { color: blue; }
.outer:is(.inner:focus):focus-visible { outline: 2px solid; }
.hover-outer:is(.hover-inner:hover):hover { color: navy; }
:where(button, a):focus-visible { outline: 2px solid; }
mybutton:hover { color: red; }
/* .comment-state:hover { color: green; } */
.literal::before { content: ".string-state:hover"; }
""".strip(),
        encoding="utf-8",
    )

    assert class_list_has_interaction_state("direct", component, "hover", "button")
    assert class_list_has_interaction_state("nested", component, "focus", "button")
    assert class_list_has_interaction_state("comma", component, "hover", "button")
    assert class_list_has_interaction_state("inner", component, "focus", "button")
    assert class_list_has_interaction_state("hover-inner", component, "hover", "button")
    assert class_list_has_interaction_state("missing", component, "focus", "button")
    assert not class_list_has_interaction_state("missing", component, "hover", "button")
    assert class_list_has_interaction_state(
        "comment-state", component, "hover", "section"
    )
    assert class_list_has_interaction_state(
        "string-state", component, "hover", "section"
    )
    assert class_list_has_interaction_state(
        "bg-blue-500 hover:bg-blue-600",
        component,
        "hover",
        "button",
    )


def test_stylesheet_context_resets_after_worker_exception(tmp_path: Path) -> None:
    _write_static_analysis_fixture(tmp_path)
    observed_contexts: list[object] = []

    def fail_analysis(
        _path: Path,
        *,
        design_variance: int,
    ) -> list[Finding]:
        assert design_variance == 8
        observed_contexts.append(analyzer_interactions._STYLESHEET_CONTEXT.get())
        raise RuntimeError("synthetic analyzer failure")

    with pytest.raises(RuntimeError, match="synthetic analyzer failure"):
        analyzer_engine.analyze_directory(
            str(tmp_path),
            _analyze_file=fail_analysis,
        )

    assert observed_contexts
    assert all(context is not None for context in observed_contexts)
    assert analyzer_interactions._STYLESHEET_CONTEXT.get() is None
