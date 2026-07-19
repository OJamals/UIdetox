"""Map command: persist semantic frontend structure for redesign planning."""

import argparse
import json
from collections import Counter
from pathlib import Path

from uidetox.frontend_map import map_frontend, save_frontend_map
from uidetox.runtime_observer import observe_frontend
from uidetox.state import get_project_root, get_uidetox_dir, load_config


def run(args: argparse.Namespace) -> None:
    root = get_project_root()
    target = getattr(args, "target", ".")
    runtime_requested = getattr(args, "runtime", False)
    screenshots_requested = getattr(args, "screenshots", False)
    if screenshots_requested and not runtime_requested:
        raise ValueError("--screenshots requires --runtime")

    runtime_observation = None
    if runtime_requested:
        config = load_config()
        urls = getattr(args, "urls", None) or [
            config.get("dev_server", "http://localhost:3000")
        ]
        screenshot_dir = (
            get_uidetox_dir() / "runtime-screenshots" if screenshots_requested else None
        )
        runtime_observation = observe_frontend(
            urls,
            screenshots_dir=screenshot_dir,
            timeout_ms=getattr(args, "timeout", 15_000),
        )
        if not runtime_observation.pages:
            detail = (
                runtime_observation.errors[0]
                if runtime_observation.errors
                else "no pages observed"
            )
            raise RuntimeError(f"Runtime observation failed: {detail}")

    frontend_map = map_frontend(root, target, runtime_observation)
    output_arg = getattr(args, "output", None)
    output_path = save_frontend_map(
        frontend_map,
        Path(output_arg) if output_arg else None,
    )

    if getattr(args, "json", False):
        print(json.dumps(frontend_map.to_dict(), indent=2, sort_keys=True))
        return

    counts = Counter(node.kind for node in frontend_map.nodes)
    frameworks = ", ".join(frontend_map.evidence.get("frameworks", [])) or "unknown"
    print("Frontend map created.")
    print(f"  Target      : {frontend_map.target}")
    print(f"  Frameworks  : {frameworks}")
    print(f"  Files       : {frontend_map.evidence.get('files_mapped', 0)}")
    print(f"  Components  : {counts['component']}")
    print(f"  Routes      : {counts['route']}")
    print(f"  Actions     : {counts['action']}")
    print(f"  Data sources: {counts['data']}")
    print(f"  Artifact    : {output_path}")
    if frontend_map.evidence.get("runtime_observed"):
        viewports = ", ".join(frontend_map.evidence.get("runtime_viewports", []))
        print(
            f"  Runtime     : {frontend_map.evidence.get('runtime_pages', 0)} page/view(s) ({viewports})"
        )
        runtime_errors = frontend_map.evidence.get("runtime_errors", [])
        if runtime_errors:
            print(
                f"  Warnings    : {len(runtime_errors)} runtime observation failure(s)"
            )
    else:
        print("  Runtime     : not observed; unknowns recorded in artifact")
