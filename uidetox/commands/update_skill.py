"""Install bundled UIdetox guidance for a supported coding agent."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from uidetox.agent_integration import (
    SUPPORTED_AGENT_NAMES,
    AgentIntegrationEnvironment,
    default_data_dir,
    install_agent,
)


def _get_data_dir() -> Path:
    """Compatibility seam for tests and editable installations."""

    return default_data_dir()


def _environment(data: Path, cwd: Path) -> AgentIntegrationEnvironment:
    return AgentIntegrationEnvironment(
        project_root=cwd,
        home=Path.home(),
        data_root=data,
        interactive=False,
        input_fn=input,
        output_fn=print,
        which=shutil.which,
    )


def _exit_error(message: str, *, reinstall: bool = False) -> None:
    print(f"Error: {message}", file=sys.stderr)
    if reinstall:
        print(
            "If you installed via pip, try reinstalling: "
            "pip install --force-reinstall uidetox",
            file=sys.stderr,
        )
    raise SystemExit(1)


def run(args: argparse.Namespace) -> None:
    agent = str(args.agent)
    print("==============================")
    print(f" UIdetox → {agent.capitalize()}")
    print("==============================\n")

    data = _get_data_dir()
    skill_source = data / "SKILL.md"
    if not skill_source.is_file():
        _exit_error(
            f"Bundled SKILL.md not found at {skill_source}",
            reinstall=True,
        )
    if agent not in SUPPORTED_AGENT_NAMES:
        _exit_error(
            f"Unknown agent '{agent}'. Valid options: "
            f"{', '.join(sorted(SUPPORTED_AGENT_NAMES))}"
        )

    print(f"Installing UIdetox skill files for {agent.capitalize()}...\n")
    result = install_agent(agent, _environment(data, Path.cwd()))
    if not result.success:
        _exit_error(result.error or "Agent integration failed.")
    for message in result.messages:
        print(message)

    if result.guide is not None:
        print(f"\n{'─' * 40}")
        print(f"  {agent.capitalize()} Integration Guide")
        print(f"{'─' * 40}\n")
        print(result.guide)

    print("\n✓ Done. Run `uidetox setup` then `uidetox scan` to begin.")
