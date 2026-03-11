"""Tooling auto-detection for UIdetox.

Scans the project root for configuration files and determines which
linters, formatters, compilers, package managers, backend frameworks,
database ORMs, and API layers are present.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


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
    backend: list[ToolInfo] = field(default_factory=list)
    database: list[ToolInfo] = field(default_factory=list)
    api: list[ToolInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {}
        d["root"] = self.root
        d["package_manager"] = self.package_manager
        d["typescript"] = asdict(self.typescript) if self.typescript else None
        d["linter"] = asdict(self.linter) if self.linter else None
        d["formatter"] = asdict(self.formatter) if self.formatter else None
        d["backend"] = [asdict(t) for t in self.backend]
        d["database"] = [asdict(t) for t in self.database]
        d["api"] = [asdict(t) for t in self.api]
        return d


def _find_any(root: Path, names: list[str]) -> str | None:
    """Return the first matching filename found in root."""
    for name in names:
        if name.endswith("*"):
            prefix = name[:-1]
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
        all_deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        return dep in all_deps
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False


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


def detect_backend(root: Path) -> list[ToolInfo]:
    """Detect backend frameworks."""
    found = []
    if _has_dep(root, "@nestjs/core"):
        found.append(ToolInfo(name="nestjs", config_file="nest-cli.json", run_cmd=_npx_or_local(root, "nest build")))
    elif _has_dep(root, "express") or _has_dep(root, "fastify") or _has_dep(root, "koa"):
        found.append(ToolInfo(name="node.js", config_file="package.json", run_cmd="node --check ."))
        
    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        found.append(ToolInfo(name="python", config_file="pyproject.toml", run_cmd="python -m pytest"))
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
        backend=detect_backend(root),
        database=detect_database(root),
        api=detect_api(root),
    )
