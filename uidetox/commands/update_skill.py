"""Update Skill command — installs UIdetox rules into the target agent's configuration."""

import argparse
import shutil
import sys
from pathlib import Path


def _get_data_dir() -> Path:
    """Locate the bundled data directory inside the installed package."""
    pkg_data = Path(__file__).resolve().parent.parent / "data"
    if pkg_data.exists():
        return pkg_data
    # Fallback: project root (development mode / editable install)
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root


def _copy_file(src: Path, dst: Path, label: str | None = None) -> None:
    """Copy a single file, creating parent dirs as needed."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    display = label or dst.name
    print(f"  ✓ {display} → {dst}")


def _merge_dir(src: Path, dst: Path, label: str | None = None) -> None:
    """Copy a directory into an existing destination without deleting unrelated files."""
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        target = dst / item.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
    display = label or src.name
    print(f"  ✓ {display}/ → {dst}/")


def _install_project_skill(data: Path, dest: Path) -> None:
    """Install UIdetox inside its own namespace without deleting sibling files."""
    dest.mkdir(parents=True, exist_ok=True)
    for filename in ("SKILL.md", "AGENTS.md"):
        source = data / filename
        if source.exists():
            _copy_file(source, dest / filename)
    _merge_dir(data / "reference", dest / "reference")
    _merge_dir(data / "commands", dest / "commands")


def _install_claude(data: Path, cwd: Path) -> None:
    """Claude Code: .claude/skills/uidetox/"""
    dest = cwd / ".claude" / "skills" / "uidetox"
    _install_project_skill(data, dest)
    print("\n  Claude Code will auto-detect the skill from .claude/skills/.")
    print("  Paste the agent prompt from the README to start the loop.")


def _install_cursor(data: Path, cwd: Path) -> None:
    """Cursor: .cursor/skills/uidetox/ plus namespaced activation rule."""
    dest = cwd / ".cursor" / "skills" / "uidetox"
    _install_project_skill(data, dest)

    # Auto-generate the .cursor/rules MDC file
    rules_dir = cwd / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    mdc_path = rules_dir / "uidetox.mdc"
    mdc_content = """---
description: UIdetox Anti-Slop Guidelines
globs: "*.tsx, *.jsx, *.ts, *.js, *.css, *.html, *.vue, *.svelte"
---
Before generating or reviewing frontend code, use the UIdetox skill at
`.cursor/skills/uidetox/SKILL.md`. Follow its bundled `AGENTS.md` workflow. Preserve
project-owned root instructions and never replace unrelated skills or commands.
"""
    mdc_path.write_text(mdc_content, encoding="utf-8")
    print(f"  ✓ uidetox.mdc → {mdc_path}")
    print("\n  Enable Agent Skills in Cursor Settings → Beta → Agent Skills.")
    print("  The .cursor/rules/uidetox.mdc will auto-activate on frontend files.")


def _install_gemini(data: Path, cwd: Path) -> None:
    """Gemini CLI: .gemini/skills/uidetox/."""
    dest = cwd / ".gemini" / "skills" / "uidetox"
    _install_project_skill(data, dest)
    print("\n  Gemini will discover UIdetox from .gemini/skills/.")


def _install_codex(data: Path, cwd: Path) -> None:
    """Codex CLI: ~/.codex/skills/uidetox/"""
    dest = Path.home() / ".codex" / "skills" / "uidetox"
    _install_project_skill(data, dest)

    # Also copy commands as prompts
    prompts_dir = Path.home() / ".codex" / "prompts" / "uidetox"
    _merge_dir(data / "commands", prompts_dir, label="commands (as prompts)")


def _install_windsurf(data: Path, cwd: Path) -> None:
    """Windsurf: .windsurf/skills/uidetox/."""
    dest = cwd / ".windsurf" / "skills" / "uidetox"
    _install_project_skill(data, dest)
    print("\n  Windsurf will discover UIdetox from .windsurf/skills/.")


def _install_copilot(data: Path, cwd: Path) -> None:
    """GitHub Copilot: .github/skills/uidetox/."""
    dest = cwd / ".github" / "skills" / "uidetox"
    _install_project_skill(data, dest)
    print("\n  Copilot will discover UIdetox from .github/skills/.")


_INSTALLERS = {
    "claude": _install_claude,
    "cursor": _install_cursor,
    "gemini": _install_gemini,
    "codex": _install_codex,
    "windsurf": _install_windsurf,
    "copilot": _install_copilot,
}


def run(args: argparse.Namespace) -> None:
    agent = args.agent
    print("==============================")
    print(f" UIdetox → {agent.capitalize()}")
    print("==============================\n")

    data = _get_data_dir()
    cwd = Path.cwd()

    # Verify bundled data exists
    skill_src = data / "SKILL.md"
    if not skill_src.exists():
        print(f"Error: Bundled SKILL.md not found at {skill_src}", file=sys.stderr)
        print(
            "If you installed via pip, try reinstalling: pip install --force-reinstall uidetox",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Installing UIdetox skill files for {agent.capitalize()}...\n")

    installer = _INSTALLERS.get(agent)
    if not installer:
        valid = ", ".join(sorted(_INSTALLERS.keys()))
        print(
            f"Error: Unknown agent '{agent}'. Valid options: {valid}", file=sys.stderr
        )
        sys.exit(1)
    installer(data, cwd)

    # Print the tailored guide from docs/
    doc_path = data / "docs" / f"{agent.upper()}.md"
    if doc_path.exists():
        print(f"\n{'─' * 40}")
        print(f"  {agent.capitalize()} Integration Guide")
        print(f"{'─' * 40}\n")
        print(doc_path.read_text(encoding="utf-8"))

    print("\n✓ Done. Run `uidetox setup` then `uidetox scan` to begin.")
