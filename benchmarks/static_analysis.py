"""Differential benchmark for invocation-scoped static-analysis facts."""

from __future__ import annotations

import argparse
import concurrent.futures
import functools
import hashlib
import json
import re
import statistics
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import Self
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from uidetox import analyzer_ast, analyzer_custom, analyzer_engine, source_facts
from uidetox import analyzer_interactions as interactions
from uidetox.findings import Finding


class _ImmediateFuture:
    def __init__(self, function: Callable[..., object], args: tuple[object, ...]):
        try:
            self._result = function(*args)
            self._error: BaseException | None = None
        except BaseException as error:  # noqa: BLE001
            self._result = None
            self._error = error

    def result(self) -> object:
        if self._error is not None:
            raise self._error
        return self._result


class _SequentialExecutor:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def submit(
        self,
        function: Callable[..., object],
        *args: object,
    ) -> _ImmediateFuture:
        return _ImmediateFuture(function, args)


def _materialize_fixture(root: Path) -> None:
    package_specs = (("package-a", 14), ("package-b", 13))
    file_count = 0
    for package_name, component_count in package_specs:
        package = root / package_name
        package.mkdir()
        (package / "package.json").write_text("{}", encoding="utf-8")
        file_count += 1
        selectors = [
            "a:hover { color: navy; }",
            "a:focus-visible { outline: 2px solid; }",
            "mybutton:hover { color: red; }",
            'output::before { content: ".string-state:hover"; }',
            "/* .comment-state:hover { color: red; } */",
        ]
        for class_index in range(36):
            if class_index % 3 == 0:
                selectors.append(
                    f".state-{class_index}:hover, "
                    f".state-{class_index}:focus-visible {{ color: navy; }}"
                )
            elif class_index % 3 == 1:
                selectors.append(
                    f".state-{class_index}[data-ready]:hover, "
                    f".state-{class_index}:is(.ready, .active):focus "
                    "{ color: teal; }"
                )
            else:
                selectors.append(
                    f".state-{class_index} {{ "
                    "&:hover { color: blue; } "
                    "&:focus-visible { outline: 2px solid; } "
                    "}"
                )
        (package / "states.css").write_text(
            "\n".join(selectors),
            encoding="utf-8",
        )
        file_count += 1
        semantic_classes = tuple(index for index in range(36) if index % 3 != 2)
        for component_index in range(component_count):
            component_classes = []
            for index in range(12):
                class_index = (component_index * 12 + index) % len(semantic_classes)
                component_classes.append(f"state-{semantic_classes[class_index]}")
            buttons = "\n".join(
                (
                    f'<button data-ready="true" className="{class_name}">'
                    f"Save {index}</button>"
                )
                for index, class_name in enumerate(component_classes)
            )
            (package / f"Buttons{component_index:02d}.tsx").write_text(
                "export function Buttons"
                f"{component_index}() {{ return <main>"
                '<div className="hover:bg-blue-500 focus:ring-2">Utility</div>'
                f"{buttons}</main>; }}",
                encoding="utf-8",
            )
            file_count += 1
        (package / "Malformed.tsx").write_text(
            "export function Broken( { return <button>Broken</button>",
            encoding="utf-8",
        )
        file_count += 1
        (package / "static.html").write_text(
            '<main><button class="state-0">Static</button></main>',
            encoding="utf-8",
        )
        file_count += 1
        (package / "vite.config.ts").write_text(
            "export default { server: { proxy: { '/api': "
            "{ target: 'http://localhost:4000' } } } };",
            encoding="utf-8",
        )
        file_count += 1
    assert file_count == 37


