"""Tooling auto-detection for UIdetox.

Scans the project root for configuration files and determines which
linters, formatters, compilers, package managers, backend frameworks,
database ORMs, and API layers are present.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path


_PYTHON_BACKEND_DEPS = {
    "aiohttp",
    "bottle",
    "django",
    "falcon",
    "fastapi",
    "flask",
    "gunicorn",
    "hypercorn",
    "pyramid",
    "quart",
    "sanic",
    "starlette",
    "tornado",
    "uvicorn",
}

_PYTHON_BACKEND_PATTERNS = [
    re.compile(r"\bFastAPI\s*\(", re.IGNORECASE),
    re.compile(r"\bFlask\s*\(", re.IGNORECASE),
    re.compile(r"\bAPIRouter\s*\(", re.IGNORECASE),
    re.compile(r"\bStarlette\s*\(", re.IGNORECASE),
    re.compile(r"\bSanic\s*\(", re.IGNORECASE),
    re.compile(r"\bQuart\s*\(", re.IGNORECASE),
    re.compile(r"uvicorn\.run\s*\(", re.IGNORECASE),
    re.compile(r"WSGI_APPLICATION", re.IGNORECASE),
    re.compile(r"ASGI_APPLICATION", re.IGNORECASE),
]

_PYTHON_BACKEND_ENTRY_FILES = [
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "app.py",
    "main.py",
    "server.py",
    "api.py",
]

_PYTHON_BACKEND_ALWAYS_ENTRY_FILES = {
    "manage.py",
    "wsgi.py",
    "asgi.py",
}

_PYTHON_BACKEND_SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".uidetox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "tests",
    "venv",
}


@dataclass
class ToolInfo:
    """A detected tool with its run command."""
    name: str
    config_file: str
    run_cmd: str
    fix_cmd: str | None = None


@dataclass
class ProjectProfile:
    """Everything we know about the project's tooling."""
    root: str = "."
    package_manager: str | None = None
    typescript: ToolInfo | None = None
    linter: ToolInfo | None = None
    formatter: ToolInfo | None = None
    frontend: list[ToolInfo] = field(default_factory=list)
    backend: list[ToolInfo] = field(default_factory=list)
    database: list[ToolInfo] = field(default_factory=list)
    api: list[ToolInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {}
        d["root"] = str(self.root) if self.root else None
        d["package_manager"] = self.package_manager
        
        ts = self.typescript
        ln = self.linter
        fm = self.formatter
        
        d["typescript"] = asdict(ts) if ts is not None else None # type: ignore
        d["linter"] = asdict(ln) if ln is not None else None # type: ignore
        d["formatter"] = asdict(fm) if fm is not None else None # type: ignore
        d["frontend"] = [asdict(t) for t in self.frontend] # type: ignore
        d["backend"] = [asdict(t) for t in self.backend] # type: ignore
        d["database"] = [asdict(t) for t in self.database] # type: ignore
        d["api"] = [asdict(t) for t in self.api] # type: ignore
        return d


def _find_any(root: Path, names: list[str]) -> str | None:
    """Return the first matching filename found in root."""
    for name in names:
        if name.endswith("*"):
            prefix = name[:-1] # type: ignore
            for f in root.iterdir():
                if f.name.startswith(prefix) and f.is_file():
                    return f.name
        elif (root / name).exists():
            return name
    return None


def _has_dep(root: Path, dep: str) -> bool:
    """Check if a dependency exists in package.json."""
    pkg = root / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        deps = data.get("dependencies", {}) or {}
        dev_deps = data.get("devDependencies", {}) or {}
        if not isinstance(deps, dict):
            deps = {}
        if not isinstance(dev_deps, dict):
            dev_deps = {}
        all_deps = {
            **deps,
            **dev_deps,
        }
        return dep in all_deps
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False


def _normalize_dep_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _extract_requirement_name(spec: str) -> str | None:
    spec = spec.split("#", 1)[0].split(";", 1)[0].strip()
    if not spec or spec.startswith(("-", "--")):
        return None
    match = re.match(r"([A-Za-z0-9_.-]+)", spec)
    if not match:
        return None
    return _normalize_dep_name(match.group(1))


def _read_pyproject_dependency_names(root: Path) -> set[str]:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return set()

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return set()

    deps: set[str] = set()

    def add_spec(spec: str) -> None:
        dep_name = _extract_requirement_name(spec)
        if dep_name:
            deps.add(dep_name)

    project = data.get("project", {})
    if isinstance(project, dict):
        for spec in project.get("dependencies", []) or []:
            if isinstance(spec, str):
                add_spec(spec)

        optional = project.get("optional-dependencies", {}) or {}
        if isinstance(optional, dict):
            for group_specs in optional.values():
                if isinstance(group_specs, list):
                    for spec in group_specs:
                        if isinstance(spec, str):
                            add_spec(spec)

    dependency_groups = data.get("dependency-groups", {}) or {}
    if isinstance(dependency_groups, dict):
        for group_specs in dependency_groups.values():
            if isinstance(group_specs, list):
                for spec in group_specs:
                    if isinstance(spec, str):
                        add_spec(spec)

    tool = data.get("tool", {}) or {}
    if isinstance(tool, dict):
        poetry = tool.get("poetry", {}) or {}
        if isinstance(poetry, dict):
            poetry_deps = poetry.get("dependencies", {}) or {}
            if isinstance(poetry_deps, dict):
                for name in poetry_deps:
                    dep_name = _normalize_dep_name(name)
                    if dep_name and dep_name != "python":
                        deps.add(dep_name)

            poetry_groups = poetry.get("group", {}) or {}
            if isinstance(poetry_groups, dict):
                for group in poetry_groups.values():
                    if not isinstance(group, dict):
                        continue
                    group_deps = group.get("dependencies", {}) or {}
                    if isinstance(group_deps, dict):
                        for name in group_deps:
                            dep_name = _normalize_dep_name(name)
                            if dep_name and dep_name != "python":
                                deps.add(dep_name)

    return deps


def _iter_requirements_files(root: Path) -> list[Path]:
    files = list(root.glob("requirements*.txt"))
    req_dir = root / "requirements"
    if req_dir.exists():
        files.extend(req_dir.glob("*.txt"))

    unique_files: list[Path] = []
    seen: set[str] = set()
    for file_path in files:
        key = str(file_path.resolve())
        if key not in seen:
            seen.add(key)
            unique_files.append(file_path)
    return unique_files


def _requirements_file_has_backend_dep(req_path: Path) -> bool:
    try:
        for line in req_path.read_text(encoding="utf-8").splitlines():
            dep_name = _extract_requirement_name(line)
            if dep_name in _PYTHON_BACKEND_DEPS:
                return True
    except (OSError, UnicodeDecodeError):
        return False
    return False


def _path_is_in_skipped_dir(path: Path) -> bool:
    return any(part in _PYTHON_BACKEND_SKIP_DIRS for part in path.parts)


def _find_python_backend_entrypoint(root: Path) -> str | None:
    for entry_name in _PYTHON_BACKEND_ALWAYS_ENTRY_FILES:
        direct = root / entry_name
        if direct.exists():
            return entry_name

    for entry_name in _PYTHON_BACKEND_ENTRY_FILES:
        for candidate in root.rglob(entry_name):
            if _path_is_in_skipped_dir(candidate):
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if any(pattern.search(content) for pattern in _PYTHON_BACKEND_PATTERNS):
                return candidate.relative_to(root).as_posix()

    return None


def _detect_python_backend_config(root: Path) -> str | None:
    pyproject_deps = _read_pyproject_dependency_names(root)
    if pyproject_deps & _PYTHON_BACKEND_DEPS:
        return "pyproject.toml"

    for req_file in _iter_requirements_files(root):
        if _requirements_file_has_backend_dep(req_file):
            return req_file.relative_to(root).as_posix()

    return _find_python_backend_entrypoint(root)


def _npx_or_local(root: Path, cmd: str) -> str:
    """Return npx prefix or local node_modules/.bin/ path."""
    local = root / "node_modules" / ".bin" / cmd.split()[0]
    if local.exists():
        return f"./node_modules/.bin/{cmd}"
    return f"npx {cmd}"


def detect_package_manager(root: Path) -> str | None:
    """Detect which package manager the project uses."""
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "package-lock.json").exists():
        return "npm"
    if (root / "package.json").exists():
        return "npm"  # default if package.json exists
    return None


