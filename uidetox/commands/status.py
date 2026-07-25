"""Project health and canonical finalization eligibility."""

import argparse
import json
import subprocess
import sys

from uidetox.findings import (
    EligibilityContext,
    current_evidence_hashes,
    current_verification_fresh,
    evaluate_eligibility,
)
from uidetox.state import load_config, load_state
from uidetox.visual_semantics import project_visual_evidence_status


def _git_context() -> tuple[str, bool]:
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return branch, dirty
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "", True


def eligibility_status(
    state: dict,
    config: dict,
    *,
    visual_ready: bool = True,
) -> dict:
    branch, dirty = _git_context()
    evidence_hashes = current_evidence_hashes()
    context = EligibilityContext(
        target_score=int(config.get("target_score", 95)),
        current_branch=branch,
        session_branch=(branch if branch.startswith("uidetox-session-") else "uidetox-session-*"),
        dirty=dirty,
        verification_fresh=current_verification_fresh() and visual_ready,
        require_session_branch=True,
        evidence_hashes=evidence_hashes,
    )
    return evaluate_eligibility(state, context).to_dict()


def run(args: argparse.Namespace) -> None:
    state, config = load_state(), load_config()
    visual = project_visual_evidence_status(
        config,
        required=(True if getattr(args, "require_visual_evidence", False) else None),
        manifest_path=getattr(args, "visual_evidence_file", None),
    )
    eligibility = eligibility_status(
        state,
        config,
        visual_ready=not visual.required or visual.ready,
    )
    scores = eligibility["score"]
    issues, resolved = state.get("issues", []), state.get("resolved", [])
    stats = state.get("stats", {})
    payload = {
        "design_score": scores["blended_score"],
        "objective_score": scores["objective_score"],
        "subjective_score": scores["subjective_score"],
        "qualified_coverage": scores["qualified_coverage"],
        "total_issues": len(issues),
        "total_resolved": len(resolved),
        "total_found": stats.get("total_found", len(issues) + len(resolved)),
        "scans_run": stats.get("scans_run", 0),
        "last_scan": state.get("last_scan"),
        "eligibility": eligibility,
        "visual_evidence": visual.to_dict(),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2))
    else:
        print("UIdetox health")
        print(f"  Design score : {scores['blended_score']}/100")
        print(f"  Coverage     : {scores['qualified_coverage']:.0%}")
        print(f"  Pending      : {len(issues)}")
        print(f"  Resolved     : {len(resolved)}")
        print(f"  Visual       : {visual.state}")
        print(f"  Finalizable  : {'yes' if eligibility['eligible'] else 'no'}")
        for blocker in eligibility["blockers"]:
            print(f"    - {blocker['code']}: {blocker['message']}")
    if visual.required and not visual.ready:
        raise SystemExit(1)
