"""Tooling auto-detection for UIdetox.

Scans the project root for configuration files and determines which
linters, formatters, compilers, package managers, backend frameworks,
database ORMs, and API layers are present.
"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field, asdict
from pathlib import Path

from uidetox.contracts import discover_schemas  # type: ignore

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
    all_linters: list[ToolInfo] = field(default_factory=list)
    all_formatters: list[ToolInfo] = field(default_factory=list)
    frontend: list[ToolInfo] = field(default_factory=list)
    backend: list[ToolInfo] = field(default_factory=list)
    database: list[ToolInfo] = field(default_factory=list)
    api: list[ToolInfo] = field(default_factory=list)
    contract_artifacts: dict[str, list[str]] = field(
        default_factory=lambda: {
            "schema_files": [],
            "dto_files": [],
            "contract_files": [],
        }
    )

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
        d["all_linters"] = [asdict(t) for t in self.all_linters] # type: ignore
        d["all_formatters"] = [asdict(t) for t in self.all_formatters] # type: ignore
        d["frontend"] = [asdict(t) for t in self.frontend] # type: ignore
        d["backend"] = [asdict(t) for t in self.backend] # type: ignore
        d["database"] = [asdict(t) for t in self.database] # type: ignore
        d["api"] = [asdict(t) for t in self.api] # type: ignore
        d["contract_artifacts"] = {
            "schema_files": list(self.contract_artifacts.get("schema_files", [])),
            "dto_files": list(self.contract_artifacts.get("dto_files", [])),
            "contract_files": list(self.contract_artifacts.get("contract_files", [])),
        }
        return d


def _find_any(root: Path, names: list[str]) -> str | None:
    """Return the first matching filename found in root."""
    for name in names:
        if name.endswith("*"):
            prefix = name[:-1] # type: ignore
            try:
                for f in root.iterdir():
                    if f.name.startswith(prefix) and f.is_file():
                        return f.name
            except PermissionError:
                continue
        elif (root / name).exists():
            return name
    return None


# Directories to skip during recursive file discovery.
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "vendor",
              "__pycache__", ".tox", "coverage", ".turbo", "out"}


def _safe_glob(root: Path, suffix: str, *, limit: int = 50) -> list[Path]:
    """Recursively find files with *suffix* while skipping heavy directories.

    Unlike ``root.glob("**/*<suffix>")``, this skips ``node_modules``,
    ``.git``, ``dist``, etc. and caps results at *limit* to avoid
    traversing enormous trees.
    """
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter dirnames in-place to control recursion
        keep = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith('.')]
        dirnames.clear()
        dirnames.extend(keep)
        for f in filenames:
            if f.endswith(suffix):
                results.append(Path(dirpath) / f)
                if len(results) >= limit:
                    return results
    return results


_pkg_json_cache: dict[str, dict[str, object]] = {}


def _get_all_deps(root: Path) -> dict[str, object]:
    """Return merged deps/devDeps from package.json (cached per root)."""
    key = str(root)
    if key in _pkg_json_cache:
        return _pkg_json_cache[key]
    pkg = root / "package.json"
    if not pkg.exists():
        _pkg_json_cache[key] = {}
        return {}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        merged = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        _pkg_json_cache[key] = merged
        return merged
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        _pkg_json_cache[key] = {}
        return {}


def _has_dep(root: Path, dep: str) -> bool:
    """Check if a dependency exists in package.json (cached)."""
    return dep in _get_all_deps(root)


def _local_bin_cmd(root: Path, binary: str, args: list[str]) -> str | None:
    """Return a local node_modules/.bin command if the binary exists."""
    local = root / "node_modules" / ".bin" / binary
    if not local.exists():
        return None
    suffix = f" {' '.join(args)}" if args else ""
    return f"./node_modules/.bin/{binary}{suffix}"


def _package_manager_exec(root: Path, cmd: str) -> str:
    """Wrap a project-local Node command with the detected package manager."""
    package_manager = detect_package_manager(root)
    if package_manager == "pnpm":
        return f"pnpm exec {cmd}"
    if package_manager == "bun":
        return f"bunx {cmd}"
    if package_manager == "yarn":
        return f"yarn {cmd}"
    return f"npx {cmd}"


def _npx_or_local(root: Path, cmd: str) -> str:
    """Return a package-manager-aware command for a project-local Node binary."""
    parts = shlex.split(cmd)
    if not parts:
        return cmd
    binary = parts[0]
    args = [p for i, p in enumerate(parts) if i > 0]
    local = _local_bin_cmd(root, binary, args)
    if local:
        return local
    return _package_manager_exec(root, cmd)


def _dlx_or_local(root: Path, package: str, binary: str, args: str = "") -> str:
    """Run an on-demand package manager command, preferring a local binary if present."""
    arg_parts = shlex.split(args) if args else []
    local = _local_bin_cmd(root, binary, arg_parts)
    if local:
        return local

    suffix = f" {args}" if args else ""
    package_manager = detect_package_manager(root)
    if package_manager == "pnpm":
        return f"pnpm dlx {package}{suffix}"
    if package_manager == "yarn":
        return f"yarn dlx {package}{suffix}"
    if package_manager == "bun":
        return f"bunx {package}{suffix}"
    return f"npx {package}{suffix}"


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


def detect_linters(root: Path) -> list[ToolInfo]:
    """Detect linters: biome, eslint, stylelint, markuplint."""
    found: list[ToolInfo] = []
    
    biome_cfg = _find_any(root, ["biome.json", "biome.jsonc"])
    if biome_cfg:
        found.append(ToolInfo(
            name="biome",
            config_file=biome_cfg,
            run_cmd=_npx_or_local(root, "biome check ."),
            fix_cmd=_npx_or_local(root, "biome check --write ."),
        ))

    eslint_cfg = _find_any(root, [
        "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
        ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
    ])
    if eslint_cfg or _has_dep(root, "eslint"):
        found.append(ToolInfo(
            name="eslint",
            config_file=eslint_cfg or "package.json",
            run_cmd=_npx_or_local(root, "eslint --format unix ."),
            fix_cmd=_npx_or_local(root, "eslint --fix ."),
        ))
        
    stylelint_cfg = _find_any(root, [
        ".stylelintrc", ".stylelintrc.js", ".stylelintrc.json", ".stylelintrc.yml",
        ".stylelintrc.yaml", "stylelint.config.js", "stylelint.config.mjs",
        "stylelint.config.cjs",
    ])
    if stylelint_cfg or _has_dep(root, "stylelint"):
        found.append(ToolInfo(
            name="stylelint",
            config_file=stylelint_cfg or "package.json",
            run_cmd=_npx_or_local(root, 'stylelint "**/*.{css,scss,sass,less}"'),
            fix_cmd=_npx_or_local(root, 'stylelint "**/*.{css,scss,sass,less}" --fix'),
        ))
        
    markuplint_cfg = _find_any(root, [
        ".markuplintrc", "markuplint.config.js", "markuplint.config.ts",
        "markuplint.config.mjs", "markuplint.config.cjs",
    ])
    if markuplint_cfg or _has_dep(root, "markuplint"):
        found.append(ToolInfo(
            name="markuplint",
            config_file=markuplint_cfg or "package.json",
            run_cmd=_npx_or_local(root, "markuplint **/*.html"),
            fix_cmd=_npx_or_local(root, "markuplint **/*.html --fix"),
        ))
    return found


def detect_linter(root: Path) -> ToolInfo | None:
    """Detect primary linter: biome > eslint."""
    linters = detect_linters(root)
    # Prefer biome if present, otherwise first one found
    for l in linters:
        if l.name == "biome":
            return l
    return linters[0] if linters else None


def detect_formatters(root: Path) -> list[ToolInfo]:
    """Detect formatters: biome, prettier."""
    found: list[ToolInfo] = []
    
    biome_cfg = _find_any(root, ["biome.json", "biome.jsonc"])
    if biome_cfg:
        found.append(ToolInfo(
            name="biome",
            config_file=biome_cfg,
            run_cmd=_npx_or_local(root, "biome check ."),
            fix_cmd=_npx_or_local(root, "biome check --write ."),
        ))

    prettier_cfg = _find_any(root, [
        ".prettierrc", ".prettierrc.js", ".prettierrc.json", ".prettierrc.yml",
        ".prettierrc.yaml", ".prettierrc.toml", "prettier.config.js",
        "prettier.config.mjs", "prettier.config.cjs",
    ])
    if prettier_cfg or _has_dep(root, "prettier"):
        found.append(ToolInfo(
            name="prettier",
            config_file=prettier_cfg or "package.json",
            run_cmd=_npx_or_local(root, "prettier --check ."),
            fix_cmd=_npx_or_local(root, "prettier --write ."),
        ))
    return found


def detect_formatter(root: Path) -> ToolInfo | None:
    """Detect primary formatter: biome (if already linter) > prettier."""
    formatters = detect_formatters(root)
    for f in formatters:
        if f.name == "biome":
            return f
    return formatters[0] if formatters else None


def detect_frontend(root: Path) -> list[ToolInfo]:
    """Detect frontend frameworks and tools."""
    found = []
    # Use 'if' (not 'elif') so projects with multiple frameworks are fully detected
    if _has_dep(root, "next"):
        cfg = _find_any(root, ["next.config.js", "next.config.mjs", "next.config.ts"])
        found.append(ToolInfo(name="next.js", config_file=cfg or "package.json", run_cmd=_npx_or_local(root, "next build")))
    if _has_dep(root, "nuxt"):
        found.append(ToolInfo(name="nuxt", config_file="nuxt.config.ts", run_cmd=_npx_or_local(root, "nuxt build")))
    if _has_dep(root, "@sveltejs/kit"):
        found.append(ToolInfo(name="sveltekit", config_file="svelte.config.js", run_cmd=_npx_or_local(root, "vite build")))
    if _has_dep(root, "@remix-run/react"):
        found.append(ToolInfo(name="remix", config_file="remix.config.js", run_cmd=_npx_or_local(root, "remix build")))
    if _has_dep(root, "astro"):
        cfg = _find_any(root, ["astro.config.mjs", "astro.config.js", "astro.config.ts"])
        found.append(ToolInfo(name="astro", config_file=cfg or "package.json", run_cmd=_npx_or_local(root, "astro check")))
        
    if _has_dep(root, "tailwindcss"):
        cfg = _find_any(root, ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.mjs"])
        found.append(ToolInfo(name="tailwindcss", config_file=cfg or "package.json", run_cmd=_npx_or_local(root, "tailwindcss build")))
    if _has_dep(root, "vite"):
        cfg = _find_any(root, ["vite.config.js", "vite.config.ts"])
        found.append(ToolInfo(name="vite", config_file=cfg or "package.json", run_cmd=_npx_or_local(root, "vite build")))
        
    return found


def detect_backend(root: Path) -> list[ToolInfo]:
    """Detect backend frameworks."""
    found = []
    # Use 'if' (not 'elif') so NestJS + Express co-existing projects detect both
    if _has_dep(root, "@nestjs/core"):
        found.append(ToolInfo(name="nestjs", config_file="nest-cli.json", run_cmd=_npx_or_local(root, "nest build")))
    if _has_dep(root, "express") and not _has_dep(root, "@nestjs/core"):
        found.append(ToolInfo(name="express", config_file="package.json", run_cmd="node -e \"process.exit(0)\""))
    if _has_dep(root, "fastify"):
        found.append(ToolInfo(name="fastify", config_file="package.json", run_cmd="node -e \"process.exit(0)\""))
    if _has_dep(root, "koa"):
        found.append(ToolInfo(name="koa", config_file="package.json", run_cmd="node -e \"process.exit(0)\""))
        
    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        cfg = "pyproject.toml" if (root / "pyproject.toml").exists() else "requirements.txt"
        found.append(ToolInfo(name="python", config_file=cfg, run_cmd="python -m pytest"))
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
        found.append(ToolInfo(name="knex", config_file="knexfile.js", run_cmd=_npx_or_local(root, "knex migrate:status")))
    if _has_dep(root, "typeorm"):
        found.append(ToolInfo(name="typeorm", config_file="ormconfig.json", run_cmd=_npx_or_local(root, "typeorm query")))
    if _has_dep(root, "sequelize"):
        found.append(ToolInfo(name="sequelize", config_file=".sequelizerc", run_cmd=_npx_or_local(root, "sequelize db:migrate:status")))
    return found


def detect_api(root: Path) -> list[ToolInfo]:
    """Detect API layer tools."""
    found = []
    openapi = _find_any(root, ["openapi.yaml", "openapi.yml", "openapi.json",
                                 "swagger.yaml", "swagger.yml", "swagger.json"])
    if openapi:
        found.append(ToolInfo(
            name="openapi",
            config_file=openapi,
            run_cmd=_dlx_or_local(root, "@redocly/cli", "redocly", f"lint {openapi}"),
        ))
    graphql_files = _safe_glob(root, ".graphql", limit=50)
    if graphql_files:
        found.append(ToolInfo(name="graphql", config_file=str(graphql_files[0]), run_cmd=_npx_or_local(root, "graphql-inspector validate")))
    if _has_dep(root, "@trpc/server") or _has_dep(root, "@trpc/client"):
        found.append(ToolInfo(name="trpc", config_file="package.json", run_cmd=_npx_or_local(root, "tsc --noEmit")))
    return found


def detect_contract_artifacts(root: Path, *, limit_per_bucket: int = 75) -> dict[str, list[str]]:
    """Detect schema/DTO/contract artifact files used for full-stack validation."""
    schema_files: list[str] = []
    dto_files: list[str] = []
    contract_files: list[str] = []

    # Canonical schema discovery (OpenAPI/GraphQL/Prisma)
    try:
        for schema_path in discover_schemas(root):
            try:
                rel = schema_path.relative_to(root).as_posix()
            except ValueError:
                rel = str(schema_path.as_posix())
            schema_files.append(rel)
            if len(schema_files) >= limit_per_bucket:
                break
    except Exception:
        # Contract discovery is additive-only; never fail tooling detection.
        pass

    # Heuristic DTO/contract discovery from source files
    exts = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".graphql", ".gql"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            path = Path(dirpath) / fname
            if path.suffix.lower() not in exts:
                continue

            lower_name = fname.lower()
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = str(path.as_posix())

            if (
                ("dto" in lower_name or lower_name.endswith(".dto.ts") or ".dto." in lower_name)
                and len(dto_files) < limit_per_bucket
            ):
                dto_files.append(rel)
                continue

            if (
                any(token in lower_name for token in ("contract", "schema", "validator", "zod", "valibot", "io-ts"))
                and len(contract_files) < limit_per_bucket
            ):
                contract_files.append(rel)

        if (
            len(dto_files) >= limit_per_bucket
            and len(contract_files) >= limit_per_bucket
        ):
            break

    return {
        "schema_files": sorted(set(schema_files)),
        "dto_files": sorted(set(dto_files)),
        "contract_files": sorted(set(contract_files)),
    }


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
        all_linters=detect_linters(root),
        all_formatters=detect_formatters(root),
        frontend=detect_frontend(root),
        backend=detect_backend(root),
        database=detect_database(root),
        api=detect_api(root),
        contract_artifacts=detect_contract_artifacts(root),
    )