def detect_typescript(root: Path) -> ToolInfo | None:
    """Detect TypeScript configuration."""
    cfg = _find_any(root, ["tsconfig.json", "tsconfig.app.json", "tsconfig.build.json"])
    if cfg:
        return ToolInfo(
            name="typescript",
            config_file=cfg,
            run_cmd=_npx_or_local(root, "tsc --noEmit"),
            fix_cmd=None,
        )
    return None


def detect_linter(root: Path) -> ToolInfo | None:
    """Detect linter: biome > eslint."""
    biome_cfg = _find_any(root, ["biome.json", "biome.jsonc"])
    if biome_cfg:
        return ToolInfo(
            name="biome",
            config_file=biome_cfg,
            run_cmd=_npx_or_local(root, "biome check ."),
            fix_cmd=_npx_or_local(root, "biome check --write ."),
        )

    eslint_cfg = _find_any(root, [
        "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
    ])
    if eslint_cfg or _has_dep(root, "eslint"):
        return ToolInfo(
            name="eslint",
            config_file=eslint_cfg or "package.json",
            run_cmd=_npx_or_local(root, "eslint --format unix ."),
            fix_cmd=_npx_or_local(root, "eslint --fix ."),
        )
    return None


def detect_formatter(root: Path) -> ToolInfo | None:
    """Detect formatter: biome (if already linter) > prettier."""
    # If biome is detected, it handles formatting too
    biome_cfg = _find_any(root, ["biome.json", "biome.jsonc"])
    if biome_cfg:
        return ToolInfo(
            name="biome",
            config_file=biome_cfg,
            run_cmd=_npx_or_local(root, "biome format --check ."),
            fix_cmd=_npx_or_local(root, "biome format --write ."),
        )

    prettier_cfg = _find_any(root, [
        ".prettierrc", ".prettierrc.js", ".prettierrc.json", ".prettierrc.yml",
        ".prettierrc.yaml", ".prettierrc.toml", "prettier.config.js",
        "prettier.config.mjs", "prettier.config.cjs",
    ])
    if prettier_cfg or _has_dep(root, "prettier"):
        return ToolInfo(
            name="prettier",
            config_file=prettier_cfg or "package.json",
            run_cmd=_npx_or_local(root, "prettier --check ."),
            fix_cmd=_npx_or_local(root, "prettier --write ."),
        )
    return None


