"""Shared mechanical diagnostic execution, parsing, and finding construction."""

from __future__ import annotations

import hashlib
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from uidetox.findings import Finding
from uidetox.utils import prepare_subprocess_cmd

_TSC_ERROR = re.compile(
    r"^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)$", re.MULTILINE
)
_LINT_ERROR = re.compile(
    r"^([^:\n]+?):(\d+):(\d+)(?::\s*|\s+-\s*|\s+)(.+)$", re.MULTILINE
)


@dataclass(frozen=True)
class MechanicalDiagnostic:
    path: str
    line: int
    column: int
    code: str
    message: str

    @property
    def signature(self) -> str:
        value = f"{self.code}\0{self.message.strip()}".encode()
        return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class MechanicalRun:
    returncode: int
    output: str
    error: str = ""

    @property
    def evidence_hash(self) -> str:
        value = f"{self.returncode}\0{self.error}\0{self.output}".encode()
        return hashlib.sha256(value).hexdigest()


def resolve_tool(
    tool: str, root: Path, config: dict | None = None
) -> dict[str, str | None]:
    from uidetox.state import load_config
    from uidetox.tooling import detect_linter, detect_typescript

    active_config = load_config(root) if config is None else config
    tooling = active_config.get("tooling", {})
    configured = tooling.get(tool) if isinstance(tooling, dict) else None
    if isinstance(configured, dict) and configured.get("run_cmd"):
        return dict(configured)

    detector = {
        "typescript": detect_typescript,
        "linter": detect_linter,
    }.get(tool)
    detected = detector(root) if detector else None
    if detected is None:
        return {}
    return {
        "name": detected.name,
        "run_cmd": detected.run_cmd,
        "fix_cmd": detected.fix_cmd,
    }


def run_diagnostics(
    tool: str, command: str, root: Path
) -> tuple[MechanicalRun, tuple[MechanicalDiagnostic, ...]]:
    try:
        argv, env = prepare_subprocess_cmd(command)
        result = subprocess.run(
            argv, capture_output=True, text=True, cwd=root, timeout=120, env=env
        )
        run = MechanicalRun(result.returncode, result.stdout + result.stderr)
    except FileNotFoundError:
        run = MechanicalRun(-1, "", "command_not_found")
    except subprocess.TimeoutExpired:
        run = MechanicalRun(-1, "", "timeout")
    return run, parse_diagnostics(tool, run.output)


def parse_diagnostics(tool: str, output: str) -> tuple[MechanicalDiagnostic, ...]:
    if tool == "typescript":
        return tuple(
            MechanicalDiagnostic(path.strip(), int(line), int(column), code, message.strip())
            for path, line, column, code, message in _TSC_ERROR.findall(output)
        )
    if tool == "linter":
        return tuple(
            MechanicalDiagnostic(path, int(line), int(column), "lint", message.strip())
            for path, line, column, message in _LINT_ERROR.findall(output)
            if path.startswith("/") or path.startswith(".") or ":" not in path
        )
    return ()


def diagnostic_finding(tool: str, diagnostic: MechanicalDiagnostic) -> Finding:
    prefix = "TSC" if tool == "typescript" else "LINT"
    queue_id = f"{prefix}-{str(uuid.uuid4())[:6].upper()}"
    message = (
        f"[{diagnostic.code}] {diagnostic.message} (line {diagnostic.line})"
        if tool == "typescript"
        else f"Lint: {diagnostic.message} (line {diagnostic.line})"
    )
    return Finding.create(
        detector_id=f"mechanical-{tool}-{diagnostic.signature[:16]}",
        category="code quality",
        severity="info",
        confidence=1.0,
        message=message,
        provenance="mechanical",
        evidence={"code": diagnostic.code, "message": diagnostic.message},
        source_anchor={
            "path": diagnostic.path,
            "line": diagnostic.line,
            "column": diagnostic.column,
        },
        suppression_key=f"{tool}:{diagnostic.signature}",
        verifier={"kind": "mechanical", "tool": tool, "signature": diagnostic.signature},
        legacy={"id": queue_id, "command": f"{prefix.lower()}-fix"},
    )
