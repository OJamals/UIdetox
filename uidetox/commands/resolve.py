"""Resolve one finding through the shared batch verifier path."""

import argparse

from uidetox.commands.batch_resolve import run as _run_batch


def run(args: argparse.Namespace) -> None:
    _run_batch(
        argparse.Namespace(
            **vars(args),
            issue_ids=[args.issue_id],
            single=True,
        )
    )
