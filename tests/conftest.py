"""Shared pytest configuration and contributor environment preflight."""

import pytest

from uidetox.analyzer import HAS_AST


def pytest_sessionstart(session: pytest.Session) -> None:
    """Reject contributor environments without the core AST dependencies."""
    if not HAS_AST:
        raise pytest.UsageError(
            "Core AST support is unavailable. Run "
            "python -m pip install -e '.[dev]' before running tests."
        )
