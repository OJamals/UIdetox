"""Shared pytest configuration and contributor environment preflight."""

import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from uidetox.analyzer import ast_capabilities


def pytest_sessionstart(session: pytest.Session) -> None:
    """Reject contributor environments without the core AST dependencies."""
    unavailable = [
        name
        for name, capability in ast_capabilities().items()
        if not capability["available"]
    ]
    if unavailable:
        raise pytest.UsageError(
            f"AST support is unavailable for {', '.join(unavailable)}. Run "
            "python -m pip install -e '.[dev]' before running tests."
        )


@pytest.fixture
def local_http_server() -> Iterator[Callable[[Path], str]]:
    """Start localhost-only static servers and prove teardown leaves no process."""
    processes: list[subprocess.Popen[bytes]] = []

    def start(directory: Path) -> str:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(directory.resolve()),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(process)
        origin = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Local qualification server exited before readiness.")
            try:
                with urlopen(f"{origin}/", timeout=0.2) as response:
                    if response.status == 200:
                        return origin
            except URLError:
                time.sleep(0.05)
        raise RuntimeError("Local qualification server did not become ready.")

    yield start

    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        assert process.poll() is not None
