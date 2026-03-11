"""CLI entry point for UIdetox."""

import argparse
import sys
from importlib import import_module
from pathlib import Path


def _get_version() -> str:
    """Return package version."""
    try:
        from uidetox import __version__
        return __version__
    except ImportError:
        return "0.1.0"


def _get_commands_dir() -> Path | None:
    """Find the commands/ directory — bundled data first, then project root."""
    # 1. Bundled inside the installed package (uidetox/data/commands/)
    pkg_data = Path(__file__).resolve().parent / "data" / "commands"
    if pkg_data.exists():
        return pkg_data
    # 2. Project root commands/ (development / editable install)
    try:
        from uidetox.state import get_project_root
        cmd_dir = get_project_root() / "commands"
        if cmd_dir.exists():
            return cmd_dir
    except Exception:
        pass
    # 3. Fallback: sibling to the package root
    pkg_root = Path(__file__).resolve().parent.parent
    cmd_dir = pkg_root / "commands"
    if cmd_dir.exists():
        return cmd_dir
    return None


def parse_args(args_list=None):
    parser = argparse.ArgumentParser(
        prog="uidetox",
        description="UIdetox — agent harness to eliminate AI slop and enforce code quality across frontend, backend, and database layers."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_get_version()}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: setup
    setup_parser = subparsers.add_parser("setup", help="Gather project design context and configure dials")
    setup_parser.add_argument("--auto-commit", action="store_true", help="Enable automated git commits for resolved issues")
    
    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Full diagnostic audit of frontend interface quality")
    scan_parser.add_argument("--path", default=".", help="Directory to scan")

    # Command: add-issue (For agent use during scan)
    add_parser = subparsers.add_parser("add-issue", help="Add an issue to the state queue (Agent use)")
    add_parser.add_argument("--file", required=True, help="File path with the issue")
    add_parser.add_argument("--tier", required=True, choices=["T1", "T2", "T3", "T4"], help="Severity tier")
    add_parser.add_argument("--issue", required=True, help="Description of the issue")
    add_parser.add_argument("--fix-command", required=True, help="Suggested command to fix")

    # Command: next
    next_parser = subparsers.add_parser("next", help="Picks the next highest-priority issue from the scan queue")

    # Command: resolve
    resolve_parser = subparsers.add_parser("resolve", help="Mark a specific issue as resolved")
    resolve_parser.add_argument("issue_id", help="The ID of the issue to resolve (e.g. SCAN-001)")
    resolve_parser.add_argument("--note", required=True, help="Mandatory explanation of the fix applied")

    # Command: batch-resolve
    batch_resolve_parser = subparsers.add_parser("batch-resolve", help="Resolve multiple issues with a single coherent commit")
    batch_resolve_parser.add_argument("issue_ids", nargs="+", help="Issue IDs to resolve (e.g. SCAN-001 SCAN-002 SCAN-003)")
    batch_resolve_parser.add_argument("--note", required=True, help="Mandatory explanation of fixes applied")
    batch_resolve_parser.add_argument("--skip-verify", action="store_true", help="Skip pre-commit verification gate")

    # Command: plan
    plan_parser = subparsers.add_parser("plan", help="Reorder priorities or cluster related issues in the queue")
    
    # Command: review
    review_parser = subparsers.add_parser("review", help="Subjective UX review of the latest changes")
    review_parser.add_argument("--score", type=int, help="Store an LLM-assigned subjective design score (0-100)")
    
    # Command: capture
    capture_parser = subparsers.add_parser("capture", help="Capture a visual regression screenshot via Playwright")
    capture_parser.add_argument("--url", type=str, help="URL of the local dev server (default: http://localhost:3000)")
    
    # Command: update-skill
    update_parser = subparsers.add_parser("update-skill", help="Installs UIdetox rules into your agent's configuration")
    update_parser.add_argument("agent", choices=["claude", "cursor", "gemini", "codex", "windsurf", "copilot"], help="Target AI agent")

    # Command: status
    status_parser = subparsers.add_parser("status", help="Show project health dashboard with design score")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Command: show
    show_parser = subparsers.add_parser("show", help="Show details of issues, filter by file/tier/ID")
    show_parser.add_argument("pattern", nargs="?", default=None, help="Filter by issue ID, file path, or tier (T1-T4)")

    # Command: exclude
    exclude_parser = subparsers.add_parser("exclude", help="Exclude a directory from scanning")
    exclude_parser.add_argument("path", help="Path to exclude (e.g. node_modules, dist)")

    # Command: autofix
    autofix_parser = subparsers.add_parser("autofix", help="Batch-apply all safe T1 quick fixes")
    autofix_parser.add_argument("--dry-run", action="store_true", help="Preview fixes without applying")

    # Command: rescan
    rescan_parser = subparsers.add_parser("rescan", help="Clear queue and re-scan the project fresh")
    rescan_parser.add_argument("--path", default=".", help="Directory to rescan")

    # Command: loop
    loop_parser = subparsers.add_parser("loop", help="Instruct the AI agent to enter an autonomous fix loop")
    loop_parser.add_argument("--target", type=int, default=95, help="Target design score to reach (default 95)")
    loop_parser.add_argument("--orchestrator", action="store_true", help="Use sub-agent orchestrator mode (one agent per stage)")

    # Command: finish
    finish_parser = subparsers.add_parser("finish", help="Squash-merge and commit an active UIdetox session branch")

    # Command: subagent
    sub_parser = subparsers.add_parser("subagent", help="Manage sub-agent sessions and generate stage prompts")
    sub_parser.add_argument("--stage-prompt", type=str, help="Generate prompt for a stage (observe/diagnose/prioritize/fix/verify)")
    sub_parser.add_argument("--parallel", type=int, default=1, help="Number of parallel sub-agents to shard the workload across")
    sub_parser.add_argument("--list", action="store_true", help="List all sub-agent sessions")
    sub_parser.add_argument("--show", type=str, help="Show details of a session by ID")
    sub_parser.add_argument("--record", type=str, help="Mark a session as completed")
    sub_parser.add_argument("--note", type=str, default="", help="Note for --record")

    # Command: history
    history_parser = subparsers.add_parser("history", help="View run history and score progression")
    history_parser.add_argument("--full", action="store_true", help="Show full run details")
    history_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Command: viz
    viz_parser = subparsers.add_parser("viz", help="Generate an HTML treemap heatmap of codebase issues")
    viz_parser.add_argument("--path", default=".", help="Directory to visualize")
    viz_parser.set_defaults(viz_cmd="viz")

    # Command: tree
    tree_parser = subparsers.add_parser("tree", help="Print a terminal tree of codebase issues")
    tree_parser.add_argument("--path", default=".", help="Directory to visualize")
    tree_parser.add_argument("--depth", type=int, default=3, help="Max depth of the tree")
    tree_parser.set_defaults(viz_cmd="tree")

    # Command: zone
    zone_parser = subparsers.add_parser("zone", help="Show, set, or clear file classifications (production, test, vendor, etc.)")
    zone_parser.add_argument("zone_action", nargs="?", choices=["show", "set", "clear"], default="show", help="Action to perform")
    zone_parser.add_argument("zone_path", nargs="?", help="File path to override")
    zone_parser.add_argument("zone_value", nargs="?", help="Zone value (production, test, config, generated, script, vendor)")

    # Command: suppress
    suppress_parser = subparsers.add_parser("suppress", help="Permanently suppress issues matching a pattern")
    suppress_parser.add_argument("pattern", nargs="?", help="Pattern to suppress (e.g., *vendor/* or 'Uses Inter font')")
    suppress_parser.add_argument("--remove", action="store_true", help="Remove an existing suppression pattern")

    # Command: memory
    memory_parser = subparsers.add_parser("memory", help="Read or write to the persistent agent memory bank")
    memory_parser.add_argument("memory_action", nargs="?", choices=["show", "pattern", "note", "clear"], default="show", help="Action to perform")
    memory_parser.add_argument("value", nargs="?", help="The pattern or note string to save")

    # Command: detect
    detect_parser = subparsers.add_parser("detect", help="Auto-detect project tooling (linters, formatters, tsc, backend, db)")
    detect_parser.add_argument("--path", default=".", help="Project root to scan")

    # Command: check (master: tsc → lint → format)
    check_parser = subparsers.add_parser("check", help="Run tsc → lint → format in sequence")
    check_parser.add_argument("--fix", action="store_true", help="Auto-fix lint and format issues")

    # Command: tsc
    tsc_parser = subparsers.add_parser("tsc", help="Run TypeScript compiler and queue errors")
    tsc_parser.add_argument("--fix", action="store_true", help="(reserved for future use)")

    # Command: lint
    lint_parser = subparsers.add_parser("lint", help="Run detected linter and queue errors")
    lint_parser.add_argument("--fix", action="store_true", help="Auto-fix lint errors")

    # Command: format
    format_parser = subparsers.add_parser("format", help="Run detected formatter")
    format_parser.add_argument("--fix", action="store_true", help="Auto-fix formatting")

    # Dynamic Slash Commands (e.g., /audit, /polish) from the commands/ directory
    cmd_dir = _get_commands_dir()
    if cmd_dir:
        for md_file in cmd_dir.glob("*.md"):
            skill_name = md_file.stem
            if skill_name not in ["scan", "setup", "fix"]:
                skill_parser = subparsers.add_parser(skill_name, help=f"Execute the '{skill_name}' UX design skill")
                skill_parser.add_argument("target", nargs="?", default=".", help="Target file, directory, or component pattern")

    # Catch common mistake: uidetox --check → redirect to uidetox check
    if args_list is None and len(sys.argv) > 1 and sys.argv[1] == "--check":
        print("Did you mean 'uidetox check'? Run 'uidetox check --fix' for mechanical fixes.")
        sys.exit(0)

    return parser.parse_args(args_list)

