"""Canonical project-root-aware frontend file discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


FRONTEND_EXTENSIONS = frozenset(
    {
        ".css",
        ".html",
        ".js",
        ".jsx",
        ".less",
        ".md",
        ".sass",
        ".scss",
        ".svelte",
        ".ts",
        ".tsx",
        ".vue",
    }
)

IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".claude",
        ".cursor",
        ".git",
        ".next",
        ".nuxt",
        ".turbo",
        ".uidetox",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "out",
        "vendor",
    }
)

_PROJECT_ROOT_MARKERS = (
    ".uidetox",
    ".git",
    "pyproject.toml",
    "package.json",
    "pnpm-workspace.yaml",
    "Cargo.toml",
    "go.mod",
    "composer.json",
    "Gemfile",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
)
_SKIPPED_ZONES = frozenset({"vendor", "generated"})


def find_project_root(start: str | Path) -> Path:
    """Return nearest project ancestor, falling back to *start* itself."""
    candidate = Path(start).resolve()
    if candidate.is_file():
        candidate = candidate.parent

    marker_groups = (
        (".uidetox",),
        (".git",),
        _PROJECT_ROOT_MARKERS[2:],
    )
    for markers in marker_groups:
        current = candidate
        while True:
            if any((current / marker).exists() for marker in markers):
                return current
            if current == current.parent:
                break
            current = current.parent
    return candidate


def _normalized_parts(value: str) -> tuple[str, ...]:
    normalized = value.strip().replace("\\", "/").strip("/")
    if not normalized:
        return ()
    return tuple(
        part for part in PurePosixPath(normalized).parts if part not in ("", ".")
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class ProjectFileSet:
    """Discover frontend files using one root-relative exclusion policy.

    ``explicit_targets=None`` walks ``scope_root``. An explicit empty iterable
    discovers no files. Relative targets and zone entries resolve from
    ``project_root``, never from process cwd.
    """

    project_root: str | Path
    excludes: Iterable[str] = ()
    zone_overrides: Mapping[str, str] = field(default_factory=dict)
    explicit_targets: Iterable[str | Path] | None = None
    scope_root: str | Path | None = None
    _excluded_basenames: frozenset[str] = field(init=False, repr=False)
    _excluded_subtrees: tuple[tuple[str, ...], ...] = field(init=False, repr=False)
    _skipped_zone_paths: tuple[Path, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        root = Path(self.project_root).resolve()
        scope = root if self.scope_root is None else Path(self.scope_root).resolve()
        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "scope_root", scope)
        object.__setattr__(self, "excludes", tuple(self.excludes))
        object.__setattr__(self, "zone_overrides", dict(self.zone_overrides))
        if self.explicit_targets is not None:
            object.__setattr__(self, "explicit_targets", tuple(self.explicit_targets))
        basenames: set[str] = set()
        subtrees: list[tuple[str, ...]] = []
        for entry in self.excludes:
            if not isinstance(entry, str):
                continue
            parts = _normalized_parts(entry)
            if not parts or ".." in parts:
                continue
            if "/" in entry or "\\" in entry:
                subtrees.append(parts)
            else:
                basenames.add(parts[0])
        object.__setattr__(self, "_excluded_basenames", frozenset(basenames))
        object.__setattr__(self, "_excluded_subtrees", tuple(subtrees))

        zone_paths: list[Path] = []
        for entry, zone in self.zone_overrides.items():
            if zone not in _SKIPPED_ZONES or not isinstance(entry, str):
                continue
            normalized = entry.replace("\\", "/")
            zone_path = Path(normalized)
            if not zone_path.is_absolute():
                zone_path = self.root.joinpath(*_normalized_parts(entry))
            resolved = zone_path.resolve()
            if _is_within(resolved, self.root):
                zone_paths.append(resolved)
        object.__setattr__(self, "_skipped_zone_paths", tuple(zone_paths))

    @property
    def root(self) -> Path:
        return self.project_root  # type: ignore[return-value]

    @property
    def scope(self) -> Path:
        return self.scope_root  # type: ignore[return-value]

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate.resolve()

    def _directory_allowed(self, path: str | Path) -> bool:
        candidate = self._resolve(path)
        if not candidate.is_dir():
            return False
        if not _is_within(candidate, self.root) or not _is_within(
            candidate, self.scope
        ):
            return False
        relative_parts = candidate.relative_to(self.root).parts
        if any(
            part.startswith(".") or part in IGNORED_DIRECTORY_NAMES
            for part in relative_parts
        ):
            return False
        if any(part in self._excluded_basenames for part in relative_parts):
            return False
        if any(
            relative_parts[: len(parts)] == parts for parts in self._excluded_subtrees
        ):
            return False
        return not any(
            candidate == zone_path or _is_within(candidate, zone_path)
            for zone_path in self._skipped_zone_paths
        )

    def accepts(self, path: str | Path, *, require_extension: bool = True) -> bool:
        """Return whether *path* is an eligible in-root file."""
        candidate = self._resolve(path)
        if not candidate.is_file():
            return False
        if not _is_within(candidate, self.root) or not _is_within(
            candidate, self.scope
        ):
            return False

        relative = candidate.relative_to(self.root)
        directories = relative.parts[:-1]
        if any(
            part.startswith(".") or part in IGNORED_DIRECTORY_NAMES
            for part in directories
        ):
            return False

        if any(part in self._excluded_basenames for part in directories):
            return False
        relative_parts = relative.parts
        if any(
            relative_parts[: len(parts)] == parts for parts in self._excluded_subtrees
        ):
            return False

        if any(
            candidate == zone_path or _is_within(candidate, zone_path)
            for zone_path in self._skipped_zone_paths
        ):
            return False
        return not require_extension or candidate.suffix.lower() in FRONTEND_EXTENSIONS

    def explicit_candidates(
        self, *, require_extension: bool = False
    ) -> list[Path] | None:
        """Resolve explicit targets; return ``None`` when discovery should walk."""
        if self.explicit_targets is None:
            return None
        accepted = {
            self._resolve(target)
            for target in self.explicit_targets
            if self.accepts(target, require_extension=require_extension)
        }
        return sorted(accepted, key=lambda path: path.as_posix())

    def discover(self) -> list[Path]:
        """Return stable, deduplicated absolute frontend paths."""
        targets = self.explicit_candidates(require_extension=True)
        if targets is not None:
            return targets
        if not self.scope.is_dir() or not _is_within(self.scope, self.root):
            return []

        files: set[Path] = set()
        for dirpath, dirnames, filenames in os.walk(self.scope, followlinks=False):
            dirnames[:] = sorted(
                dirname
                for dirname in dirnames
                if self._directory_allowed(Path(dirpath) / dirname)
            )
            for filename in filenames:
                candidate = Path(dirpath) / filename
                if self.accepts(candidate):
                    files.add(candidate.resolve())
        return sorted(files, key=lambda path: path.as_posix())

    def relative_paths(self) -> list[str]:
        """Return discovered paths normalized relative to project root."""
        return [path.relative_to(self.root).as_posix() for path in self.discover()]
