"""Consent-aware detection and provisioning for optional UIdetox capabilities."""

from __future__ import annotations

import importlib.util
import os
import posixpath
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from importlib import metadata
from pathlib import Path

CODEBASE_MEMORY_DOCS_URL = "https://github.com/DeusData/codebase-memory-mcp#quick-start"
DEFAULT_COMMAND_TIMEOUT = 300
DEFAULT_OUTPUT_LIMIT = 4_000


class Capability(str, Enum):
    CODEBASE_MEMORY = "codebase-memory"
    PILLOW = "pillow"
    PLAYWRIGHT = "playwright"
    CHROMIUM = "chromium"


CAPABILITY_ORDER = (
    Capability.CODEBASE_MEMORY,
    Capability.PILLOW,
    Capability.PLAYWRIGHT,
    Capability.CHROMIUM,
)


class ProbeState(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class InstallMethod(str, Enum):
    UV = "uv"
    PIP = "pip"


class InvocationKind(str, Enum):
    ACTIVE_PYTHON = "active_python"
    UV_TOOL = "uv_tool"
    UVX = "uvx"


class SetupOutcome(str, Enum):
    EXECUTED = "executed"
    VERIFIED = "verified"
    SKIPPED = "skipped"
    NEEDS_ACTION = "needs_action"
    FAILED = "failed"


class VerificationMode(str, Enum):
    CURRENT_ENVIRONMENT = "current_environment"
    DURABLE_UV_OPERATION = "durable_uv_operation"


@dataclass(frozen=True)
class CommandExecution:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def _default_runner(argv: tuple[str, ...], timeout: int) -> CommandExecution:
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )
    return CommandExecution(
        argv=argv,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _default_chromium_probe() -> ProbeState:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ProbeState.MISSING

    try:
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
            if executable.is_file() and os.access(executable, os.X_OK):
                return ProbeState.AVAILABLE
            return ProbeState.MISSING
    except Exception:
        return ProbeState.UNKNOWN


def _default_mcp_probe(executable: str) -> ProbeState:
    try:
        completed = subprocess.run(
            [executable, "cli", "list_projects", "{}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ProbeState.UNKNOWN
    return ProbeState.AVAILABLE if completed.returncode == 0 else ProbeState.UNKNOWN


@dataclass(frozen=True)
class CapabilityEnvironment:
    """Injectable process boundary for detection, prompting, and execution."""

    interactive: bool
    input_fn: Callable[[str], str]
    output_fn: Callable[[str], None]
    python_executable: str
    prefix: str
    environ: Mapping[str, str]
    distribution_version: Callable[[str], str]
    find_spec: Callable[[str], object | None]
    which: Callable[[str], str | None]
    chromium_probe: Callable[[], ProbeState]
    runner: Callable[[tuple[str, ...], int], CommandExecution]
    mcp_probe: Callable[[str], ProbeState] = _default_mcp_probe

    @classmethod
    def from_system(
        cls,
        *,
        interactive: bool | None = None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> CapabilityEnvironment:
        if interactive is None:
            interactive = bool(sys.stdin.isatty() and sys.stdout.isatty())
        return cls(
            interactive=interactive,
            input_fn=input_fn,
            output_fn=output_fn,
            python_executable=sys.executable,
            prefix=sys.prefix,
            environ=dict(os.environ),
            distribution_version=metadata.version,
            find_spec=importlib.util.find_spec,
            which=shutil.which,
            chromium_probe=_default_chromium_probe,
            runner=_default_runner,
            mcp_probe=_default_mcp_probe,
        )


@dataclass(frozen=True)
class CapabilityStatus:
    capability: Capability
    distribution: ProbeState = ProbeState.NOT_APPLICABLE
    importable: ProbeState = ProbeState.NOT_APPLICABLE
    runtime: ProbeState = ProbeState.NOT_APPLICABLE
    command: ProbeState = ProbeState.NOT_APPLICABLE
    mcp: ProbeState = ProbeState.NOT_APPLICABLE
    version: str | None = None
    detail: str = ""

    @property
    def ready(self) -> bool:
        if self.capability is Capability.CODEBASE_MEMORY:
            return (
                self.command is ProbeState.AVAILABLE
                and self.mcp is ProbeState.AVAILABLE
            )
        if self.capability in {Capability.PILLOW, Capability.PLAYWRIGHT}:
            return (
                self.distribution is ProbeState.AVAILABLE
                and self.importable is ProbeState.AVAILABLE
            )
        return self.runtime is ProbeState.AVAILABLE


@dataclass(frozen=True)
class SetupAction:
    capabilities: tuple[Capability, ...]
    argv: tuple[str, ...] | None
    guidance: str | None = None
    verification: VerificationMode = VerificationMode.CURRENT_ENVIRONMENT


@dataclass(frozen=True)
class CapabilitySetupResult:
    capabilities: tuple[Capability, ...]
    outcome: SetupOutcome
    argv: tuple[str, ...] | None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    message: str = ""


@dataclass(frozen=True)
class CapabilityProvisioningResult:
    complete: bool
    skipped: bool
    statuses: tuple[CapabilityStatus, ...]
    results: tuple[CapabilitySetupResult, ...]


def _probe_distribution(
    name: str,
    environment: CapabilityEnvironment,
) -> tuple[ProbeState, str | None]:
    try:
        return ProbeState.AVAILABLE, environment.distribution_version(name)
    except metadata.PackageNotFoundError:
        return ProbeState.MISSING, None
    except Exception:
        return ProbeState.UNKNOWN, None


def _probe_import(name: str, environment: CapabilityEnvironment) -> ProbeState:
    try:
        return (
            ProbeState.AVAILABLE
            if environment.find_spec(name) is not None
            else ProbeState.MISSING
        )
    except Exception:
        return ProbeState.UNKNOWN


def detect_capabilities(
    environment: CapabilityEnvironment | None = None,
) -> tuple[CapabilityStatus, ...]:
    """Detect optional capabilities without importing them at module import time."""

    environment = environment or CapabilityEnvironment.from_system()
    codebase_path = environment.which("codebase-memory-mcp")
    mcp_state = ProbeState.UNKNOWN
    if codebase_path is not None:
        try:
            mcp_state = environment.mcp_probe(codebase_path)
        except Exception:
            mcp_state = ProbeState.UNKNOWN
    codebase = CapabilityStatus(
        capability=Capability.CODEBASE_MEMORY,
        command=(
            ProbeState.AVAILABLE if codebase_path is not None else ProbeState.MISSING
        ),
        mcp=mcp_state,
        detail=(
            f"External MCP adapter. Command: {codebase_path}. Agent connection must "
            f"be verified after restart; MCP probe: {mcp_state.value}. "
            f"{CODEBASE_MEMORY_DOCS_URL}"
            if codebase_path is not None
            else f"External MCP adapter not found. {CODEBASE_MEMORY_DOCS_URL}"
        ),
    )

    pillow_distribution, pillow_version = _probe_distribution("Pillow", environment)
    pillow_import = _probe_import("PIL", environment)
    pillow = CapabilityStatus(
        capability=Capability.PILLOW,
        distribution=pillow_distribution,
        importable=pillow_import,
        version=pillow_version,
        detail="Pillow is distributed as `Pillow` and imported as `PIL`.",
    )

    playwright_distribution, playwright_version = _probe_distribution(
        "playwright",
        environment,
    )
    playwright_import = _probe_import("playwright", environment)
    playwright = CapabilityStatus(
        capability=Capability.PLAYWRIGHT,
        distribution=playwright_distribution,
        importable=playwright_import,
        version=playwright_version,
        detail="Playwright Python package; browser binaries are checked separately.",
    )

    chromium_state = ProbeState.UNKNOWN
    chromium_detail = "Install and import Playwright before checking Chromium."
    if playwright_import is ProbeState.AVAILABLE:
        try:
            chromium_state = environment.chromium_probe()
            chromium_detail = "Playwright-managed Chromium executable readiness."
        except Exception as error:
            chromium_state = ProbeState.UNKNOWN
            chromium_detail = f"Chromium readiness could not be verified: {error}"
    chromium = CapabilityStatus(
        capability=Capability.CHROMIUM,
        runtime=chromium_state,
        detail=chromium_detail,
    )
    return codebase, pillow, playwright, chromium


def _normalized_location(value: str) -> str:
    expanded = os.path.expanduser(value).replace("\\", "/")
    return posixpath.normpath(expanded).rstrip("/").lower()


def _is_within_location(path: str, parent: str) -> bool:
    return path == parent or path.startswith(f"{parent}/")


def detect_invocation_kind(
    prefix: str,
    environ: Mapping[str, str],
) -> InvocationKind:
    """Distinguish persistent uv tools from disposable uvx cache environments."""

    normalized_prefix = _normalized_location(prefix)
    uv_tool_dir = environ.get("UV_TOOL_DIR")
    if uv_tool_dir and _is_within_location(
        normalized_prefix,
        _normalized_location(uv_tool_dir),
    ):
        return InvocationKind.UV_TOOL
    uv_cache_dir = environ.get("UV_CACHE_DIR")
    if uv_cache_dir and _is_within_location(
        normalized_prefix,
        _normalized_location(uv_cache_dir),
    ):
        return InvocationKind.UVX

    if "/uv/tools/" in normalized_prefix:
        return InvocationKind.UV_TOOL
    if any(
        cache_marker in normalized_prefix
        for cache_marker in ("/cache/uv/", "/uv/cache/")
    ) and any(marker in normalized_prefix for marker in ("/archive", "/environments")):
        return InvocationKind.UVX
    return InvocationKind.ACTIVE_PYTHON


def _ordered_unique(capabilities: Sequence[Capability]) -> tuple[Capability, ...]:
    selected = set(capabilities)
    return tuple(
        capability for capability in CAPABILITY_ORDER if capability in selected
    )


def build_setup_plan(
    capabilities: Sequence[Capability],
    method: InstallMethod,
    environment: CapabilityEnvironment | None = None,
) -> tuple[SetupAction, ...]:
    """Build allowlisted argv actions; returned strings are never shell commands."""

    environment = environment or CapabilityEnvironment.from_system()
    selected = _ordered_unique(capabilities)
    invocation = detect_invocation_kind(environment.prefix, environment.environ)
    if method is InstallMethod.PIP and invocation is InvocationKind.UVX:
        raise ValueError(
            "Cannot mutate a disposable uvx environment with pip; choose durable uv "
            "tool installation."
        )

    actions: list[SetupAction] = []
    if Capability.CODEBASE_MEMORY in selected:
        executable = environment.which("codebase-memory-mcp")
        guidance = (
            "Install the external codebase-memory MCP adapter from its official "
            f"guide, restart the agent, then rerun UIdetox: "
            f"{CODEBASE_MEMORY_DOCS_URL}"
            if executable is None
            else (
                f"The external adapter exists at {executable}, but its agent "
                "configuration must be run outside this active agent session because "
                "it restarts MCP processes. Follow the official guide, restart the "
                f"agent, then rerun UIdetox: {CODEBASE_MEMORY_DOCS_URL}"
            )
        )
        actions.append(
            SetupAction(
                capabilities=(Capability.CODEBASE_MEMORY,),
                argv=None,
                guidance=guidance,
            )
        )

    python_capabilities = tuple(
        capability
        for capability in (Capability.PILLOW, Capability.PLAYWRIGHT)
        if capability in selected
    )
    if python_capabilities:
        extra = "capture" if Capability.PLAYWRIGHT in python_capabilities else "visual"
        package = f"uidetox[{extra}]"
        if method is InstallMethod.UV:
            uv = environment.which("uv") or "uv"
            argv = (uv, "tool", "install", package)
            verification = VerificationMode.DURABLE_UV_OPERATION
        else:
            argv = (
                environment.python_executable,
                "-m",
                "pip",
                "install",
                package,
            )
            verification = VerificationMode.CURRENT_ENVIRONMENT
        actions.append(
            SetupAction(
                capabilities=python_capabilities,
                argv=argv,
                verification=verification,
            )
        )

    if Capability.CHROMIUM in selected:
        if method is InstallMethod.UV:
            uv = environment.which("uv") or "uv"
            argv = (
                uv,
                "tool",
                "run",
                "--from",
                "playwright",
                "playwright",
                "install",
                "chromium",
            )
            verification = VerificationMode.DURABLE_UV_OPERATION
        else:
            argv = (
                environment.python_executable,
                "-m",
                "playwright",
                "install",
                "chromium",
            )
            verification = VerificationMode.CURRENT_ENVIRONMENT
        actions.append(
            SetupAction(
                capabilities=(Capability.CHROMIUM,),
                argv=argv,
                verification=verification,
            )
        )
    return tuple(actions)


def _bounded(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}… [truncated]"


def _executable_available(
    executable: str,
    environment: CapabilityEnvironment,
) -> bool:
    if executable == environment.python_executable:
        return True
    return environment.which(Path(executable).name) is not None


def execute_setup_plan(
    plan: Sequence[SetupAction],
    environment: CapabilityEnvironment | None = None,
    *,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
    output_limit: int = DEFAULT_OUTPUT_LIMIT,
) -> tuple[CapabilitySetupResult, ...]:
    """Execute consented actions with bounded output and structured failures."""

    environment = environment or CapabilityEnvironment.from_system()
    results: list[CapabilitySetupResult] = []
    for action in plan:
        if action.argv is None:
            results.append(
                CapabilitySetupResult(
                    capabilities=action.capabilities,
                    outcome=SetupOutcome.NEEDS_ACTION,
                    argv=None,
                    message=action.guidance or "Manual setup required.",
                )
            )
            continue
        if not _executable_available(action.argv[0], environment):
            results.append(
                CapabilitySetupResult(
                    capabilities=action.capabilities,
                    outcome=SetupOutcome.FAILED,
                    argv=action.argv,
                    message=f"Executable is unavailable: {action.argv[0]}",
                )
            )
            continue

        environment.output_fn(f"Running approved argv: {list(action.argv)!r}")
        try:
            execution = environment.runner(action.argv, timeout)
        except (OSError, subprocess.SubprocessError) as error:
            results.append(
                CapabilitySetupResult(
                    capabilities=action.capabilities,
                    outcome=SetupOutcome.FAILED,
                    argv=action.argv,
                    message=str(error),
                )
            )
            continue
        outcome = (
            SetupOutcome.EXECUTED if execution.returncode == 0 else SetupOutcome.FAILED
        )
        results.append(
            CapabilitySetupResult(
                capabilities=action.capabilities,
                outcome=outcome,
                argv=action.argv,
                returncode=execution.returncode,
                stdout=_bounded(execution.stdout, output_limit),
                stderr=_bounded(execution.stderr, output_limit),
                message=(
                    "Command completed."
                    if outcome is SetupOutcome.EXECUTED
                    else f"Command exited with status {execution.returncode}."
                ),
            )
        )
    return tuple(results)


def _prompt_selection(
    statuses: tuple[CapabilityStatus, ...],
    environment: CapabilityEnvironment,
) -> tuple[tuple[Capability, ...], bool] | None:
    missing = tuple(status.capability for status in statuses if not status.ready)
    environment.output_fn("Optional recommended capabilities:")
    for status in statuses:
        label = "ready" if status.ready else "not ready"
        environment.output_fn(f"  - {status.capability.value}: {label}")
    if not missing:
        environment.output_fn("All optional capabilities are already ready.")
        return (), False

    try:
        answer = environment.input_fn(
            "Set up all missing optional capabilities? [Y/n/custom] "
        )
    except (EOFError, KeyboardInterrupt):
        return None
    normalized = answer.strip().lower()
    if normalized in {"n", "no", "none"}:
        return (), True
    if normalized in {"", "y", "yes", "all"}:
        return missing, False
    if normalized == "custom":
        try:
            normalized = (
                environment.input_fn(
                    "Capabilities (comma-separated: codebase-memory,pillow,"
                    "playwright,chromium; blank skips all): "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            return None
    if not normalized:
        return (), True

    requested = {item.strip() for item in normalized.split(",") if item.strip()}
    lookup = {capability.value: capability for capability in CAPABILITY_ORDER}
    if not requested <= lookup.keys():
        environment.output_fn("Unknown capability selection; nothing was installed.")
        return None
    return _ordered_unique(tuple(lookup[item] for item in requested)), False


def _prompt_method(
    selected: tuple[Capability, ...],
    environment: CapabilityEnvironment,
) -> InstallMethod | None:
    needs_python = any(
        capability in {Capability.PILLOW, Capability.PLAYWRIGHT, Capability.CHROMIUM}
        for capability in selected
    )
    if not needs_python:
        return InstallMethod.PIP

    invocation = detect_invocation_kind(environment.prefix, environment.environ)
    if invocation is InvocationKind.UVX:
        environment.output_fn(
            "Current uvx environment is disposable; using durable `uv tool install`."
        )
        return InstallMethod.UV

    default = InstallMethod.UV if environment.which("uv") else InstallMethod.PIP
    try:
        answer = environment.input_fn(
            f"Python capability installer [uv/pip] (default {default.value}): "
        )
    except (EOFError, KeyboardInterrupt):
        return None
    normalized = answer.strip().lower()
    if not normalized:
        return default
    try:
        return InstallMethod(normalized)
    except ValueError:
        environment.output_fn("Unknown installer; nothing was installed.")
        return None


def provision_capabilities(
    environment: CapabilityEnvironment | None = None,
) -> CapabilityProvisioningResult:
    """Prompt, execute, and verify optional setup without silent installation."""

    environment = environment or CapabilityEnvironment.from_system()
    statuses = detect_capabilities(environment)
    if not environment.interactive:
        return CapabilityProvisioningResult(
            complete=False,
            skipped=False,
            statuses=statuses,
            results=(),
        )

    selection = _prompt_selection(statuses, environment)
    if selection is None:
        return CapabilityProvisioningResult(
            complete=False,
            skipped=False,
            statuses=statuses,
            results=(),
        )
    selected, skipped = selection
    if skipped or not selected:
        return CapabilityProvisioningResult(
            complete=True,
            skipped=skipped,
            statuses=statuses,
            results=(),
        )

    status_by_capability = {status.capability: status for status in statuses}
    pending = tuple(
        capability
        for capability in selected
        if not status_by_capability[capability].ready
    )
    if not pending:
        return CapabilityProvisioningResult(
            complete=True,
            skipped=False,
            statuses=statuses,
            results=(),
        )

    method = _prompt_method(pending, environment)
    if method is None:
        return CapabilityProvisioningResult(
            complete=False,
            skipped=False,
            statuses=statuses,
            results=(),
        )
    try:
        plan = build_setup_plan(pending, method, environment)
    except ValueError as error:
        environment.output_fn(str(error))
        return CapabilityProvisioningResult(
            complete=False,
            skipped=False,
            statuses=statuses,
            results=(),
        )

    executed = execute_setup_plan(plan, environment)
    verified_statuses = detect_capabilities(environment)
    verified_by_capability = {status.capability: status for status in verified_statuses}
    verified_results: list[CapabilitySetupResult] = []
    for action, result in zip(plan, executed):
        if (
            result.outcome is SetupOutcome.EXECUTED
            and action.verification is VerificationMode.DURABLE_UV_OPERATION
        ):
            result = replace(
                result,
                outcome=SetupOutcome.VERIFIED,
                message=(
                    "Durable uv operation verified. Re-run UIdetox from the installed "
                    "tool; the current process environment is unchanged."
                ),
            )
        elif result.outcome is SetupOutcome.EXECUTED and all(
            verified_by_capability[capability].ready
            for capability in result.capabilities
        ):
            result = replace(
                result,
                outcome=SetupOutcome.VERIFIED,
                message="Capability verified.",
            )
        elif result.outcome is SetupOutcome.EXECUTED:
            result = replace(
                result,
                outcome=SetupOutcome.NEEDS_ACTION,
                message="Command completed, but capability verification is incomplete.",
            )
        verified_results.append(result)

    for result in verified_results:
        labels = ", ".join(capability.value for capability in result.capabilities)
        environment.output_fn(f"{labels}: {result.outcome.value} — {result.message}")
        if result.stderr:
            environment.output_fn(f"  stderr: {result.stderr}")

    complete = bool(verified_results) and all(
        result.outcome is SetupOutcome.VERIFIED for result in verified_results
    )
    return CapabilityProvisioningResult(
        complete=complete,
        skipped=False,
        statuses=verified_statuses,
        results=tuple(verified_results),
    )


def visual_install_guidance() -> str:
    return (
        "Install visual evidence support with: pip install 'uidetox[visual]' "
        "(or 'uidetox[capture]' for browser screenshots)."
    )


def chromium_install_guidance() -> str:
    return "Install Chromium with: python -m playwright install chromium"


def capture_install_guidance() -> str:
    return (
        "Install capture support with: pip install 'uidetox[capture]'\n"
        f"{chromium_install_guidance()}"
    )
