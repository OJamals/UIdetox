"""Shared pytest configuration and contributor environment preflight."""

import socket
import subprocess
import sys
import time
import venv
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from uidetox.analyzer import ast_capabilities


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).parents[1]


@pytest.fixture(scope="session")
def publish_workflow(project_root: Path) -> str:
    return (project_root / ".github/workflows/python-publish.yml").read_text(
        encoding="utf-8"
    )


@pytest.fixture(scope="session")
def packaged_asset_pairs(
    project_root: Path,
) -> tuple[tuple[Path, Path], ...]:
    data = project_root / "uidetox" / "data"
    pairs = [
        (project_root / "SKILL.md", data / "SKILL.md"),
        (project_root / "AGENTS.md", data / "AGENTS.md"),
    ]
    for directory in ("commands", "reference"):
        for canonical in sorted((project_root / directory).glob("*.md")):
            pairs.append((canonical, data / directory / canonical.name))
    for bundled in sorted((data / "docs").glob("*.md")):
        pairs.append((project_root / "docs" / bundled.name, bundled))
    return tuple(pairs)


@pytest.fixture(scope="session")
def built_wheel(project_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    wheel_dir = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(project_root),
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wheels = tuple(wheel_dir.glob("uidetox-*.whl"))
    assert len(wheels) == 1
    return wheels[0]


@pytest.fixture(scope="session")
def installed_wheel_cli_output(
    built_wheel: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[str, str]:
    root = tmp_path_factory.mktemp("installed-wheel")
    environment = root / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    scripts = environment / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    cli = scripts / ("uidetox.exe" if sys.platform == "win32" else "uidetox")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(built_wheel)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    outside_checkout = root / "outside-checkout"
    outside_checkout.mkdir()
    completed = subprocess.run(
        [str(cli), "--version"],
        cwd=outside_checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    pyvenv_config = (environment / "pyvenv.cfg").read_text(encoding="utf-8")
    return completed.stdout.strip(), pyvenv_config


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
