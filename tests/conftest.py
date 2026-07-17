"""Shared pytest configuration and contributor environment preflight."""

import pytest

from uidetox.analyzer import ast_capabilities


def pytest_sessionstart(session: pytest.Session) -> None:
    """Reject contributor environments without the core AST dependencies."""
    unavailable = [
        name for name, capability in ast_capabilities().items()
        if not capability["available"]
    ]
    if unavailable:
        raise pytest.UsageError(
            f"AST support is unavailable for {', '.join(unavailable)}. Run "
            "python -m pip install -e '.[dev]' before running tests."
        )
