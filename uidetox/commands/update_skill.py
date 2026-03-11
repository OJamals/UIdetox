"""Update Skill command — installs UIdetox rules into the target agent's configuration."""

import argparse
import os
import shutil
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


def _copy_dir(src: Path, dst: Path, label: str | None = None) -> None:
    """Recursively copy a directory, creating it if needed."""
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    display = label or src.name
    print(f"  ✓ {display}/ → {dst}/")


def _install_claude(data: Path, cwd: Path) -> None:
    """Claude Code: .claude/skills/uidetox/"""
    dest = cwd / ".claude" / "skills" / "uidetox"
    dest.mkdir(parents=True, exist_ok=True)
    _copy_file(data / "SKILL.md", dest / "SKILL.md")
    _copy_dir(data / "reference", dest / "reference")
    _copy_dir(data / "commands", dest / "commands")
    print("\n  Claude Code will auto-detect the skill from .claude/skills/.")
    print("  Paste the agent prompt from the README to start the loop.")


def _install_cursor(data: Path, cwd: Path) -> None:
    """Cursor: copy SKILL.md + AGENTS.md to root, create .cursor/rules/uidetox.mdc"""
    _copy_file(data / "SKILL.md", cwd / "SKILL.md")
    _copy_file(data / "AGENTS.md", cwd / "AGENTS.md")
    _copy_dir(data / "reference", cwd / "reference")
    _copy_dir(data / "commands", cwd / "commands")

    # Auto-generate the .cursor/rules MDC file
    rules_dir = cwd / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    mdc_path = rules_dir / "uidetox.mdc"
    mdc_content = """---
description: UIdetox Anti-Slop Guidelines
globs: "*.tsx, *.jsx, *.ts, *.js, *.css, *.html, *.vue, *.svelte"
---
Before generating or reviewing frontend code, ALWAYS cross-reference the anti-patterns
and design rules in `SKILL.md` at the project root. Follow `AGENTS.md` for the full
scan→fix loop workflow. DO NOT output purple-blue gradients, generic Inter typography,
glassmorphism cards, or bounce animations.
"""
    mdc_path.write_text(mdc_content, encoding="utf-8")
    print(f"  ✓ uidetox.mdc → {mdc_path}")
    print("\n  Enable Agent Skills in Cursor Settings → Beta → Agent Skills.")
    print("  The .cursor/rules/uidetox.mdc will auto-activate on frontend files.")


def _install_gemini(data: Path, cwd: Path) -> None:
    """Gemini CLI: copy SKILL.md to root, create/append GEMINI.md"""
    _copy_file(data / "SKILL.md", cwd / "SKILL.md")
    _copy_file(data / "AGENTS.md", cwd / "AGENTS.md")
    _copy_dir(data / "reference", cwd / "reference")
    _copy_dir(data / "commands", cwd / "commands")

    gemini_md = cwd / "GEMINI.md"
    ref_line = "@./SKILL.md"
    if gemini_md.exists():
        content = gemini_md.read_text(encoding="utf-8")
        if ref_line not in content:
            with open(gemini_md, "a", encoding="utf-8") as f:
                f.write(f"\n{ref_line}\n")
            print(f"  ✓ Appended '{ref_line}' to GEMINI.md")
        else:
            print(f"  ✓ GEMINI.md already references SKILL.md")
    else:
        gemini_md.write_text(
            f"{ref_line}\n\n# UI Directives\nEnforce the Anti-Slop catalog defined in SKILL.md.\n",
            encoding="utf-8",
        )
        print(f"  ✓ Created GEMINI.md with SKILL.md reference")


def _install_codex(data: Path, cwd: Path) -> None:
    """Codex CLI: ~/.codex/skills/uidetox/"""
    dest = Path.home() / ".codex" / "skills" / "uidetox"
    dest.mkdir(parents=True, exist_ok=True)
    _copy_file(data / "SKILL.md", dest / "SKILL.md")
    _copy_dir(data / "reference", dest / "reference")
    _copy_dir(data / "commands", dest / "commands")

    # Also copy commands as prompts
    prompts_dir = Path.home() / ".codex" / "prompts"
    _copy_dir(data / "commands", prompts_dir, label="commands (as prompts)")


def _install_windsurf(data: Path, cwd: Path) -> None:
    """Windsurf: copy SKILL.md to root, create/update .windsurfrules"""
    _copy_file(data / "SKILL.md", cwd / "SKILL.md")
    _copy_file(data / "AGENTS.md", cwd / "AGENTS.md")
    _copy_dir(data / "reference", cwd / "reference")
    _copy_dir(data / "commands", cwd / "commands")

    rules_path = cwd / ".windsurfrules"
    rules_content = """# UIdetox Anti-Slop Directives
Before writing any frontend code (React, Vue, Svelte, HTML/CSS), you MUST refer to
`SKILL.md` to avoid generic AI aesthetics. Follow `AGENTS.md` for the scan→fix loop.

DO NOT use purple/blue default gradients, Inter fonts, glassmorphism, or bouncy animations.
Adhere to the DESIGN_VARIANCE, MOTION_INTENSITY, and VISUAL_DENSITY scores defined in
`.uidetox/config.json`.
"""
    if rules_path.exists():
        existing = rules_path.read_text(encoding="utf-8")
        if "UIdetox" not in existing:
            with open(rules_path, "a", encoding="utf-8") as f:
                f.write(f"\n{rules_content}")
            print(f"  ✓ Appended UIdetox rules to .windsurfrules")
        else:
            print(f"  ✓ .windsurfrules already contains UIdetox rules")
    else:
        rules_path.write_text(rules_content, encoding="utf-8")
        print(f"  ✓ Created .windsurfrules")


def _install_copilot(data: Path, cwd: Path) -> None:
    """GitHub Copilot: copy SKILL.md + AGENTS.md to project root."""
    _copy_file(data / "SKILL.md", cwd / "SKILL.md")
    _copy_file(data / "AGENTS.md", cwd / "AGENTS.md")
    _copy_dir(data / "reference", cwd / "reference")
    _copy_dir(data / "commands", cwd / "commands")
    print("\n  Copilot will pick up SKILL.md and AGENTS.md from the project root.")
    print("  Reference them in your Copilot Workspace spec or IDE prompt.")


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
    print(f"==============================")
    print(f" UIdetox → {agent.capitalize()}")
    print(f"==============================\n")

    data = _get_data_dir()
    cwd = Path.cwd()

    # Verify bundled data exists
    skill_src = data / "SKILL.md"
    if not skill_src.exists():
        print(f"Error: Bundled SKILL.md not found at {skill_src}")
        print("If you installed via pip, try reinstalling: pip install --force-reinstall uidetox")
        return

    print(f"Installing UIdetox skill files for {agent.capitalize()}...\n")

    installer = _INSTALLERS.get(agent)
    if installer:
        installer(data, cwd)
    else:
        print(f"Unknown agent: {agent}")
        return

    # Print the tailored guide from docs/
    doc_path = data / "docs" / f"{agent.upper()}.md"
    if doc_path.exists():
        print(f"\n{'─' * 40}")
        print(f"  {agent.capitalize()} Integration Guide")
        print(f"{'─' * 40}\n")
        print(doc_path.read_text(encoding="utf-8"))

    print(f"\n✓ Done. Run `uidetox setup` then `uidetox scan` to begin.")
