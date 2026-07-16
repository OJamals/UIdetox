"""Prototype command: emit an isolated implementation brief for one proposal."""

import argparse
from pathlib import Path

from uidetox.prototype import build_prototype_brief, save_prototype_brief
from uidetox.redesign import load_redesign_set


def run(args: argparse.Namespace) -> None:
    file_arg = getattr(args, "redesign_file", None)
    redesign_set = load_redesign_set(Path(file_arg) if file_arg else None)
    proposal_id = args.proposal_id
    output_arg = getattr(args, "output", None)
    output_path = save_prototype_brief(
        redesign_set,
        proposal_id,
        Path(output_arg) if output_arg else None,
    )

    if getattr(args, "stdout", False):
        print(build_prototype_brief(redesign_set, proposal_id))
        return

    print(f"Prototype brief created: {output_path}")
    print("  Mode: disposable; do not merge prototype code into production")
    print(f"  Launch: open a fresh agent session with {output_path}")
