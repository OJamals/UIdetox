"""Custom setuptools build backend that syncs root assets before building.

This wraps the standard setuptools backend to ensure uidetox/data/ is always
up-to-date with root-level asset files before a wheel or sdist is produced.

Configured in pyproject.toml:
    [build-system]
    build-backend = "_build_backend"
    backend-path = ["."]
"""

from setuptools.build_meta import *  # noqa: F401,F403
from setuptools.build_meta import (
    build_sdist as _orig_build_sdist,
    build_wheel as _orig_build_wheel,
)


def _sync_assets() -> None:
    """Run scripts/sync_data.py before building."""
    from pathlib import Path
    import importlib.util

    sync_script = Path(__file__).resolve().parent / "scripts" / "sync_data.py"
    if not sync_script.exists():
        return
    spec = importlib.util.spec_from_file_location("sync_data", sync_script)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mod.sync()


def build_wheel(
    wheel_directory: str,
    config_settings: dict | None = None,
    metadata_directory: str | None = None,
) -> str:
    _sync_assets()
    return _orig_build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(
    sdist_directory: str,
    config_settings: dict | None = None,
) -> str:
    _sync_assets()
    return _orig_build_sdist(sdist_directory, config_settings)
