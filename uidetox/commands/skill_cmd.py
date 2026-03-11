"""Skill command handler: dynamically executes markdown slash commands from commands/ directory."""

import argparse
import sys
from pathlib import Path
from uidetox.state import get_project_root


def _find_skill_file(skill_name: str) -> Path | None:
    """Locate a skill markdown file.

    Search order:
    1. Project root commands/ (user-customized or installed via update-skill)
    2. .claude/skills/uidetox/commands/ (Claude skill directory)
    3. Bundled package data/commands/ (pip-installed default)
    """
    name = f"{skill_name}.md"

    # 1. Project root
    project_cmd = get_project_root() / "commands" / name
    if project_cmd.exists():
        return project_cmd

    # 2. Claude skills directory
    claude_cmd = Path.cwd() / ".claude" / "skills" / "uidetox" / "commands" / name
    if claude_cmd.exists():
        return claude_cmd

    # 3. Bundled data inside pip package
    pkg_data = Path(__file__).resolve().parent.parent / "data" / "commands" / name
    if pkg_data.exists():
        return pkg_data

    return None


def _list_available_skills() -> list[str]:
    """List all available skill commands from all locations."""
    skills: set[str] = set()

    search_dirs = [
        get_project_root() / "commands",
        Path.cwd() / ".claude" / "skills" / "uidetox" / "commands",
        Path(__file__).resolve().parent.parent / "data" / "commands",
    ]

    for d in search_dirs:
        if d.is_dir():
            for f in d.glob("*.md"):
                skills.add(f.stem)

    return sorted(skills)


def run(args: argparse.Namespace):
    skill_name = args.command
    target = getattr(args, "target", ".")
    
    skill_file = _find_skill_file(skill_name)
    
    if not skill_file:
        available = _list_available_skills()
        print(f"Error: Skill command '{skill_name}' not found.")
        if available:
            print(f"Available skills: {', '.join(available)}")
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
    print(f"Source: {skill_file}")
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
