"""Memory command: persistent agent storage with auto-saved session data."""

import argparse
from uidetox.memory import (
    get_patterns,
    get_notes,
    add_pattern,
    add_note,
    clear_memory,
    get_reviewed_files,
    get_session,
    get_last_scan,
    get_progress_log
)


def run(args: argparse.Namespace):
    action = getattr(args, "memory_action", "show")

    if action == "show":
        print("╔══════════════════════════════╗")
        print("║   UIdetox Agent Memory Bank  ║")
        print("╚══════════════════════════════╝")

        # Session state (auto-saved)
        session = get_session()
        if session:
            print()
            print("  ─── Session Checkpoint (auto-saved) ───")
            print(f"    Phase          : {session.get('phase', 'unknown')}")
            print(f"    Last Command   : {session.get('last_command', 'none')}")
            if session.get("last_component"):
                print(f"    Last Component : {session['last_component']}")
            print(f"    Issues Fixed   : {session.get('issues_fixed_this_session', 0)}")
            print(f"    Saved At       : {session.get('saved_at', 'unknown')}")
            if session.get("context"):
                print(f"    Context        : {session['context']}")
            print()
            print("  [CONTINUATION HINT]")
            phase = session.get("phase", "")
            if phase == "scan_complete":
                print("    Last action was a scan. Continue with: uidetox plan → uidetox next")
            elif phase == "fixing":
                print("    Fixes were in progress. Continue with: uidetox next")
            else:
                print("    Run: uidetox status → uidetox next")

        # Last scan summary (auto-saved)
        last_scan = get_last_scan()
        if last_scan:
            print()
            print("  ─── Last Scan Summary (auto-saved) ───")
            print(f"    Timestamp      : {last_scan.get('timestamp', 'unknown')}")
            print(f"    Total Found    : {last_scan.get('total_found', 0)}")
            print(f"    Files Scanned  : {last_scan.get('files_scanned', 0)}")
            by_tier = last_scan.get("by_tier", {})
            if by_tier:
                tier_str = ", ".join(f"{k}={v}" for k, v in sorted(by_tier.items()) if v > 0)
                print(f"    By Tier        : {tier_str or 'none'}")
            by_cat = last_scan.get("by_category", {})
            if by_cat:
                cat_str = ", ".join(f"{k}={v}" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])[:5])
                print(f"    Top Categories : {cat_str}")
            top_files = last_scan.get("top_files", [])
            if top_files:
                print(f"    Most Affected  : {', '.join(top_files[:3])}")

        # Learned patterns (manual + auto)
        patterns = get_patterns()
        if patterns:
            print(f"\n  ─── Learned Patterns ({len(patterns)}) ───")
            for idx, p in enumerate(patterns):
                print(f"    {idx+1}. [{p.get('category', 'general')}] {p['pattern']}")
        else:
            print("\n  ─── Learned Patterns ───")
            print("    No patterns learned yet.")

        # Agent notes (manual)
        notes = get_notes()
        if notes:
            print(f"\n  ─── Agent Notes ({len(notes)}) ───")
            for idx, n in enumerate(notes):
                print(f"    {idx+1}. {n['note']}")
        else:
            print("\n  ─── Agent Notes ───")
            print("    No notes saved yet.")

        # Reviewed files
        files = get_reviewed_files()
        print(f"\n  ─── Reviewed Files ───")
        print(f"    {len(files)} file(s) in memory.")

        # Progress log (auto-saved, last 10)
        progress = get_progress_log()
        if progress:
            print(f"\n  ─── Recent Progress ({len(progress)} entries) ───")
            for entry in progress[-10:]:
                ts = entry.get("timestamp", "")[:19]  # Trim to readable length
                print(f"    [{ts}] {entry.get('action', '?')}: {entry.get('details', '')}")

        print()

    elif action == "pattern":
        val = getattr(args, "value", None)
        if not val:
            print("Error: Must provide a pattern string.")
            return
        add_pattern(val)
        print(f"✓ Learned new architectural pattern: '{val}'")

    elif action == "note":
        val = getattr(args, "value", None)
        if not val:
            print("Error: Must provide a note string.")
            return
        add_note(val)
        print(f"✓ Saved agent note: '{val}'")

    elif action == "clear":
        clear_memory()
        print("✓ Agent Memory Bank completely wiped.")
