"""Skill command handler: dynamically executes markdown slash commands from commands/ directory."""

import argparse
import sys
from pathlib import Path
from uidetox.state import get_project_root

def run(args: argparse.Namespace):
    skill_name = args.command
    target = getattr(args, "target", ".")
    
    cmd_dir = get_project_root() / "commands"
    skill_file = cmd_dir / f"{skill_name}.md"
    
    if not skill_file.exists():
        print(f"Error: Skill command '{skill_name}' not found at {skill_file}")
        sys.exit(1)
        
    try:
        content = skill_file.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading skill file: {e}")
        sys.exit(1)
        
    print("================================================================")
    print(f" UIdetox Skill Execution: /{skill_name.upper()}")
    print("================================================================")
    print(f"Targeting: {target}")
    print()
    print("[AGENT INSTRUCTION]")
    print(f"You have been invoked to perform the '{skill_name}' skill on '{target}'.")
    print("Read the following contextual rules carefully and execute the assignment:")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(content)
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("\nWhen finished, track your architectural learnings:")
    print("  uidetox memory pattern \"Discovered that...\"")
    print("Then check your score progression:")
    print("  uidetox status")