def main():
    args = parse_args()
    if not args.command:
        # Just show help
        parse_args(["--help"])
        return

    # Dispatch to the specific command module
    try:
        # Check dynamic skills
        cmd_dir = _get_commands_dir()
        dynamic_skills = []
        if cmd_dir:
            dynamic_skills = [f.stem for f in cmd_dir.glob("*.md") if f.stem not in ["scan", "setup", "fix"]]
            
        if args.command in dynamic_skills:
            command_name = "skill_cmd"
        else:
            command_name = args.command.replace("-", "_")
            
        # Avoid collision with builtins and top-level modules
        name_map = {
            "format": "format_cmd", 
            "subagent": "subagent_cmd", 
            "history": "history_cmd",
            "memory": "memory_cmd",
            "tree": "viz" # route 'tree' to 'viz.py'
        }
        command_name = name_map.get(command_name, command_name)
        module = import_module(f"uidetox.commands.{command_name}")
        
        if hasattr(module, "run"):
            # Pass args to the command runner
            module.run(args)
        else:
            print(f"Error: Command module for '{args.command}' lacks a run() function.", file=sys.stderr)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nInterrupted. Run 'uidetox status' to see where you left off.")
        sys.exit(130)
    except ImportError as e:
        print(f"Error: Command '{args.command}' is not implemented yet. ({e})", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
