"""Update Skill command — installs UIdetox rules into the target agent's configuration."""

import argparse
import shutil
from pathlib import Path

_MARKER_BEGIN = "<!-- uidetox-skill-begin -->"
_MARKER_END = "<!-- uidetox-skill-end -->"


def _get_data_dir() -> Path:
    """Locate the bundled data directory inside the installed package."""
    pkg_data = Path(__file__).resolve().parent.parent / "data"
    if pkg_data.exists():
        return pkg_data
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


def _wrap_section(content: str) -> str:
    """Wrap content in UIdetox section markers for idempotent updates."""
    return f"{_MARKER_BEGIN}\n{content.strip()}\n{_MARKER_END}\n"


def _replace_section(file_path: Path, section_content: str) -> None:
    """Insert or replace the UIdetox section in a shared file.

    If markers already exist, replaces everything between them.
    If the file exists without markers, appends the section.
    If the file doesn't exist, creates it with just the section.
    """
    wrapped = _wrap_section(section_content)

    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        begin_idx = existing.find(_MARKER_BEGIN)
        end_idx = existing.find(_MARKER_END)
        if begin_idx != -1 and end_idx != -1:
            after_marker = end_idx + len(_MARKER_END)
            # consume the newline that follows the end marker
            if after_marker < len(existing) and existing[after_marker] == "\n":
                after_marker += 1
            updated = existing[:begin_idx] + wrapped + existing[after_marker:]
            updated = updated.replace("\n\n\n", "\n\n")
            file_path.write_text(updated, encoding="utf-8")
            print(f"  ✓ Updated UIdetox section in {file_path}")
        else:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n{wrapped}")
            print(f"  ✓ Appended UIdetox section to {file_path}")
    else:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(wrapped, encoding="utf-8")
        print(f"  ✓ Created {file_path}")


def _install_claude(data: Path, cwd: Path) -> None:
    """Claude Code: .claude/skills/uidetox/"""
    dest = cwd / ".claude" / "skills" / "uidetox"
    dest.mkdir(parents=True, exist_ok=True)
    _copy_file(data / "SKILL.md", dest / "SKILL.md")
    _copy_file(data / "AGENTS.md", dest / "AGENTS.md")
    _copy_dir(data / "reference", dest / "reference")
    _copy_dir(data / "commands", dest / "commands")
    print("\n  Claude Code will auto-detect the skill from .claude/skills/.")
    print("  Paste the agent prompt from the README to start the loop.")


def _install_skill_assets(data: Path, cwd: Path, platform: str) -> Path:
    """Install SKILL.md, AGENTS.md, reference/, commands/ to .<platform>/skills/uidetox/."""
    dest = cwd / f".{platform}" / "skills" / "uidetox"
    dest.mkdir(parents=True, exist_ok=True)
    _copy_file(data / "SKILL.md", dest / "SKILL.md")
    _copy_file(data / "AGENTS.md", dest / "AGENTS.md")
    _copy_dir(data / "reference", dest / "reference")
    _copy_dir(data / "commands", dest / "commands")
    return dest


def _install_cursor(data: Path, cwd: Path) -> None:
    """Cursor: .cursor/skills/uidetox/ + .cursor/rules/ + .cursor/agents/"""
    _install_skill_assets(data, cwd, "cursor")

    rules_dir = cwd / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    mdc_path = rules_dir / "uidetox.mdc"
    skill_ref = ".cursor/skills/uidetox"
    mdc_content = f"""---
description: UIdetox Anti-Slop Guidelines
globs: "*.tsx, *.jsx, *.ts, *.js, *.css, *.html, *.vue, *.svelte"
---
Before generating or reviewing frontend code, ALWAYS cross-reference the anti-patterns
and design rules in `{skill_ref}/SKILL.md`. Follow `{skill_ref}/AGENTS.md` for the full
scan→fix loop workflow. DO NOT output purple-blue gradients, generic Inter typography,
glassmorphism cards, or bounce animations.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST
conform exactly to pre-existing backend architectures, API contracts, database schemas,
and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
"""
    mdc_path.write_text(mdc_content, encoding="utf-8")
    print(f"  ✓ uidetox.mdc → {mdc_path}")

    agents_dir = cwd / ".cursor" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agents_dir / "uidetox.md"
    agent_content = """---
name: uidetox
description: Eliminates AI slop by running the UIdetox scan→fix loop
tools:
  - run_terminal_command
  - read_file
  - edit_file
---
Your entire job is executing the UIdetox loop. Run `uidetox loop` to bootstrap the full
5-phase protocol.

The loop will guide you through:
1. Mechanical fixes (`uidetox check --fix`)
2. LLM-dynamic codebase exploration and design audit (`uidetox scan`)
3. Component-level batch fixes (`uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`)
4. Subjective review (`uidetox review` → `uidetox review --score N`)
5. Status check with blended Design Score (`uidetox status`)
6. Finalize (`uidetox finish`)

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform
exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs.
"""
    agent_path.write_text(agent_content, encoding="utf-8")
    print(f"  ✓ uidetox.md → {agent_path}")
    print("\n  Enable Agent Skills in Cursor Settings → Beta → Agent Skills.")
    print("  The .cursor/rules/uidetox.mdc will auto-activate on frontend files.")
    print("  Use the 'uidetox' agent in Cursor Chat to start the loop.")