def _baseline_extract_source_facts(
    path: Path,
    content: str,
    *,
    parser_factory: source_facts.ParserFactory | None = None,
) -> source_facts.SourceFacts | None:
    """Frozen pre-change extractor with six independent syntax-tree walks."""
    extension = path.suffix.lower()
    parser = (parser_factory or source_facts.get_parser)(extension)
    if parser is None:
        return None
    try:
        tree = parser.parse(content.encode("utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001
        return None

    root_node = tree.root_node
    imports, aliases = source_facts._extract_imports(source_facts._walk(root_node))
    exports, default_component = source_facts._extract_exports(
        source_facts._walk(root_node),
        path,
    )
    bindings = source_facts._extract_bindings(source_facts._walk(root_node))
    callables = source_facts._extract_callables(source_facts._walk(root_node))
    calls = source_facts._extract_calls(source_facts._walk(root_node))
    network_calls, network_symbols = source_facts._classify_network_calls(
        aliases=aliases,
        bindings=bindings,
        callables=callables,
        calls=calls,
    )
    alias_map = {item.local: item.imported for item in aliases}
    react_aliases = tuple(item for item in aliases if item.source == "react")
    use_state_names = {
        "useState",
        "React.useState",
        *(item.local for item in react_aliases if item.imported == "useState"),
    }

    components = [default_component] if default_component is not None else []
    rendered_modules: list[str] = []
    rendered_bindings: list[source_facts.RenderFact] = []
    selectors: list[source_facts.SelectorFact] = []
    regions: list[source_facts.SourceOccurrence] = []
    actions: list[source_facts.SourceOccurrence] = []
    states: list[source_facts.SourceOccurrence] = []
    routes: list[source_facts.SourceOccurrence] = []
    config_routes: list[source_facts.SourceOccurrence] = []
    has_router_signal = False

    analyzer_state = source_facts._MutableAnalyzerState()
    for node in source_facts._walk(root_node):
        source_facts._collect_semantic_node(
            node,
            alias_map=alias_map,
            use_state_names=use_state_names,
            components=components,
            rendered_modules=rendered_modules,
            rendered_bindings=rendered_bindings,
            selectors=selectors,
            regions=regions,
            actions=actions,
            states=states,
            routes=routes,
            config_routes=config_routes,
        )
        if (
            node.type == "identifier"
            and source_facts._text(node) in source_facts._ROUTER_IDENTIFIERS
        ):
            has_router_signal = True
        if extension in source_facts._SCRIPT_EXTENSIONS:
            source_facts._collect_analyzer_node(node, analyzer_state)

    if has_router_signal:
        routes.extend(config_routes)
    parse_errors = bool(tree.root_node.has_error)
    return source_facts.SourceFacts(
        path=path,
        extension=extension,
        imports=tuple(dict.fromkeys(item for item in imports if item)),
        import_aliases=aliases,
        exports=exports,
        bindings=bindings,
        callables=callables,
        calls=calls,
        react_aliases=react_aliases,
        rendered_modules=tuple(dict.fromkeys(rendered_modules)),
        rendered_bindings=source_facts._unique_rendered_bindings(rendered_bindings),
        selectors=source_facts._unique_selectors(selectors),
        declared_ui_modules=source_facts._unique_occurrences(components),
        regions=tuple(regions),
        actions=tuple(actions),
        states=source_facts._unique_occurrences(states),
        network_calls=network_calls,
        network_symbols=network_symbols,
        endpoints=source_facts._unique_endpoints(
            [
                source_facts.EndpointFact(
                    item.url,
                    item.line,
                    item.method,
                    item.dynamic,
                )
                for item in network_calls
                if item.client_family in {"fetch", "axios", "ky", "http-wrapper"}
            ]
        ),
        routes=source_facts._unique_occurrences(routes),
        analyzer=analyzer_state.freeze(),
        extractor="tree-sitter",
        confidence=0.85 if parse_errors else 1.0,
        parse_errors=parse_errors,
    )


def _baseline_stylesheet_signature(
    root: Path,
) -> tuple[tuple[str, int, int], ...]:
    entries: list[tuple[str, int, int]] = []
    for stylesheet in root.rglob("*.css"):
        if not interactions._IGNORED_STYLE_DIRS.isdisjoint(
            stylesheet.relative_to(root).parts
        ):
            continue
        try:
            stat = stylesheet.stat()
        except OSError:
            continue
        entries.append((str(stylesheet), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(entries))


@functools.lru_cache(maxsize=64)
def _baseline_stylesheet_text(
    signature: tuple[tuple[str, int, int], ...],
) -> str:
    sources: list[str] = []
    for path, _, _ in signature:
        try:
            sources.append(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
    return "\n".join(sources)


def _baseline_tag_has_state(
    stylesheet: str,
    tag: str,
    states: tuple[str, ...],
) -> bool:
    state_pattern = "|".join(re.escape(state) for state in states)
    tag_pattern = re.compile(rf"(?<![\w-]){re.escape(tag)}(?![\w-])")
    for selector_list in re.findall(r"([^{}]+)\{", stylesheet):
        for selector in interactions._split_selector_list(selector_list):
            if re.search(rf":(?:{state_pattern})\b", selector) and tag_pattern.search(
                selector
            ):
                return True
    return False


def _baseline_class_list_has_interaction_state(
    classes: str,
    filepath: Path,
    state: str,
    tag: str,
) -> bool:
    utility_variants = {
        "hover": ("hover:",),
        "focus": ("focus:", "focus-visible:"),
    }[state]
    if interactions._uses_utility_classes(classes):
        return any(variant in classes for variant in utility_variants)
    states = ("focus", "focus-visible") if state == "focus" else ("hover",)
    stylesheet = _baseline_stylesheet_text(
        _baseline_stylesheet_signature(interactions._project_root(filepath))
    )
    if not stylesheet:
        return False
    if _baseline_tag_has_state(stylesheet, tag, states):
        return True
    state_pattern = "|".join(re.escape(item) for item in states)
    state_expression = rf":(?:{state_pattern})\b"
    for token in classes.split():
        escaped = re.escape(token)
        direct = (
            rf"\.{escaped}(?:\[[^\]]+\]|:[\w-]+(?:\([^)]*\))?)*"
            f"{state_expression}"
        )
        nested = rf"\.{escaped}\s*\{{[^{{}}]*&{state_expression}"
        if re.fullmatch(r"[A-Za-z_][\w-]*", token) and re.search(
            rf"(?:{direct}|{nested})",
            stylesheet,
            re.DOTALL,
        ):
            return True
    return False


def _projection(findings: list[Finding]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            finding.fingerprint,
            finding.detector_id,
            finding.code,
            dict(finding.source_anchor),
            finding.message,
            dict(finding.evidence),
        )
        for finding in findings
    )


def _projection_sha256(
    projection: tuple[tuple[object, ...], ...],
    root: Path,
) -> str:
    root_text = str(root.resolve())

    def normalize(value: object) -> object:
        if isinstance(value, str):
            return value.replace(root_text, "<ROOT>")
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value

    # Exact path-sensitive fingerprints remain in the in-process parity projection.
    # Cross-run digest uses normalized fingerprint inputs so temp roots do not drift.
    semantic_projection = [normalize(row[1:]) for row in projection]
    return hashlib.sha256(
        json.dumps(
            semantic_projection,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _run_sample(
    root: Path,
    *,
    baseline: bool,
    sequential: bool,
    instrument: bool,
) -> tuple[
    float,
    tuple[tuple[object, ...], ...],
    dict[str, int],
]:
    counts = {
        "stylesheet_inventories": 0,
        "selector_list_parses": 0,
        "parser_calls": 0,
        "root_walks": 0,
        "nodes_visited": 0,
        "rule_calls": 0,
    }
    lock = threading.Lock()
    path_type = type(root)
    original_rglob = path_type.rglob
    original_split = interactions._split_selector_list
    original_get_parser = source_facts.get_parser
    original_walk = source_facts._walk
    original_rule = analyzer_engine._analyze_rule
    walk_state = threading.local()

    def count_rglob(path: Path, pattern: str):
        if pattern == "*.css":
            with lock:
                counts["stylesheet_inventories"] += 1
        return original_rglob(path, pattern)

    def count_split(selector_list: str) -> tuple[str, ...]:
        with lock:
            counts["selector_list_parses"] += 1
        return original_split(selector_list)

    def count_get_parser(extension: str):
        parser = original_get_parser(extension)
        if parser is None:
            return None

        class _Parser:
            def parse(self, content: bytes):
                with lock:
                    counts["parser_calls"] += 1
                return parser.parse(content)

        return _Parser()

    def count_walk(node: object):
        depth = getattr(walk_state, "depth", 0)
        outermost = depth == 0
        walk_state.depth = depth + 1
        if outermost and getattr(node, "parent", None) is None:
            with lock:
                counts["root_walks"] += 1
        try:
            for item in original_walk(node):
                if outermost:
                    with lock:
                        counts["nodes_visited"] += 1
                yield item
        finally:
            walk_state.depth -= 1

    def count_rule(*args: object, **kwargs: object):
        with lock:
            counts["rule_calls"] += 1
        return original_rule(*args, **kwargs)

    started = time.perf_counter()
    with ExitStack() as stack:
        if instrument:
            stack.enter_context(patch.object(path_type, "rglob", count_rglob))
            stack.enter_context(
                patch.object(interactions, "_split_selector_list", count_split)
            )
            stack.enter_context(
                patch.object(source_facts, "get_parser", count_get_parser)
            )
            stack.enter_context(patch.object(source_facts, "_walk", count_walk))
            stack.enter_context(
                patch.object(analyzer_engine, "_analyze_rule", count_rule)
            )
        if baseline:
            stack.enter_context(
                patch.object(
                    analyzer_engine,
                    "_stylesheet_context_for_files",
                    lambda _files: {},
                )
            )
            stack.enter_context(
                patch.object(
                    analyzer_engine,
                    "_activate_stylesheet_context",
                    lambda _context: nullcontext(),
                )
            )
            stack.enter_context(
                patch.object(
                    analyzer_engine,
                    "_stylesheet_scope",
                    lambda _filepath: nullcontext(),
                )
            )
            stack.enter_context(
                patch.object(
                    analyzer_ast,
                    "extract_source_facts",
                    _baseline_extract_source_facts,
                )
            )
            stack.enter_context(
                patch.object(
                    analyzer_custom,
                    "class_list_has_interaction_state",
                    _baseline_class_list_has_interaction_state,
                )
            )
        if sequential:
            stack.enter_context(
                patch.object(
                    concurrent.futures,
                    "ThreadPoolExecutor",
                    _SequentialExecutor,
                )
            )
        findings = analyzer_engine.analyze_directory(str(root))
    elapsed = time.perf_counter() - started
    return elapsed, _projection(findings), counts


def run_benchmark(runs: int) -> int:
    if runs < 7:
        raise ValueError("--runs must be at least 7")
    _baseline_stylesheet_text.cache_clear()
    with tempfile.TemporaryDirectory(prefix="uidetox-static-analysis-") as directory:
        root = Path(directory)
        _materialize_fixture(root)

        _, warm_baseline, _ = _run_sample(
            root,
            baseline=True,
            sequential=False,
            instrument=False,
        )
        _, warm_current, _ = _run_sample(
            root,
            baseline=False,
            sequential=False,
            instrument=False,
        )
        if warm_baseline != warm_current:
            raise RuntimeError("Warm threaded finding parity drift.")

        _, sequential_baseline, _ = _run_sample(
            root,
            baseline=True,
            sequential=True,
            instrument=False,
        )
        _, sequential_current, _ = _run_sample(
            root,
            baseline=False,
            sequential=True,
            instrument=False,
        )
        if sequential_baseline != sequential_current:
            raise RuntimeError("Sequential finding parity drift.")
        if sequential_current != warm_current:
            raise RuntimeError("Threaded/sequential finding order drift.")

        timings = {"baseline": [], "current": []}
        expected_projection = warm_current
        for index in range(runs):
            order = (
                ("baseline", "current") if index % 2 == 0 else ("current", "baseline")
            )
            for label in order:
                elapsed, projection, _counts = _run_sample(
                    root,
                    baseline=label == "baseline",
                    sequential=False,
                    instrument=False,
                )
                if projection != expected_projection:
                    raise RuntimeError(f"{label} ordered finding parity drift.")
                timings[label].append(elapsed)

        baseline_median = statistics.median(timings["baseline"])
        current_median = statistics.median(timings["current"])
        speedup = baseline_median / current_median
        _, baseline_projection, baseline_counts = _run_sample(
            root,
            baseline=True,
            sequential=False,
            instrument=True,
        )
        _, current_projection, current_counts = _run_sample(
            root,
            baseline=False,
            sequential=False,
            instrument=True,
        )
        if baseline_projection != current_projection:
            raise RuntimeError("Instrumented finding parity drift.")
        if current_counts["stylesheet_inventories"] > 2:
            raise RuntimeError(
                "Stylesheets inventoried more than once per package root."
            )
        if current_counts["root_walks"] != current_counts["parser_calls"]:
            raise RuntimeError(
                "Syntax-tree root materialization exceeded parser calls."
            )
        if baseline_counts["rule_calls"] != current_counts["rule_calls"]:
            raise RuntimeError("Rule-call parity drift.")

        print(f"runs={runs}")
        print("fixture_files=37")
        print(f"findings={len(expected_projection)}")
        print(f"baseline_median_seconds={baseline_median:.6f}")
        print(f"current_median_seconds={current_median:.6f}")
        print(f"speedup={speedup:.2f}x")
        print("baseline_counts=" + json.dumps(baseline_counts, sort_keys=True))
        print("current_counts=" + json.dumps(current_counts, sort_keys=True))
        print(f"semantic_sha256={_projection_sha256(expected_projection, root)}")
        print("threaded_sequential_parity=exact")
        if speedup < 1.8:
            print("FAIL: median speedup below 1.8x", file=sys.stderr)
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()
    return run_benchmark(args.runs)


if __name__ == "__main__":
    raise SystemExit(main())
