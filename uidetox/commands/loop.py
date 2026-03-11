"""Loop command: bootstraps the autonomous UIdetox remediation cycle.

Flow (from desloppify architecture):

  1. SCAN CODEBASE -> generate score (static + subjective)
  2. TARGET SCORE? -> YES: finish | NO: continue
  3. FIX LOOP:
     a. Make Plan   (uidetox next -- prioritise issues)
     b. Fix Issue   (agent applies fix)
     c. Update Plan (uidetox batch-resolve -- re-assess remaining)
     -> MORE FIXES? loop back to 3a
  4. RE-SCAN -> back to step 1
"""

import argparse
import pathlib
import subprocess
import sys
import uuid

from uidetox.state import load_config, save_config, load_state, ensure_uidetox_dir
from uidetox.tooling import detect_all
from uidetox.memory import get_patterns, get_notes, get_session, get_last_scan, save_session, log_progress
from uidetox.utils import compute_design_score


def run(args: argparse.Namespace):
    target = getattr(args, "target", 95)
    ensure_uidetox_dir()

    # ---- Auto-detect tooling ----
    config = load_config()
    if not config.get("tooling"):
        print("Auto-detecting project tooling...")
        profile = detect_all()
        config["tooling"] = profile.to_dict()
        save_config(config)

    # Store target in config for scan to reference
    config["target_score"] = target
    save_config(config)

    state = load_state()
    issues = state.get("issues", [])
    resolved = len(state.get("resolved", []))
    tooling = config.get("tooling", {})
    has_mechanical = tooling.get("typescript") or tooling.get("linter") or tooling.get("formatter")

    # ---- Codebase sizing ----
    frontend_exts = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".html", ".css", ".scss", ".sass"}
    exclude_dirs = {"node_modules", ".git", "dist", "build", ".next", "out", ".uidetox"}
    frontend_count = sum(
        1 for p in pathlib.Path('.').rglob('*')
        if p.is_file() and p.suffix in frontend_exts
        and not any(d in p.parts for d in exclude_dirs)
    )
    unique_files = len(set(i.get("file", "") for i in issues))
    spread = unique_files if unique_files > 0 else (frontend_count // 5)
    auto_parallel = max(1, min(5, spread))
    is_orchestrator = getattr(args, "orchestrator", False) or frontend_count > 15

    # ---- Git workspace isolation ----
    if config.get("auto_commit"):
        _ensure_session_branch()

    # ---- Header ----
    print()
    print("=" * 60)
    print("  UIdetox Autonomous Loop")
    print("=" * 60)
    print(f"  Target: {target}  |  Queue: {len(issues)}  |  Resolved: {resolved}")
    print(f"  Files: {frontend_count}  |  Orchestrator: {'yes' if is_orchestrator else 'no'}")
    print()

    # ---- Autonomous directive ----
    print("  SYSTEM DIRECTIVE: You are in FULL AUTONOMOUS LOOP MODE.")
    print(f"  Iterate until Score >= {target} and Queue is empty.")
    print("  DO NOT stop to ask permission. DO NOT summarize between fixes.")
    print()

    # ---- Continuation context ----
    session = get_session()
    last_scan = get_last_scan()
    if session or last_scan:
        print("-" * 60)
        print("  CONTINUATION CONTEXT")
        print("-" * 60)
        if session:
            phase = session.get('phase', 'unknown')
            last_cmd = session.get('last_command', 'none')
            fixed = session.get('issues_fixed_this_session', 0)
            print(f"  Last phase: {phase}  |  Last cmd: {last_cmd}  |  Fixed: {fixed}")
            if session.get("last_component"):
                print(f"  Last component: {session['last_component']}")
        if last_scan:
            ts = last_scan.get('timestamp', 'unknown')[:19]
            found = last_scan.get('total_found', 0)
            top = last_scan.get('top_files', [])[:3]
            print(f"  Last scan: {ts}  |  Found: {found}")
            if top:
                print(f"  Hottest: {', '.join(top)}")
        print("  Resume: skip completed stages and pick up where you left off.")
        print()

    # ---- Memory bank injection ----
    patterns = get_patterns()
    notes = get_notes()
    if patterns or notes:
        print("-" * 60)
        print("  MEMORY BANK (obey these during the loop)")
        print("-" * 60)
        for idx, p in enumerate(patterns, 1):
            print(f"  {idx}. [Pattern] {p['pattern']}")
        for idx, n in enumerate(notes, 1):
            print(f"  {idx}. [Note] {n['note']}")
        print()

    # ---- Full-stack integration ----
    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])
    if backends or databases or apis:
        layers = []
        if backends:
            layers.append(f"backend={', '.join(b['name'] for b in backends)}")
        if databases:
            layers.append(f"db={', '.join(d['name'] for d in databases)}")
        if apis:
            layers.append(f"api={', '.join(a['name'] for a in apis)}")
        print(f"  Full-stack: {', '.join(layers)}")
        print("  Enforce DTO alignment, type safety, error surfacing across layers.")
        print()

    # ---- Auto-commit awareness ----
    if config.get("auto_commit"):
        print("  AUTO-COMMIT ON: batch-resolve creates one commit per component.")
        print()

    # ==================================================================
    # THE LOOP PROTOCOL (3 stages matching desloppify architecture)
    # ==================================================================
    print("=" * 60)
    print("  THE LOOP PROTOCOL")
    print("=" * 60)
    print()

    # ---- STAGE 1: SCAN ----
    print("  STAGE 1: SCAN CODEBASE")
    print("  " + "-" * 40)
    if has_mechanical:
        print("    1a. Run `uidetox check --fix`  (tsc -> lint -> format)")
    print("    1b. Run `uidetox scan --path .`")
    print("        This runs the static analyzer AND prompts subjective review.")
    print("        Both mechanical issues and subjective analysis happen together.")
    if is_orchestrator:
        print(f"    1c. Orchestrator: `uidetox subagent --stage-prompt observe --parallel {auto_parallel}`")
        print(f"        Launch sub-agents to read files in parallel shards.")
        print(f"        Then: `uidetox subagent --stage-prompt diagnose`")
    print()

    # ---- STAGE 2: FIX LOOP ----
    print("  STAGE 2: FIX LOOP (repeat until queue empty)")
    print("  " + "-" * 40)
    print()
    print("    +-------------------------------------------------------+")
    print("    |  2a. MAKE PLAN    `uidetox next`                      |")
    print("    |      Get highest-priority component batch with        |")
    print("    |      SKILL.md rules injected.                         |")
    print("    |                                                       |")
    print("    |  2b. FIX ISSUE    Apply fixes properly.               |")
    print("    |      Read ALL files in the component first.           |")
    print("    |      Large refactors and small fixes -- equal energy. |")
    print("    |      Use design skills as needed:                     |")
    print("    |        uidetox polish/animate/colorize/harden <path>  |")
    print("    |                                                       |")
    print("    |  2c. UPDATE PLAN  `uidetox batch-resolve IDs --note`  |")
    print("    |      `uidetox check --fix`  (quality gate)            |")
    print("    |      `uidetox status`       (check score)             |")
    print("    |                                                       |")
    print("    |  MORE FIXES? -> loop back to 2a. No pauses.          |")
    print("    +-------------------------------------------------------+")

    if is_orchestrator:
        print()
        print(f"    Orchestrator mode: distribute fixes across sub-agents:")
        print(f"      `uidetox subagent --stage-prompt fix --parallel {auto_parallel}`")
    print()

    # ---- STAGE 3: RE-SCAN ----
    print("  STAGE 3: RE-SCAN (outer loop)")
    print("  " + "-" * 40)
    print("    When queue is empty:")
    print("    3a. Run `uidetox rescan`        (fresh static analysis)")
    print("    3b. Run `uidetox review`        (subjective quality review)")
    print("    3c. Run `uidetox review --score <N>`  (record score)")
    print("    3d. Run `uidetox status`        (check blended score)")
    print(f"    3e. Score >= {target}? -> `uidetox finish`")
    print(f"        Score < {target}?  -> back to STAGE 2")
    print()

    # ---- QUICK REFERENCE ----
    print("-" * 60)
    print("  QUICK REFERENCE")
    print("-" * 60)
    print("  Discovery : scan, detect, show, viz, tree, zone")
    print("  Mechanical: check --fix, tsc, lint, format, autofix")
    print("  Issues    : add-issue, plan, next, resolve, batch-resolve, suppress")
    print("  Skills    : audit, critique, normalize, polish, distill, clarify")
    print("              optimize, harden, animate, colorize, bolder, quieter")
    print("              delight, extract, adapt, onboard")
    print("  Scoring   : status, review, history")
    print("  Session   : memory, rescan, finish")
    print("  Parallel  : subagent --stage-prompt <stage> --parallel N")
    print()

    # ==================================================================
    # AUTO-PHASE DETECTION: Tell the agent exactly where to start
    # ==================================================================
    scores = compute_design_score(state)
    blended = scores["blended_score"]
    queue_size = len(issues)

    print("=" * 60)
    print("  START HERE")
    print("=" * 60)

    if blended >= target and queue_size == 0:
        print(f"  Score: {blended} (>= {target}), Queue: EMPTY")
        print("  -> DONE. Run `uidetox finish`.")
    elif queue_size == 0 and blended < target:
        print(f"  Score: {blended} (< {target}), Queue: EMPTY")
        print("  -> STAGE 3: Run `uidetox rescan` to discover more issues.")
    elif queue_size > 0 and (session or last_scan):
        print(f"  Score: {blended}, Queue: {queue_size} issue(s)")
        print("  -> STAGE 2: Resuming. Run `uidetox next`.")
    elif queue_size > 0:
        print(f"  Score: {blended}, Queue: {queue_size} issue(s)")
        print("  -> STAGE 2: Run `uidetox next` to start fixing.")
    else:
        if has_mechanical:
            print("  -> STAGE 1: Run `uidetox check --fix` then `uidetox scan --path .`")
        else:
            print("  -> STAGE 1: Run `uidetox scan --path .`")

    print()

    # Log the loop invocation
    log_progress("loop_start", f"target={target}, score={blended}, queue={queue_size}, orchestrator={is_orchestrator}")


def _ensure_session_branch():
    """Create or resume a UIdetox session branch for workspace isolation."""
    try:
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        if not current.startswith("uidetox-session-"):
            session_id = str(uuid.uuid4()).split("-")[0]
            branch = f"uidetox-session-{session_id}"
            print(f"  Git: switching to session branch {branch}")
            subprocess.run(["git", "checkout", "-b", branch], check=True)
        else:
            print(f"  Git: resuming session branch {current}")
    except subprocess.CalledProcessError:
        print("  Git: not initialized or branching failed. Proceeding without isolation.")
