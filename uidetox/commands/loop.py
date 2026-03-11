"""Loop command: instructs the agent to enter autonomous self-propagation.

This command bootstraps the full UIdetox loop:
1. Auto-detects tooling (if not already done)
2. Runs mechanical checks with iterative auto-fix
3. Triggers LLM-driven codebase exploration and design audit
4. Enters the autonomous fix loop with component-level batch commits
5. Deep review with subjective scoring
"""

import argparse
from uidetox.state import load_config, save_config, load_state, ensure_uidetox_dir
from uidetox.tooling import detect_all
from uidetox.memory import get_patterns, get_notes, get_session, get_last_scan, save_session, log_progress
import subprocess
import uuid
import sys


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

    # Auto-calculate codebase size and parallel count
    import pathlib
    frontend_exts = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".html", ".css", ".scss", ".sass"}
    exclude_dirs = {"node_modules", ".git", "dist", "build", ".next", "out", ".uidetox"}
    
    frontend_file_list = [
        p for p in pathlib.Path('.').rglob('*')
        if p.is_file() and p.suffix in frontend_exts and not any(excluded in p.parts for excluded in exclude_dirs)
    ]
    frontend_count = len(frontend_file_list)

    unique_files_in_queue = len(set(i.get("file", "") for i in issues))
    # If we have issues, scale based on the queue spread. Otherwise scale on total codebase size.
    spread = unique_files_in_queue if unique_files_in_queue > 0 else (frontend_count // 5)
    auto_parallel = max(1, min(5, spread))
    
    # Auto-enable orchestrator mode for large codebases (> 15 files)
    is_orchestrator = getattr(args, "orchestrator", False) or frontend_count > 15

    print("================================================================")
    print("          UIdetox Autonomous Loop — Full Bootstrap             ")
    print("================================================================")
    print()

    # --- Git Workspace Isolation ---
    if config.get("auto_commit"):
        try:
            current_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, check=True
            ).stdout.strip()

            if not current_branch.startswith("uidetox-session-"):
                session_id = str(uuid.uuid4()).split("-")[0]
                branch_name = f"uidetox-session-{session_id}"
                print(f"📦 Switching to temporary branch: {branch_name}")
                print("All AI edits will be grouped here to protect your workspace.")
                subprocess.run(["git", "checkout", "-b", branch_name], check=True)
            else:
                print(f"📦 Resuming active session branch: {current_branch}")
        except subprocess.CalledProcessError:
            print("⚠️  Warning: Git is not initialized or branching failed. Proceeding without isolation.")
    # -------------------------------

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

    # ── Continuation Context (auto-loaded from memory) ──
    session = get_session()
    last_scan = get_last_scan()
    has_prior_session = bool(session)

    if has_prior_session or last_scan:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("      [ CONTINUATION CONTEXT ]           ")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if session:
            print(f"  Last Phase     : {session.get('phase', 'unknown')}")
            print(f"  Last Command   : {session.get('last_command', 'none')}")
            if session.get("last_component"):
                print(f"  Last Component : {session['last_component']}")
            print(f"  Issues Fixed   : {session.get('issues_fixed_this_session', 0)} this session")
            if session.get("context"):
                print(f"  Context        : {session['context']}")
        if last_scan:
            print(f"  Last Scan      : {last_scan.get('timestamp', 'unknown')[:19]}")
            print(f"  Issues Found   : {last_scan.get('total_found', 0)}")
            top = last_scan.get("top_files", [])
            if top:
                print(f"  Hottest Files  : {', '.join(top[:3])}")
        print("  Resume: skip completed phases and pick up where you left off.")
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

    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])
    has_fullstack = backends or databases or apis

    if has_fullstack:
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("      [ FULL-STACK INTEGRATION ]         ")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("The following layers were detected in this project:")
        if backends: print(f"  Backend: {', '.join(b['name'] for b in backends)}")
        if databases: print(f"  Database: {', '.join(d['name'] for d in databases)}")
        if apis: print(f"  API: {', '.join(a['name'] for a in apis)}")
        print()
        print("During your deep work, you MUST ensure integration across these layers:")
        print("  - DTO shapes match exactly between frontend and backend")
        print("  - Frontend forms respect database constraints and types")
        print("  - Backend errors are properly surfaced in UI (loading/error/empty states)")
        print("  - API network boundaries are type-safe")
        print("  - NEVER hallucinate data structures — read actual backend source files")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()

    # Auto-commit awareness
    auto_commit = config.get("auto_commit", False)
    if auto_commit:
        print("📦 AUTO-COMMIT is ON — `batch-resolve` creates one coherent commit per component.")
        print()

    # ================================================================
    # COMPLETE COMMAND REFERENCE
    # ================================================================
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("      [ AVAILABLE COMMANDS ]             ")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("  DISCOVERY & ANALYSIS:")
    print("    uidetox scan --path .          Static analysis (41 rules) + design audit prompt")
    print("    uidetox detect                 Auto-detect project tooling")
    print("    uidetox show [pattern]         Filter issues by file, tier, or ID")
    print("    uidetox viz                    Generate HTML heatmap of issues")
    print("    uidetox tree                   Terminal tree of issue density")
    print("    uidetox zone show              View file zone classifications")
    print()
    print("  MECHANICAL FIXES:")
    print("    uidetox check --fix            Run tsc → lint → format (auto-fix)")
    print("    uidetox tsc                    TypeScript compiler check")
    print("    uidetox lint --fix             Run linter with auto-fix")
    print("    uidetox format --fix           Run formatter with auto-fix")
    print("    uidetox autofix                Batch-apply all safe T1 quick fixes")
    print()
    print("  ISSUE MANAGEMENT:")
    print('    uidetox add-issue --file <f> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
    print("    uidetox plan                   View/reorder issue queue")
    print("    uidetox next                   Get next component batch with SKILL.md context")
    print('    uidetox resolve <id> --note "..."         Resolve single issue')
    print('    uidetox batch-resolve ID1 ID2 --note "..."  Resolve batch (1 commit)')
    print("    uidetox suppress <pattern>     Permanently silence matching issues")
    print()
    print("  DESIGN SKILLS (invoke for targeted work):")
    print("    uidetox audit <target>         Technical quality checks (a11y, perf, theming)")
    print("    uidetox critique <target>      UX design review (hierarchy, emotion)")
    print("    uidetox normalize <target>     Align with design system standards")
    print("    uidetox polish <target>        Final pre-ship quality pass")
    print("    uidetox distill <target>       Strip to essence, remove complexity")
    print("    uidetox clarify <target>       Improve unclear UX copy")
    print("    uidetox optimize <target>      Performance improvements")
    print("    uidetox harden <target>        Error handling, i18n, edge cases")
    print("    uidetox animate <target>       Add purposeful motion")
    print("    uidetox colorize <target>      Introduce strategic color")
    print("    uidetox bolder <target>        Amplify boring designs")
    print("    uidetox quieter <target>       Tone down overly bold designs")
    print("    uidetox delight <target>       Add moments of joy")
    print("    uidetox extract <target>       Pull into reusable components")
    print("    uidetox adapt <target>         Adapt for different devices")
    print("    uidetox onboard <target>       Design onboarding flows")
    print()
    print("  SCORING & REVIEW:")
    print("    uidetox status                 Health dashboard with blended Design Score")
    print("    uidetox status --json          Machine-readable status output")
    print("    uidetox review                 LLM subjective quality review prompt")
    print("    uidetox review --score <N>     Record subjective score (0-100)")
    print("    uidetox history                View score progression over time")
    print()
    print("  SESSION MANAGEMENT:")
    print("    uidetox memory show            View persistent memory bank")
    print('    uidetox memory pattern "..."   Save an architectural pattern')
    print('    uidetox memory note "..."      Save a persistent note')
    print("    uidetox rescan                 Clear queue + fresh static analysis")
    print("    uidetox finish                 Squash-merge session branch")
    print()
    print("  ORCHESTRATOR (sub-agent pipeline):")
    print(f"    uidetox subagent --stage-prompt <stage> --parallel {auto_parallel}")
    print("    uidetox subagent --list        List all sub-agent sessions")
    print("    uidetox subagent --show <id>   Show session details")
    print("    uidetox subagent --record <id> Mark session completed")
    print()
    print("  You may invoke ANY of these commands at any point during the loop")
    print("  based on your analysis of the codebase. Use design skills when")
    print("  specific components need targeted attention.")
    print()

    # ================================================================
    # PHASE 0: MECHANICAL FIX
    # ================================================================
    if has_mechanical:
        print("╔═══════════════════════════════════════════════════╗")
        print("║ PHASE 0 — MECHANICAL FIX (run once at start)     ║")
        print("╚═══════════════════════════════════════════════════╝")
        print("  Run: uidetox check --fix")
        print("  This iteratively auto-fixes formatting and lint errors,")
        print("  then queues remaining compiler/lint errors as T1 issues.")
        print()

    # ================================================================
    # PHASE 1: EXPLORE & AUDIT (LLM-Dynamic Analysis)
    # ================================================================
    print("╔═══════════════════════════════════════════════════╗")
    print("║ PHASE 1 — EXPLORE & AUDIT (LLM-dynamic analysis) ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()
    print("  This is the CRITICAL phase that differentiates good detoxing from surface-level fixes.")
    print("  You MUST systematically read and analyze the codebase BEFORE fixing anything.")
    print()
    print("  Step 1.1: Run static analysis")
    print("    → Run: uidetox scan --path .")
    print("    → This runs the 41-rule deterministic analyzer and auto-queues anti-patterns.")
    print()
    
    
    from uidetox.commands.subagent_cmd import _handle_stage_prompt # type: ignore

    if is_orchestrator:
        print("  Step 1.2: Orchestrator Mode — Parallel Sub-Agent Exploration")
        print("    → DO NOT manually read files. Act as a manager.")
        print("    → Launch the following sub-agents in parallel using the generated native prompts below:")
        print()
        _handle_stage_prompt("observe", auto_parallel)
        print()
        print(f"    → Wait for ALL sub-agents above to finish.")
        print(f"    → Then run: uidetox subagent --stage-prompt diagnose")
        print(f"    → Launch the diagnosis agent. It will queue the issues.")
        print(f"    → Record them: uidetox subagent --record <session_id>")
        print()
    else:
        print("  Step 1.2: LLM-driven codebase exploration & Code Intelligence")
        print("    → Use GitNexus to map the UI architecture (if terminal is available):")
        print("      1. Run `npx gitnexus analyze .` (or use the GitNexus MCP server)")
        print("      2. Use `npx gitnexus query <concept>` to find relevant execution flows")
        print("      3. Use `npx gitnexus impact <target>` before touching core components")
        print("    → Read EVERY frontend file in the project (tsx, jsx, css, html, vue, svelte)")
        print("    → For each file, systematically observe:")
        print("        • Typography: font families, sizes, weights, line heights")
        print("        • Colors: all color values (hex, rgb, hsl, oklch, CSS vars, Tailwind classes)")
        print("        • Layout: grid systems, flex patterns, max-widths, padding/margin patterns")
        print("        • Components: UI patterns used (cards, modals, heroes, navbars, forms)")
        print("        • Motion: animations, transitions, hover/focus/active effects")
        print("        • States: loading, error, empty, disabled state handling")
        print("        • Accessibility: ARIA labels, focus indicators, semantic HTML")
        print("        • Content: placeholder data quality, copy tone, generic names")
        print()
        print("    → Verify changes are safe with `npx gitnexus detect_changes`")
        print()
        print("  Step 1.3: Design audit against SKILL.md")
        print("    → Read SKILL.md and compare your observations against its rules")
        print("    → For EACH issue found that wasn't caught by static analysis:")
        print('      uidetox add-issue --file <path> --tier <T1-T4> --issue "<desc>" --fix-command "<cmd>"')
        print()

    print(f"  Step {'1.3' if is_orchestrator else '1.4'}: Targeted design skill audits")
    print("    → Run design skills on components that need deep attention:")
    print("      uidetox audit <target>     — Technical quality (a11y, perf, theming)")
    print("      uidetox critique <target>  — UX review (hierarchy, emotion, composition)")
    print("    → Queue any additional issues found")
    print()

    if has_fullstack:
        print(f"  Step {'1.4' if is_orchestrator else '1.5'}: Full-stack integration audit")
        print("    → Read backend source files, API routes, and database schemas")
        print("    → Check DTO alignment, type safety across boundaries")
        print("    → Run: uidetox harden <target> for edge cases and error handling")
        print("    → Queue mismatches as issues")
        print()

    # ================================================================
    # PHASE 2: FIX LOOP (Component-Level)
    # ================================================================
    print("╔═══════════════════════════════════════════════════╗")
    print("║ PHASE 2 — THE FIX LOOP (component-level commits) ║")
    print("╚═══════════════════════════════════════════════════╝")
    print()
    print("  Step 1: Check baseline")
    print(f"          → Run `uidetox status`")
    print(f"          → Score >= {target} AND Queue Empty? → GOTO PHASE 4.")
    print(f"          → Queue Empty but Score < {target}?  → GOTO PHASE 3.")
    print()
    print("  Step 2: Clear the easy wins")
    print("          → Run `uidetox autofix`")
    print("          → Apply all safe T1 changes listed")
    print()
    print("  Step 3: Deep Work (component-level)")
    if is_orchestrator:
        print(f"          → Orchestrator Mode: Distribute the queue across parallel fix agents.")
        print(f"          → Run `uidetox subagent --stage-prompt fix --parallel {auto_parallel}`")
        print(f"          → Launch {auto_parallel} sub-agents in parallel with the printed fix prompts.")
        print(f"          → Wait for them to finish, then record them: `uidetox subagent --record <session_id>`")
    else:
        print("          → Run `uidetox next`")
        print("          → This yields a BATCH of all issues for a component/directory.")
        print("          → Read ALL files in the component. Fix ALL issues in one pass.")
    print("          → Follow SKILL.md design rules injected in the output.")
    print("          → Use targeted design skills as needed:")
    print("            uidetox normalize <target>  — align with design system")
    print("            uidetox polish <target>     — final quality pass")
    print("            uidetox animate <target>    — add motion")
    print("            uidetox colorize <target>   — introduce strategic color")
    print("            uidetox harden <target>     — error handling, edge cases")
    print("            uidetox distill <target>    — simplify over-complex components")
    print("            uidetox bolder <target>     — amplify boring designs")
    print("          → Verify no regressions.")
    print()
    print("  Step 4: Pre-Commit Quality Gate")
    print("          → Run `uidetox check --fix`")
    print("          → This auto-fixes formatting/linting and queues any new errors.")
    print()
    print("  Step 5: Batch Resolve (single coherent commit)")
    print('          → Run `uidetox batch-resolve ID1 ID2 ID3 ... --note "what you changed"`')
    print("          → This resolves all issues in the component and makes ONE git commit.")
    print()
    print("  Step 6: Record pattern knowledge")
    print('          → If you discovered a recurring pattern: uidetox memory pattern "description"')
    print('          → If you want to note something for future loops: uidetox memory note "note"')
    print()
    print("  Step 7: Loop")
    print("          → Run `uidetox next` again → GOTO Step 1. No pauses. No questions.")
    print()

    # ================================================================
    # PHASE 3: DEEP REVIEW
    # ================================================================
    print("╔═══════════════════════════════════════════════════╗")
    print("║ PHASE 3 — DEEP REVIEW (queue empty, score < tgt) ║")
    print("╚═══════════════════════════════════════════════════╝")
    print("  Step 1: Re-read every modified file and verify fixes match SKILL.md")
    print("  Step 2: Run `uidetox rescan` for fresh static analysis")
    print("  Step 3: Run targeted design skills on the weakest areas:")
    print("          uidetox critique <target>  — subjective UX review")
    print("          uidetox audit <target>     — technical quality audit")
    print("  Step 4: Run `uidetox review` — perform LLM subjective quality assessment")
    print("  Step 5: Record your score: `uidetox review --score <N>` (0-100)")
    print("  Step 6: Check `uidetox status` for the blended Design Score")
    print(f"  Step 7: Score >= {target}? → GOTO PHASE 4. Otherwise queue new issues → GOTO PHASE 2.")
    print()

    # ================================================================
    # PHASE 4: FINALIZE
    # ================================================================
    print("╔═══════════════════════════════════════════════════╗")
    print("║ PHASE 4 — FINALIZE                               ║")
    print("╚═══════════════════════════════════════════════════╝")
    print("  Step 1: Run `uidetox status` — confirm score and empty queue")
    print("  Step 2: Run `uidetox history` — review score progression")
    print("  Step 3: Run `uidetox finish` — squash-merge session branch")
    print("  Step 4: DONE. Exit the loop.")
    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    if has_mechanical:
        print("Agent: Begin with PHASE 0. Run `uidetox check --fix` now.")
    elif len(issues) == 0:
        if is_orchestrator:
            print("Agent: Begin with PHASE 1. Run `uidetox scan --path .` now, then launch the sub-agents (Step 1.2).")
        else:
            print("Agent: Begin with PHASE 1. Run `uidetox scan --path .` now, then systematically read every frontend file.")
    else:
        print("Agent: Begin with PHASE 2 Step 1. Run `uidetox status` now.")