def _install_gemini(data: Path, cwd: Path) -> None:
    """Gemini CLI: .gemini/skills/uidetox/ + inject section into GEMINI.md"""
    _install_skill_assets(data, cwd, "gemini")

    gemini_section = """@./.gemini/skills/uidetox/SKILL.md

# UIdetox — Anti-Slop Directives

Enforce the Anti-Slop catalog defined in `.gemini/skills/uidetox/SKILL.md`.
Follow `.gemini/skills/uidetox/AGENTS.md` for the scan→fix loop workflow.

Before writing any frontend code, cross-reference the anti-patterns and design rules
in SKILL.md. DO NOT output purple-blue gradients, generic Inter typography,
glassmorphism cards, or bounce animations.

Adhere to the DESIGN_VARIANCE, MOTION_INTENSITY, and VISUAL_DENSITY scores defined
in `.uidetox/config.json`.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. Conform
exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs."""

    _replace_section(cwd / "GEMINI.md", gemini_section)


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
    """Windsurf: .windsurf/skills/uidetox/ + inject section into .windsurfrules"""
    _install_skill_assets(data, cwd, "windsurf")

    windsurf_section = """# UIdetox Anti-Slop Directives

Before writing any frontend code (React, Vue, Svelte, HTML/CSS), you MUST refer to
`.windsurf/skills/uidetox/SKILL.md` to avoid generic AI aesthetics. Follow
`.windsurf/skills/uidetox/AGENTS.md` for the scan→fix loop.

DO NOT use purple/blue default gradients, Inter fonts, glassmorphism, or bouncy animations.
Adhere to the DESIGN_VARIANCE, MOTION_INTENSITY, and VISUAL_DENSITY scores defined in
`.uidetox/config.json`.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. Conform
exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs.

Note: Windsurf Cascade does not support spawning subagents. For parallel reviews,
open multiple Cascade panes manually."""

    _replace_section(cwd / ".windsurfrules", windsurf_section)


def _install_copilot(data: Path, cwd: Path) -> None:
    """GitHub Copilot: .github/skills/uidetox/ + .github/copilot-instructions.md"""
    _install_skill_assets(data, cwd, "github")

    skill_ref = ".github/skills/uidetox"
    copilot_section = f"""# UIdetox — Anti-Slop Directives

This project uses UIdetox to eliminate generic AI-generated UI patterns. Before writing
or reviewing any frontend code, you MUST read and follow:

- `{skill_ref}/SKILL.md` — Full design knowledge base with anti-pattern catalog
- `{skill_ref}/AGENTS.md` — The scan→fix loop workflow and CLI commands

## Rules

1. DO NOT output purple-blue gradients, generic Inter typography, glassmorphism cards,
   oversized shadows, gray text on colored backgrounds, or bounce animations.
2. Adhere to the DESIGN_VARIANCE, MOTION_INTENSITY, and VISUAL_DENSITY scores defined
   in `.uidetox/config.json`.
3. Any generated PR must pass `uidetox check` and `uidetox scan` without T2+ issues.
4. **CRITICAL:** All output must be strictly type-safe. Conform exactly to pre-existing
   backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate
   new endpoints or alter data structures when fixing UI slop.

## Autonomous Loop

Run `uidetox loop` to bootstrap the full 5-phase protocol:
1. `uidetox check --fix` — mechanical fixes (tsc, lint, format)
2. `uidetox scan` — static analysis + design audit
3. `uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`
4. `uidetox review` → `uidetox review --score N`
5. `uidetox status` — blended Design Score (target: 95+)"""

    _replace_section(cwd / ".github" / "copilot-instructions.md", copilot_section)
    print("\n  Copilot will auto-read .github/copilot-instructions.md as project context.")
    print(f"  Skill files installed to {skill_ref}/")


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