def detect_frontend(root: Path) -> list[ToolInfo]:
    """Detect frontend frameworks and tools."""
    found = []
    if _has_dep(root, "next"):
        cfg = _find_any(root, ["next.config.js", "next.config.mjs", "next.config.ts"])
        found.append(ToolInfo(name="next.js", config_file=cfg or "package.json", run_cmd="npx next build"))
    elif _has_dep(root, "nuxt"):
        found.append(ToolInfo(name="nuxt", config_file="nuxt.config.ts", run_cmd="npx nuxt build"))
    elif _has_dep(root, "@sveltejs/kit"):
        found.append(ToolInfo(name="sveltekit", config_file="svelte.config.js", run_cmd="npx vite build"))
    elif _has_dep(root, "@remix-run/react"):
        found.append(ToolInfo(name="remix", config_file="remix.config.js", run_cmd="npx remix build"))
    elif _has_dep(root, "astro"):
        cfg = _find_any(root, ["astro.config.mjs", "astro.config.js", "astro.config.ts"])
        found.append(ToolInfo(name="astro", config_file=cfg or "package.json", run_cmd="npx astro check"))
        
    if _has_dep(root, "tailwindcss"):
        cfg = _find_any(root, ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs"])
        found.append(ToolInfo(name="tailwindcss", config_file=cfg or "package.json", run_cmd="npx tailwindcss build"))
    if _has_dep(root, "vite"):
        cfg = _find_any(root, ["vite.config.js", "vite.config.ts"])
        found.append(ToolInfo(name="vite", config_file=cfg or "package.json", run_cmd="npx vite build"))
        
    return found


def detect_backend(root: Path) -> list[ToolInfo]:
    """Detect backend frameworks."""
    found = []
    if _has_dep(root, "@nestjs/core"):
        found.append(ToolInfo(name="nestjs", config_file="nest-cli.json", run_cmd=_npx_or_local(root, "nest build")))
    elif _has_dep(root, "express") or _has_dep(root, "fastify") or _has_dep(root, "koa"):
        found.append(ToolInfo(name="node.js", config_file="package.json", run_cmd="node -e \"process.exit(0)\""))

    python_backend_config = _detect_python_backend_config(root)
    if python_backend_config:
        found.append(ToolInfo(name="python", config_file=python_backend_config, run_cmd="python -m pytest"))
    if (root / "go.mod").exists():
        found.append(ToolInfo(name="go", config_file="go.mod", run_cmd="go vet ./..."))
    if (root / "Cargo.toml").exists():
        found.append(ToolInfo(name="rust", config_file="Cargo.toml", run_cmd="cargo check"))
    if (root / "pom.xml").exists():
        found.append(ToolInfo(name="java-maven", config_file="pom.xml", run_cmd="mvn compile"))
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        found.append(ToolInfo(name="java-gradle", config_file="build.gradle", run_cmd="gradle build"))
    return found


def detect_database(root: Path) -> list[ToolInfo]:
    """Detect database/ORM tools."""
    found = []
    prisma = root / "prisma" / "schema.prisma"
    if prisma.exists():
        found.append(ToolInfo(name="prisma", config_file="prisma/schema.prisma",
                              run_cmd=_npx_or_local(root, "prisma validate")))
    drizzle = _find_any(root, ["drizzle.config.ts", "drizzle.config.js"])
    if drizzle:
        found.append(ToolInfo(name="drizzle", config_file=drizzle,
                              run_cmd=_npx_or_local(root, "drizzle-kit check")))
    if _has_dep(root, "knex"):
        found.append(ToolInfo(name="knex", config_file="knexfile.js", run_cmd="npx knex migrate:status"))
    if _has_dep(root, "typeorm"):
        found.append(ToolInfo(name="typeorm", config_file="ormconfig.json", run_cmd="npx typeorm query"))
    if _has_dep(root, "sequelize"):
        found.append(ToolInfo(name="sequelize", config_file=".sequelizerc", run_cmd="npx sequelize db:migrate:status"))
    return found


def detect_api(root: Path) -> list[ToolInfo]:
    """Detect API layer tools."""
    found = []
    openapi = _find_any(root, ["openapi.yaml", "openapi.yml", "openapi.json",
                                 "swagger.yaml", "swagger.yml", "swagger.json"])
    if openapi:
        found.append(ToolInfo(name="openapi", config_file=openapi, run_cmd=f"npx @redocly/cli lint {openapi}"))
    graphql_files = list(root.glob("**/*.graphql"))
    if graphql_files and len(graphql_files) < 50:
        found.append(ToolInfo(name="graphql", config_file=str(graphql_files[0]), run_cmd="npx graphql-inspector validate"))
    if _has_dep(root, "@trpc/server") or _has_dep(root, "@trpc/client"):
        found.append(ToolInfo(name="trpc", config_file="package.json", run_cmd="npx tsc --noEmit"))
    return found


def detect_all(root: Path | None = None) -> ProjectProfile:
    """Run all detections and return a ProjectProfile."""
    if root is None:
        root = Path.cwd()
    root = Path(root)

    return ProjectProfile(
        root=str(root),
        package_manager=detect_package_manager(root),
        typescript=detect_typescript(root),
        linter=detect_linter(root),
        formatter=detect_formatter(root),
        frontend=detect_frontend(root),
        backend=detect_backend(root),
        database=detect_database(root),
        api=detect_api(root),
    )
