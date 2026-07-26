"""Path-isolated alternating benchmark for the runtime observer."""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

FIXTURES = ("generic", "controls", "geometry")
VOLATILE_RESULT_KEYS = frozenset(
    {
        "capture_id",
        "completed_at",
        "duration_ms",
        "generated_at",
        "screenshot",
        "started_at",
    }
)


def worker_command(
    python: Path,
    script: Path,
    *,
    expected_root: Path,
    forbidden_root: Path,
    fixture: str,
    node_count: int,
) -> list[str]:
    return [
        str(python),
        "-P",
        str(script.resolve()),
        "--worker",
        "--expected-root",
        str(expected_root.resolve()),
        "--forbidden-root",
        str(forbidden_root.resolve()),
        "--fixture",
        fixture,
        "--node-count",
        str(node_count),
    ]


def worker_environment(expected_root: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONPATH"] = str(expected_root.resolve())
    environment["PYTHONSAFEPATH"] = "1"
    return environment


def controller_python() -> Path:
    return Path(sys.executable).absolute()


def alternating_versions(pairs: int) -> Iterable[tuple[int, tuple[str, str]]]:
    for pair in range(1, pairs + 1):
        yield pair, (("base", "current") if pair % 2 else ("current", "base"))


def fixture_html(fixture: str, node_count: int) -> str:
    if fixture == "generic":
        body = "".join(
            f"<div><span>Item {index}</span></div>" for index in range(node_count)
        )
        style = ""
    elif fixture == "controls":
        body = "".join(
            (f'<button style="width:24px;height:24px">{index}</button>')
            for index in range(node_count)
        )
        style = ""
    elif fixture == "geometry":
        body = "".join(
            f'<button class="geometry-node">{index}</button>'
            for index in range(node_count)
        )
        style = (
            "<style>.geometry-node{position:absolute;left:0;top:0;"
            "width:100000000px;height:100000000px}</style>"
        )
    else:
        raise ValueError(f"Unknown fixture: {fixture}")
    return f"<!doctype html>{style}<main>{body}</main>"


def loaded_uidetox_module_files() -> dict[str, str]:
    return {
        name: str(Path(module_file).resolve())
        for name, module in sys.modules.items()
        if (name == "uidetox" or name.startswith("uidetox."))
        and (module_file := getattr(module, "__file__", None))
    }


def validate_import_provenance(
    provenance: Mapping[str, Any],
    expected_root: Path,
    forbidden_root: Path,
) -> None:
    expected = expected_root.resolve()
    forbidden = forbidden_root.resolve()
    if expected == forbidden:
        raise ValueError("Base and current roots collide.")
    if provenance.get("safe_path") is not True:
        raise ValueError("Worker did not enable Python safe-path mode.")
    if Path(str(provenance.get("expected_root", ""))).resolve() != expected:
        raise ValueError("Worker expected import root changed.")
    package_file = Path(str(provenance.get("package_file", ""))).resolve()
    if not package_file.is_relative_to(expected):
        raise ValueError("Imported uidetox package is outside expected root.")
    module_files = provenance.get("module_files")
    if not isinstance(module_files, Mapping) or not module_files:
        raise TypeError("Worker did not report imported uidetox modules.")
    if any(
        not Path(str(module_file)).resolve().is_relative_to(expected)
        for module_file in module_files.values()
    ):
        raise ValueError("Imported uidetox module is outside expected root.")
    raw_paths = provenance.get("sys_path")
    if not isinstance(raw_paths, list):
        raise TypeError("Worker did not report sys.path.")
    resolved_paths = {
        Path(path).resolve() for path in raw_paths if isinstance(path, str) and path
    }
    if expected not in resolved_paths:
        raise ValueError("Expected import root is absent from sys.path.")
    if forbidden in resolved_paths:
        raise ValueError("Worker sys.path contains forbidden checkout root.")
    cwd = Path(str(provenance.get("cwd", ""))).resolve()
    if cwd in resolved_paths or "" in raw_paths:
        raise ValueError("Worker sys.path contains its working directory.")


def validate_sample(
    sample: Mapping[str, Any],
    expected_root: Path,
    forbidden_root: Path,
    *,
    expected_emitted: int,
) -> None:
    provenance = sample.get("import")
    if not isinstance(provenance, Mapping):
        raise TypeError("Worker omitted import provenance.")
    validate_import_provenance(provenance, expected_root, forbidden_root)
    if sample.get("evaluate_count") != 1:
        raise ValueError("Benchmark requires exactly one page.evaluate.")
    coverage = sample.get("coverage")
    if not isinstance(coverage, Mapping):
        raise TypeError("Worker omitted runtime DOM coverage.")
    if coverage.get("budget") != expected_emitted:
        raise ValueError("Runtime DOM budget changed.")
    if coverage.get("emitted") != expected_emitted:
        raise ValueError("Runtime DOM emitted count changed.")
    if sample.get("element_count") != expected_emitted:
        raise ValueError("Runtime element count changed.")


def validate_pair(
    base: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    expected_emitted: int,
) -> None:
    if base.get("evaluate_count") != 1 or current.get("evaluate_count") != 1:
        raise ValueError("Benchmark requires one page.evaluate per sample.")
    if base.get("result_digest") != current.get("result_digest"):
        raise ValueError("Frozen/current canonical result mismatch.")
    if base.get("element_count") != current.get("element_count"):
        raise ValueError("Frozen/current element count mismatch.")
    for sample in (base, current):
        coverage = sample.get("coverage")
        if not isinstance(coverage, Mapping):
            raise TypeError("Worker omitted runtime DOM coverage.")
        if coverage.get("budget") != expected_emitted:
            raise ValueError("Frozen/current DOM budget mismatch.")
        if coverage.get("emitted") != expected_emitted:
            raise ValueError("Frozen/current emitted count mismatch.")
    if base.get("coverage") != current.get("coverage"):
        raise ValueError("Frozen/current runtime DOM coverage mismatch.")
    if base.get("status") != current.get("status"):
        raise ValueError("Frozen/current observation status mismatch.")


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    return {
        "samples": list(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "p90": _percentile(values, 0.9),
        "iqr": _percentile(values, 0.75) - _percentile(values, 0.25),
        "pstdev": statistics.pstdev(values),
    }


def _metric_summary(
    samples: Sequence[Mapping[str, Any]],
    key: str,
    gate_percent: float,
) -> dict[str, Any]:
    base_values = [
        float(sample[key]) for sample in samples if sample["version"] == "base"
    ]
    current_values = [
        float(sample[key]) for sample in samples if sample["version"] == "current"
    ]
    base = _distribution(base_values)
    current = _distribution(current_values)
    delta = ((current["median"] / base["median"]) - 1) * 100
    return {
        "base": base,
        "current": current,
        "delta_percent": delta,
        "gate_margin_percent": gate_percent - delta,
        "passed": delta <= gate_percent,
    }


def summarize_fixture(
    samples: Sequence[Mapping[str, Any]],
    *,
    gate_percent: float,
) -> dict[str, Any]:
    wall = _metric_summary(samples, "wall_seconds", gate_percent)
    evaluator = _metric_summary(samples, "evaluator_seconds", gate_percent)
    return {
        "sample_count": {
            version: sum(sample["version"] == version for sample in samples)
            for version in ("base", "current")
        },
        "wall_seconds": wall,
        "evaluator_seconds": evaluator,
        "passed": wall["passed"] and evaluator["passed"],
    }


def write_report(report: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + os.linesep,
        encoding="utf-8",
    )


def coverage_payload(coverage: Any) -> dict[str, Any]:
    return {
        key: getattr(coverage, key)
        for key in (
            "total",
            "candidates",
            "eligible",
            "emitted",
            "budget",
            "truncated",
        )
    }


def _canonicalize(value: Any, *, origin: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _canonicalize(item, origin=origin)
            for key, item in value.items()
            if key not in VOLATILE_RESULT_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item, origin=origin) for item in value]
    if isinstance(value, str) and origin:
        return value.replace(origin, "http://benchmark.invalid")
    return value


def _run_worker(args: argparse.Namespace) -> int:
    expected_root = Path(args.expected_root).resolve()
    forbidden_root = Path(args.forbidden_root).resolve()
    if expected_root == forbidden_root:
        raise ValueError("Base and current roots collide.")

    from playwright.sync_api import Page

    import uidetox
    from uidetox.runtime_observer import observe_frontend
    from uidetox.runtime_scenarios import VIEWPORT_REGISTRY

    provenance = {
        "safe_path": bool(sys.flags.safe_path),
        "expected_root": str(expected_root),
        "package_file": str(Path(uidetox.__file__).resolve()),
        "module_files": loaded_uidetox_module_files(),
        "sys_path": list(sys.path),
        "cwd": str(Path.cwd().resolve()),
    }
    validate_import_provenance(provenance, expected_root, forbidden_root)

    html = fixture_html(args.fixture, args.node_count)
    evaluate_count = 0
    evaluator_seconds = 0.0
    original_evaluate = Page.evaluate

    def measured_evaluate(self, expression, arg=None):
        nonlocal evaluate_count, evaluator_seconds
        started = time.perf_counter()
        try:
            return original_evaluate(self, expression, arg)
        finally:
            evaluate_count += 1
            evaluator_seconds += time.perf_counter() - started

    with tempfile.TemporaryDirectory(prefix="uidetox-benchmark-page-") as raw:
        page_root = Path(raw)
        page_root.joinpath("index.html").write_text(html, encoding="utf-8")

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return None

        handler = functools.partial(QuietHandler, directory=page_root)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        origin = f"http://127.0.0.1:{server.server_port}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        Page.evaluate = measured_evaluate
        try:
            started = time.perf_counter()
            observation = observe_frontend(
                f"{origin}/index.html",
                viewports=(VIEWPORT_REGISTRY["desktop"],),
                settle_ms=0,
            )
            wall_seconds = time.perf_counter() - started
        finally:
            Page.evaluate = original_evaluate
            server.shutdown()
            server.server_close()
            thread.join()

    provenance["module_files"] = loaded_uidetox_module_files()
    validate_import_provenance(provenance, expected_root, forbidden_root)
    canonical = json.dumps(
        _canonicalize(observation.to_dict(), origin=origin),
        separators=(",", ":"),
        sort_keys=True,
    )
    capture = observation.captures[0]
    payload = {
        "fixture": args.fixture,
        "wall_seconds": wall_seconds,
        "evaluator_seconds": evaluator_seconds,
        "evaluate_count": evaluate_count,
        "result_digest": hashlib.sha256(canonical.encode()).hexdigest(),
        "coverage": coverage_payload(capture.coverage),
        "element_count": len(observation.pages[0].elements),
        "status": observation.status,
        "import": provenance,
    }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    return 0


def _git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _materialize_ref(repo: Path, ref: str, destination: Path) -> str:
    sha = _git(repo, "rev-parse", f"{ref}^{{commit}}")
    process = subprocess.Popen(
        ["git", "archive", "--format=tar", sha],
        cwd=repo,
        stdout=subprocess.PIPE,
    )
    assert process.stdout is not None
    with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
        archive.extractall(destination, filter="data")
    if process.wait() != 0:
        raise RuntimeError(f"Could not archive frozen base {sha}.")
    return sha


def _invoke_worker(
    *,
    python: Path,
    script: Path,
    root: Path,
    forbidden_root: Path,
    fixture: str,
    node_count: int,
    cwd: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    completed = subprocess.run(
        worker_command(
            python,
            script,
            expected_root=root,
            forbidden_root=forbidden_root,
            fixture=fixture,
            node_count=node_count,
        ),
        cwd=cwd,
        env=worker_environment(root),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Benchmark worker failed ({completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("Benchmark worker emitted unexpected stdout.")
    result = json.loads(lines[0])
    if not isinstance(result, dict):
        raise TypeError("Benchmark worker did not emit a JSON object.")
    return result


def _run_controller(args: argparse.Namespace) -> int:
    if not args.base_ref:
        raise ValueError("Controller requires a frozen --base-ref.")
    script = Path(__file__).resolve()
    current_root = script.parents[1]
    python = controller_python()
    fixtures = tuple(dict.fromkeys(args.fixture or FIXTURES))
    if args.pairs < 1 or args.warmups < 0 or args.node_count < 1:
        raise ValueError(
            "Pairs and node count must be positive; warmups cannot be negative."
        )

    with tempfile.TemporaryDirectory(prefix="uidetox-benchmark-") as raw:
        temporary = Path(raw)
        base_root = temporary / "base"
        neutral = temporary / "neutral"
        base_root.mkdir()
        neutral.mkdir()
        base_sha = _materialize_ref(current_root, args.base_ref, base_root)
        if base_root.resolve() == current_root.resolve():
            raise ValueError("Frozen base and current roots collide.")

        roots = {"base": base_root, "current": current_root}
        warmups: list[dict[str, Any]] = []
        samples: list[dict[str, Any]] = []
        sequence = 0
        for fixture in fixtures:
            for warmup in range(1, args.warmups + 1):
                for version in ("base", "current"):
                    root = roots[version]
                    result = _invoke_worker(
                        python=python,
                        script=script,
                        root=root,
                        forbidden_root=roots[
                            "current" if version == "base" else "base"
                        ],
                        fixture=fixture,
                        node_count=args.node_count,
                        cwd=neutral,
                        timeout_seconds=args.timeout_seconds,
                    )
                    result.update(
                        {"version": version, "warmup": warmup, "fixture": fixture}
                    )
                    warmups.append(result)
            for pair, versions in alternating_versions(args.pairs):
                pair_samples: dict[str, dict[str, Any]] = {}
                for position, version in enumerate(versions, 1):
                    sequence += 1
                    root = roots[version]
                    forbidden = roots["current" if version == "base" else "base"]
                    result = _invoke_worker(
                        python=python,
                        script=script,
                        root=root,
                        forbidden_root=forbidden,
                        fixture=fixture,
                        node_count=args.node_count,
                        cwd=neutral,
                        timeout_seconds=args.timeout_seconds,
                    )
                    result.update(
                        {
                            "version": version,
                            "pair": pair,
                            "position": position,
                            "sequence": sequence,
                            "fixture": fixture,
                        }
                    )
                    validate_sample(
                        result,
                        root,
                        forbidden,
                        expected_emitted=args.expected_emitted,
                    )
                    samples.append(result)
                    pair_samples[version] = result
                validate_pair(
                    pair_samples["base"],
                    pair_samples["current"],
                    expected_emitted=args.expected_emitted,
                )

        summaries = {
            fixture: summarize_fixture(
                [sample for sample in samples if sample["fixture"] == fixture],
                gate_percent=args.gate_percent,
            )
            for fixture in fixtures
        }
        passed = all(
            summary["passed"]
            and summary["wall_seconds"]["gate_margin_percent"]
            >= args.required_margin_percent
            and summary["evaluator_seconds"]["gate_margin_percent"]
            >= args.required_margin_percent
            for summary in summaries.values()
        )
        report = {
            "schema_version": 1,
            "environment": {
                "python": str(python),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "safe_path_workers": True,
                "current_root": str(current_root),
                "current_sha": _git(current_root, "rev-parse", "HEAD"),
                "current_dirty": bool(
                    _git(current_root, "status", "--porcelain", "--untracked-files=all")
                ),
                "base_ref": args.base_ref,
                "base_sha": base_sha,
                "base_root": str(base_root),
                "neutral_cwd": str(neutral),
            },
            "config": {
                "fixtures": list(fixtures),
                "pairs": args.pairs,
                "warmups": args.warmups,
                "node_count": args.node_count,
                "expected_emitted": args.expected_emitted,
                "gate_percent": args.gate_percent,
                "required_margin_percent": args.required_margin_percent,
            },
            "warmups": warmups,
            "samples": samples,
            "summary": summaries,
            "passed": passed,
        }
        if args.output:
            write_report(report, Path(args.output).resolve())
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if passed else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref")
    parser.add_argument("--fixture", choices=FIXTURES, action="append")
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--node-count", type=int, default=3_200)
    parser.add_argument("--expected-emitted", type=int, default=3_000)
    parser.add_argument("--gate-percent", type=float, default=10.0)
    parser.add_argument("--required-margin-percent", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--expected-root", help=argparse.SUPPRESS)
    parser.add_argument("--forbidden-root", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.worker:
        if (
            not args.expected_root
            or not args.forbidden_root
            or not args.fixture
            or len(args.fixture) != 1
        ):
            raise ValueError("Worker requires exact roots and one fixture.")
        args.fixture = args.fixture[0]
        return _run_worker(args)
    if not args.base_ref:
        raise ValueError("Controller requires --base-ref.")
    return _run_controller(args)


if __name__ == "__main__":
    raise SystemExit(main())
