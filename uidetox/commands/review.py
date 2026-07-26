"""Capture evidence-bound subjective design review."""

import argparse
import sys
from typing import Any

from uidetox.findings import current_evidence_hashes
from uidetox.frontend_map import FrontendMap, load_frontend_map
from uidetox.state import ensure_uidetox_dir, load_config, load_state, save_state
from uidetox.utils import now_iso
from uidetox.visual_semantics import project_visual_evidence_status

_CAPS = {"A": 40, "B": 30, "C": 20, "D": 10}


def run(args: argparse.Namespace) -> None:
    config = load_config()
    visual = project_visual_evidence_status(
        config,
        required=(True if getattr(args, "require_visual_evidence", False) else None),
        manifest_path=getattr(args, "visual_evidence_file", None),
    )
    if visual.required and not visual.ready:
        print(f"Error: visual evidence is {visual.state}.", file=sys.stderr)
        for reason in visual.reasons:
            print(f"  - {reason}", file=sys.stderr)
        raise SystemExit(1)

    dimensions = {
        key: getattr(args, f"dimension_{key.lower()}", None) for key in _CAPS
    }
    if any(value is not None for value in dimensions.values()):
        _store_structured_review(args, dimensions)
        return
    if (score := getattr(args, "score", None)) is not None:
        _store_subjective_score(score)
        return
    _print_review_brief(visual, _load_review_map())


def _store_structured_review(
    args: argparse.Namespace, dimensions: dict[str, int | None]
) -> None:
    errors = [
        f"{key} must be 0-{cap}"
        for key, cap in _CAPS.items()
        if not isinstance(dimensions[key], int) or not 0 <= dimensions[key] <= cap
    ]
    rationale = str(getattr(args, "rationale", "") or "").strip()
    reviewer = str(getattr(args, "reviewer", "") or "").strip()
    required_lists = {
        "finding_link": list(getattr(args, "finding_link", None) or []),
        "region_link": list(getattr(args, "region_link", None) or []),
        "route": list(getattr(args, "route", None) or []),
        "state": list(getattr(args, "state", None) or []),
        "viewport": list(getattr(args, "viewport", None) or []),
    }
    if not rationale:
        errors.append("--rationale is required")
    if not reviewer:
        errors.append("--reviewer is required")
    errors.extend(
        f"--{name.replace('_', '-')} is required"
        for name, values in required_lists.items()
        if not values
    )
    if errors:
        print("Error: " + "; ".join(errors), file=sys.stderr)
        raise SystemExit(1)

    scores = {key: int(value) for key, value in dimensions.items() if value is not None}
    record: dict[str, Any] = {
        "dimensions": scores,
        "score": sum(scores.values()),
        "rationale": rationale,
        "reviewer": reviewer,
        "finding_links": required_lists["finding_link"],
        "region_links": required_lists["region_link"],
        "routes": required_lists["route"],
        "states": required_lists["state"],
        "viewports": required_lists["viewport"],
        "evidence_hashes": current_evidence_hashes(),
        "stale": False,
        "timestamp": now_iso(),
    }
    _save_review(record)
    print(f"✅ Structured subjective review recorded: {record['score']}/100")


def _store_subjective_score(score: int) -> None:
    """Persist legacy scalar input as incomplete, non-qualifying review evidence."""
    if not isinstance(score, int) or not 0 <= score <= 100:
        print(f"Error: score must be between 0 and 100, got {score}.", file=sys.stderr)
        raise SystemExit(1)
    _save_review(
        {
            "score": score,
            "legacy": True,
            "stale": True,
            "timestamp": now_iso(),
        }
    )
    print(f"⚠️  Legacy score recorded: {score}/100; structured A/B/C/D review required.")


def _save_review(record: dict[str, Any]) -> None:
    ensure_uidetox_dir()
    state = load_state()
    previous = state.get("subjective")
    history = list(previous.get("history", [])) if isinstance(previous, dict) else []
    history.append(dict(record))
    state["subjective"] = {**record, "history": history}
    save_state(state)


def _load_review_map() -> FrontendMap | None:
    try:
        return load_frontend_map()
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return None


def _print_review_brief(
    visual: Any,
    frontend_map: FrontendMap | None = None,
) -> None:
    print("UIdetox structured subjective review")
    print("  A Visual design 0-40 | B System 0-30 | C Craft 0-20 | D Architecture 0-10")
    print("  Record scores with --dimension-a/b/c/d, --rationale, and --reviewer.")
    if visual.state != "missing":
        print(f"  Visual evidence: {visual.state} ({visual.comparisons} cases)")
        if visual.incomplete_viewports:
            print("  Incomplete viewports: " + ", ".join(visual.incomplete_viewports))
        for artifact in visual.reviewer_artifacts:
            if artifact.get("status") == "generated":
                print(f"  {artifact.get('kind')}: {artifact.get('path')}")
        for region in visual.top_changed_regions[:5]:
            print(
                f"  {region.get('case_id')}/{region.get('region_id')}: "
                f"{region.get('pixels_changed', 0)} px"
            )
        for warning in visual.warnings:
            print(f"  Warning: {warning}")
    if frontend_map is None:
        print("  Runtime map: missing")
        return
    evidence = frontend_map.evidence
    captures = evidence.get("runtime_capture_matrix", [])
    if isinstance(captures, list):
        for capture in captures:
            if not isinstance(capture, dict):
                continue
            viewport = capture.get("viewport", {})
            viewport_name = (
                viewport.get("name", "")
                if isinstance(viewport, dict)
                else viewport
            )
            print(
                "  Capture: "
                f"{capture.get('scenario', 'default')}/"
                f"{capture.get('state', 'initial')} "
                f"{viewport_name} {capture.get('status', 'unknown')}"
            )
    screenshots = evidence.get("runtime_screenshots", [])
    if isinstance(screenshots, list):
        for screenshot in screenshots:
            print(f"  Screenshot: {screenshot}")
    semantic = evidence.get("runtime_semantic_coverage", {})
    if isinstance(semantic, dict):
        print(
            "  Paint coverage: "
            f"{semantic.get('paint_resolved', 0)} resolved; "
            f"Paint unresolved: {semantic.get('paint_unresolved', 0)}; "
            f"{semantic.get('paint_unobserved', 0)} unobserved"
        )
    findings = evidence.get("runtime_findings", [])
    if isinstance(findings, list):
        for finding in findings[:10]:
            if isinstance(finding, dict):
                print(
                    f"  Finding: {finding.get('code', 'unknown')} "
                    f"{finding.get('selector', '')}".rstrip()
                )
    for node in frontend_map.nodes:
        if not node.kind.startswith("runtime_") or node.kind == "runtime_page":
            continue
        targets = node.metadata.get("source_targets", [])
        if not isinstance(targets, list) or not targets:
            continue
        print(
            f"  Region: {node.id} {node.metadata.get('selector', '')} "
            f"-> {', '.join(str(target) for target in targets)}"
        )
