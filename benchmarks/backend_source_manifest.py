"""Relative benchmark for backend manifest-only discovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

import uidetox.contract_adapters as adapters
from uidetox.project_map import project_source_manifest

_EXPECTED_OBSERVATION_SHA256 = (
    "82f08419380a23fda5e32e119d548418c26bd975a391cd0cd858c27d894935dc"
)
_COUNTER_TARGETS = (
    "_python_code_positions",
    "_javascript_code_positions",
    "_extract_python_routes",
    "_extract_javascript_routes",
    "_extract_openapi",
)


def _materialize_fixture(root: Path) -> None:
    python_filler = "\n".join(f"STATIC_VALUE_{line} = {line}" for line in range(160))
    javascript_filler = "\n".join(
        f"const staticValue{line} = {line};" for line in range(160)
    )
    for index in range(32):
        python = root / "backend" / f"api_{index:02d}.py"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text(
            f"""
from fastapi import FastAPI
app = FastAPI()
@app.get("/items/{index}/{{item_id}}")
def item_{index}(item_id: str):
    return {{"id": item_id}}
{python_filler}
""".strip(),
            encoding="utf-8",
        )
        javascript = root / "backend" / f"router_{index:02d}.ts"
        javascript.write_text(
            f"""
import express from "express";
const router = express.Router();
router.post("/orders/{index}/:orderId", handler);
{javascript_filler}
""".strip(),
            encoding="utf-8",
        )
    for index in range(160):
        frontend = root / "frontend" / f"view_{index:03d}.tsx"
        frontend.parent.mkdir(parents=True, exist_ok=True)
        frontend.write_text(
            f"export const View{index} = () => <main>Item {index}</main>;",
            encoding="utf-8",
        )
    (root / "frontend" / "comment.ts").write_text(
        '// app.get("/comment-only", handler)',
        encoding="utf-8",
    )
    (root / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/health": {"get": {"responses": {"200": {"description": "ok"}}}}
                },
            }
        ),
        encoding="utf-8",
    )


def _observation_digest(root: Path) -> tuple[str, dict[str, str]]:
    observations, extraction = adapters.extract_backend_observations(root)
    projection = json.dumps(
        [asdict(observation) for observation in observations],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return (
        hashlib.sha256(projection).hexdigest(),
        dict(extraction["source_manifest"]),
    )


def _instrumented_call(
    root: Path,
    operation: Callable[[], dict[str, str]],
) -> tuple[float, dict[str, str], dict[str, int]]:
    counts = {
        "file_reads": 0,
        "ast_calls": 0,
        "code_position_calls": 0,
        "route_extractor_calls": 0,
    }
    path_type = type(root)
    original_read_text = path_type.read_text
    original_ast_parse = adapters.ast.parse
    resolved_root = root.resolve()

    def counted_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.resolve().is_relative_to(resolved_root):
            counts["file_reads"] += 1
        return original_read_text(path, *args, **kwargs)

    def counted_ast_parse(*args: object, **kwargs: object):
        counts["ast_calls"] += 1
        return original_ast_parse(*args, **kwargs)

    def counted_call(
        name: str,
        original: Callable[..., object],
    ) -> Callable[..., object]:
        counter = (
            "code_position_calls"
            if name.endswith("_code_positions")
            else "route_extractor_calls"
        )

        def call(*args: object, **kwargs: object) -> object:
            counts[counter] += 1
            return original(*args, **kwargs)

        return call

    started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(patch.object(path_type, "read_text", counted_read_text))
        stack.enter_context(patch.object(adapters.ast, "parse", counted_ast_parse))
        for name in _COUNTER_TARGETS:
            original = getattr(adapters, name)
            stack.enter_context(
                patch.object(adapters, name, counted_call(name, original))
            )
        result = operation()
    return time.perf_counter() - started, result, counts


def _full_extraction_manifest(root: Path) -> dict[str, str]:
    _, extraction = adapters.extract_backend_observations(root)
    return dict(extraction["source_manifest"])


def _median_counts(samples: list[dict[str, int]]) -> dict[str, int]:
    return {
        key: int(statistics.median(sample[key] for sample in samples))
        for key in samples[0]
    }


def run_benchmark(runs: int) -> int:
    if runs < 7:
        raise ValueError("--runs must be at least 7")
    with tempfile.TemporaryDirectory(prefix="uidetox-backend-manifest-") as directory:
        root = Path(directory)
        _materialize_fixture(root)
        expected_digest, expected_manifest = _observation_digest(root)
        if expected_digest != _EXPECTED_OBSERVATION_SHA256:
            raise RuntimeError(
                "Observation parity drift: "
                f"expected {_EXPECTED_OBSERVATION_SHA256}, found {expected_digest}"
            )
        if project_source_manifest(root) != expected_manifest:
            raise RuntimeError("Manifest-only discovery differs from full extraction.")

        _instrumented_call(root, lambda: _full_extraction_manifest(root))
        _instrumented_call(root, lambda: project_source_manifest(root))

        timings = {"full": [], "manifest": []}
        counters: dict[str, list[dict[str, int]]] = {"full": [], "manifest": []}
        for index in range(runs):
            order = ("full", "manifest") if index % 2 == 0 else ("manifest", "full")
            for label in order:
                operation = (
                    (lambda: _full_extraction_manifest(root))
                    if label == "full"
                    else (lambda: project_source_manifest(root))
                )
                elapsed, manifest, counts = _instrumented_call(root, operation)
                if manifest != expected_manifest:
                    raise RuntimeError(f"{label} manifest parity drift")
                timings[label].append(elapsed)
                counters[label].append(counts)

        full_median = statistics.median(timings["full"])
        manifest_median = statistics.median(timings["manifest"])
        speedup = full_median / manifest_median
        full_counts = _median_counts(counters["full"])
        manifest_counts = _median_counts(counters["manifest"])
        if manifest_counts["route_extractor_calls"] != 0:
            raise RuntimeError("Manifest-only path performed route extraction.")

        print(f"runs={runs}")
        print(f"qualified_sources={len(expected_manifest)}")
        print(f"full_median_seconds={full_median:.6f}")
        print(f"manifest_median_seconds={manifest_median:.6f}")
        print(f"speedup={speedup:.2f}x")
        print("full_calls=" + json.dumps(full_counts, sort_keys=True))
        print("manifest_calls=" + json.dumps(manifest_counts, sort_keys=True))
        print(f"observation_sha256={expected_digest}")
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
