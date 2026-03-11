"""Loop command: instructs the agent to enter autonomous self-propagation.

This command bootstraps the full UIdetox loop:
1. Auto-detects tooling (if not already done)
2. Runs mechanical checks with iterative auto-fix
3. Triggers a full scan
4. Enters the autonomous fix loop until target score is reached
"""

import argparse
from uidetox.state import load_config, save_config, load_state, ensure_uidetox_dir
from uidetox.tooling import detect_all
from uidetox.memory import get_patterns, get_notes


def run(args: argparse.Namespace):
    target = getattr(args, "target", 95)

    ensure_uidetox_dir()

    # Auto-detect tooling if not already done
    config = load_config()
    if not config.get("tooling"):
        print("Auto-detecting project tooling...")
        profile = detect_all()
        config["tooling"] = profile.to_dict()
        save_config(config)
        pm = profile.package_manager or "none"
        ts = profile.typescript.config_file if profile.typescript else "no"
        lint = profile.linter.name if profile.linter else "none"
        fmt = profile.formatter.name if profile.formatter else "none"
        print(f"  Found: pkg={pm}, tsc={ts}, lint={lint}, fmt={fmt}\n")

    state = load_state()
    issues = state.get("issues", [])
    resolved = len(state.get("resolved", []))
    
    # Auto-calculate optimal parallel count from unique files in queue
    unique_files = len(set(i.get("file", "") for i in issues))
    auto_parallel = max(1, min(5, unique_files))  # 1-5 based on file spread

    print("================================================================")
    print("          UIdetox Autonomous Loop — Full Bootstrap             ")
    print("================================================================")
    print()
    print(f"  Target Score : {target}")
    print(f"  Current Queue: {len(issues)} issue(s)")
    print(f"  Resolved     : {resolved} so far")
    print()
    print("SYSTEM DIRECTIVE TO THE AI AGENT:")
    print("You are now in FULL AUTONOMOUS LOOP MODE.")
    print(f"You must relentlessly improve this codebase until Score >= {target} and Queue is empty.")
    print()
    print("DO NOT stop to ask the user for permission.")
    print("DO NOT ask 'should I continue?' — the answer is always YES.")
    print("DO NOT summarize progress between issues — just fix and move on.")
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("        THE AUTONOMOUS LOOP PROTOCOL     ")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    tooling = config.get("tooling", {})
    has_mechanical = tooling.get("typescript") or tooling.get("linter") or tooling.get("formatter")

    # Inject Memory Bank
    patterns = get_patterns()
    notes = get_notes()
    if patterns or notes:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("      [ MEMORY BANK INJECTION ]          ")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("The following architectural patterns and notes MUST BE OBEYED")
        print("during your autonomous detoxing loop context:")
        if patterns:
            for idx, p in enumerate(patterns):
                print(f"  {idx+1}. [Pattern] {p['pattern']}")
        if notes:
            for idx, n in enumerate(notes):
                print(f"  {idx+1}. [Note] {n['note']}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()

    # Auto-commit awareness
    auto_commit = config.get("auto_commit", False)
    if auto_commit:
        print("📦 AUTO-COMMIT is ON — every `uidetox resolve` atomically commits the fix to git.")
        print()

    if has_mechanical:
        print("PHASE 0 — MECHANICAL FIX (run once at start)")
        print("  Run: uidetox check --fix")
        print("  This iteratively auto-fixes formatting and lint errors,")
        print("  then queues remaining compiler/lint errors as T1 issues.")
        print()

    if len(issues) == 0:
        print("PHASE 1 — INITIAL SCAN (queue is empty, need issues)")
        print("  Run: uidetox scan --path .")
        print("  Read every frontend file. Check SKILL.md anti-patterns.")
        print("  For each issue found:")
        print("    uidetox add-issue --file <path> --tier <T1-T4> --issue <desc> --fix-command <cmd>")
        print()

    print("PHASE 2 — THE FIX LOOP (repeat until done)")
    print()
    print("  Step 1: Check baseline")
    print(f"          → Run `uidetox status`")
    print(f"          → Score >= {target} AND Queue Empty? → DONE. Exit loop.")
    print(f"          → Queue Empty but Score < {target}?  → Run `uidetox rescan`")
    print()
    print("  Step 2: Clear the easy wins")
    print("          → Run `uidetox autofix`")
    print("          → Apply all safe T1 changes listed, then `uidetox resolve <ID> --note \"...\"`")
    print()
    print("  Step 3: Deep Work")
    print("          → Run `uidetox next`")
    print("          → This yields a BATCH of issues for a specific file.")
    print("          → Read the file. Fix ALL issues in the batch in one go. Follow SKILL.md.")
    print("          → Verify no regressions.")
    print("          → Run `uidetox resolve <ID> --note \"...\"` for each issue in the batch.")
    print("  Step 4: GOTO Step 1. No pauses. No questions.")
    print()
    print("PHASE 3 — DEEP REVIEW (when queue is empty but score < target)")
    print("  Run: uidetox review")
    print("  The agent must perform a subjective UX quality review.")
    print("  Check: visual hierarchy, emotional tone, composition balance.")
    print("  Queue any new design issues found, then re-enter PHASE 2.")
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    if has_mechanical:
        print("Agent: Begin with PHASE 0. Run `uidetox check --fix` now.")
    elif len(issues) == 0:
        print("Agent: Begin with PHASE 1. Run `uidetox scan --path .` now.")
    else:
        print("Agent: Begin with PHASE 2 Step 1. Run `uidetox status` now.")

    # Orchestrator mode: use sub-agents
    orchestrator = getattr(args, "orchestrator", False)
    if orchestrator:
        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("      ORCHESTRATOR MODE ENABLED          ")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()
        print("Instead of fixing everything directly, you will launch")
        print("ONE sub-agent per stage. This isolates concerns and improves quality.")
        print()
        print("For each stage (observe → diagnose → prioritize → fix → verify):")
        print()
        print(f"  1. Generate the stage prompt(s):")
        print(f"     uidetox subagent --stage-prompt <stage> --parallel {auto_parallel}")
        print()
        print(f"  2. Launch up to {auto_parallel} sub-agents (Agent tools) with the printed prompts.")
        print("     Each sub-agent gets completely isolated context — don't combine stages.")
        print("     Run them concurrently! Do not wait for Agent 1 to finish before launching Agent 2.")
        print()
        print(f"  3. When all {auto_parallel} sub-agents finish, record the results sequentially:")
        print("     uidetox subagent --record <session_id>")
        print()
        print("  4. Check progress and proceed to next stage:")
        print("     uidetox status")
        print()
        print("  5. Repeat for the next stage.")
        print()
        print("Key rules:")
        print("  - Launch massive parallel subagents simultaneously whenever multiple prompts are generated.")
        print("  - Check `uidetox status` between stages.")
        print("  - The FIX stage sub-agents safely avoid merge-conflicts since files are sharded across buckets.")
        print("  - The VERIFY stage should re-scan and confirm improvements.")
        print("  - After all 5 stages, check if target is met; if not, loop again.")
        print()
        print(f"Agent: Start by spawning a highly parallel scan swarm: uidetox subagent --stage-prompt observe --parallel {auto_parallel}")

