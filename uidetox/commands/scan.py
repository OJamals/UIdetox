"""Scan command — enhanced with tooling auto-detection and mechanical checks."""

import argparse
import uuid
from uidetox.analyzer import analyze_directory
from uidetox.commands.add_issue import _is_suppressed
from uidetox.state import add_issue, ensure_uidetox_dir, load_config, save_config, increment_scans
from uidetox.tooling import detect_all
from uidetox.history import save_run_snapshot


def run(args: argparse.Namespace):
    ensure_uidetox_dir()
    config = load_config()
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)

    # Auto-detect tooling if not already configured
    if not config.get("tooling"):
        profile = detect_all(args.path)
        config["tooling"] = profile.to_dict()
        save_config(config)

    tooling = config.get("tooling", {})

    print("╔══════════════════════════════╗")
    print("║      UIdetox Full Scan       ║")
    print("╚══════════════════════════════╝")
    print(f"Path: {args.path}")
    print(f"Vibe: Variance={variance}, Motion={intensity}, Density={density}")

    # Report detected tooling
    pm = tooling.get("package_manager")
    ts = tooling.get("typescript")
    linter = tooling.get("linter")
    fmt = tooling.get("formatter")
    backends = tooling.get("backend", [])
    databases = tooling.get("database", [])
    apis = tooling.get("api", [])

    print(f"\nDetected Tooling:")
    print(f"  Package Manager : {pm or 'none'}")
    print(f"  TypeScript      : {ts['config_file'] if ts else 'no'}")
    print(f"  Linter          : {linter['name'] if linter else 'none'}")
    print(f"  Formatter       : {fmt['name'] if fmt else 'none'}")
    if backends:
        print(f"  Backend         : {', '.join(b['name'] for b in backends)}")
    if databases:
        print(f"  Database/ORM    : {', '.join(d['name'] for d in databases)}")
    if apis:
        print(f"  API Layer       : {', '.join(a['name'] for a in apis)}")

    # Mechanical checks instructions
    print(f"\n[STEP 1 — MECHANICAL CHECKS]")
    if ts or linter or fmt:
        print(f"Run 'uidetox check' to execute tsc → lint → format in sequence.")
        print(f"This queues all compiler/lint errors as T1 issues automatically.")
        print(f"Alternatively, run individually: 'uidetox tsc', 'uidetox lint', 'uidetox format'")
    else:
        print(f"No mechanical tools detected. Skipping to design audit.")

    # Design audit instructions
    print(f"\n[STEP 2 — DESIGN AUDIT]")
    print(f"Read all frontend files in '{args.path}'.")
    
    # Enforce Zones and Suppressions
    ignore_patterns = config.get("ignore_patterns", [])
    if ignore_patterns:
        print("\n  [!] ACTIVE SUPPRESSIONS (Do NOT flag issues matching these patterns):")
        for p in ignore_patterns:
            print(f"      - {p}")
    
    overrides = config.get("zone_overrides", {})
    if overrides:
        print(f"\n  [!] ACTIVE ZONE OVERRIDES ({len(overrides)}):")
        print("      Run 'uidetox zone show' for details.")
        
    print("\n  [!] ZONING RULES:")
    print("      SKIP all files in 'vendor' or 'generated' zones (e.g., node_modules, dist, .next).")
    print("      ONLY audit 'production' and 'config' zones.")
    
    print(f"\nEvaluate against SKILL.md. Check for AI Slop:")
    print(f"  - Inter/system fonts, purple-blue gradients, glassmorphism")
    print(f"  - Card grids, hero metric dashboards, bounce animations")
    print(f"  - Generic startup copy, gray text on colored backgrounds")

    print(f"\n[!] RUNNING STATIC SLOP ANALYZER...")
    exclude_paths = config.get("exclude", [])
    zone_overrides = config.get("zone_overrides", {})
    slop_issues = analyze_directory(args.path, exclude_paths=exclude_paths, zone_overrides=zone_overrides)
    queued_count = 0
    for issue in slop_issues:
        if not _is_suppressed(issue['file'], issue['issue'], ignore_patterns):
            issue_id = f"SCAN-{str(uuid.uuid4())[:6].upper()}"
            new_issue = {
                "id": issue_id,
                "file": issue['file'],
                "tier": issue["tier"],
                "issue": issue["issue"],
                "command": issue["command"]
            }
            add_issue(new_issue)
            queued_count += 1
            
    if queued_count > 0:
        print(f"  ✓ Auto-queued {queued_count} deterministic AI slop anti-patterns.")
    else:
        print(f"  ✓ No deterministic AI slop detected by static analysis.")

    print(f"\nFor each manual, subjective issue found by the agent, run:")
    print(f"  uidetox add-issue --file <path> --tier <T1-T4> --issue <description> --fix-command <cmd>")

    # Full-stack integration instructions
    if backends or databases or apis:
        print(f"\n[STEP 3 — FULL-STACK INTEGRATION]")
        print(f"Check for integration issues between layers:")
        print(f"  - DTO shapes match between frontend and backend")
        print(f"  - Frontend forms respect database constraints")
        print(f"  - Backend errors surfaced properly in UI (loading/error/empty states)")
        print(f"  - Type safety across API boundaries")
        if apis:
            print(f"  - API contract validation ({', '.join(a['name'] for a in apis)})")
        if databases:
            print(f"  - Schema alignment ({', '.join(d['name'] for d in databases)})")

    print(f"\nWhen finished, run 'uidetox plan' then 'uidetox next'.")
    increment_scans()
    save_run_snapshot(trigger="scan")
