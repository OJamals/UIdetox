"""Memory command: persistent agent storage integration."""

import argparse
from uidetox.memory import (
    get_patterns, 
    get_notes, 
    add_pattern, 
    add_note, 
    clear_memory,
    get_reviewed_files
)

def run(args: argparse.Namespace):
    action = getattr(args, "memory_action", "show")
    
    if action == "show":
        print("==============================")
        print(" UIdetox Agent Memory Bank")
        print("==============================")
        
        patterns = get_patterns()
        if patterns:
            print(f"\n[Learned Patterns] ({len(patterns)})")
            for idx, p in enumerate(patterns):
                print(f"  {idx+1}. [{p.get('category', 'general')}] {p['pattern']}")
        else:
            print("\n[Learned Patterns]\n  No patterns learned yet.")
            
        notes = get_notes()
        if notes:
            print(f"\n[Agent Notes] ({len(notes)})")
            for idx, n in enumerate(notes):
                print(f"  {idx+1}. {n['note']}")
        else:
            print("\n[Agent Notes]\n  No notes saved yet.")
            
        files = get_reviewed_files()
        print(f"\n[Reviewed Files] {len(files)} file(s) scanned in memory.")
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
        print("✓ Agent memory Bank completely wiped.")
