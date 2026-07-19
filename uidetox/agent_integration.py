"""Structured, non-destructive installation of bundled UIdetox agent guidance."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Agent(str, Enum):
    CLAUDE = "claude"
    CURSOR = "cursor"
    GEMINI = "gemini"
    CODEX = "codex"
    WINDSURF = "windsurf"
    COPILOT = "copilot"


SUPPORTED_AGENT_NAMES = tuple(agent.value for agent in Agent)


class InstallOutcome(str, Enum):
    VERIFIED = "verified"
    ERROR = "error"


class ProvisioningStatus(str, Enum):
    COMPLETE = "complete"
    SKIPPED = "skipped"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class AgentIntegrationEnvironment:
    """Injectable filesystem and interaction boundary for agent setup."""

    project_root: Path
    home: Path
    data_root: Path
    interactive: bool
    input_fn: Callable[[str], str]
    output_fn: Callable[[str], None]
    which: Callable[[str], str | None]

    @classmethod
    def from_system(
        cls,
        *,
        data_root: Path | None = None,
        interactive: bool | None = None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> AgentIntegrationEnvironment:
        if interactive is None:
            interactive = bool(sys.stdin.isatty() and sys.stdout.isatty())
        return cls(
            project_root=Path.cwd(),
            home=Path.home(),
            data_root=data_root or default_data_dir(),
            interactive=interactive,
            input_fn=input_fn,
            output_fn=output_fn,
            which=shutil.which,
        )


@dataclass(frozen=True)
class AgentCandidate:
    agent: Agent
    reasons: tuple[str, ...]
    installed: bool


@dataclass(frozen=True)
class AgentInstallResult:
    agent: Agent | None
    requested_agent: str
    outcome: InstallOutcome
    verified: bool
    changed: bool
    destinations: tuple[Path, ...]
    messages: tuple[str, ...] = ()
    guide: str | None = None
    error_code: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.outcome is InstallOutcome.VERIFIED and self.verified


@dataclass(frozen=True)
class AgentProvisioningResult:
    status: ProvisioningStatus
    candidates: tuple[AgentCandidate, ...]
    results: tuple[AgentInstallResult, ...]

    @property
    def complete(self) -> bool:
        return self.status in {
            ProvisioningStatus.COMPLETE,
            ProvisioningStatus.SKIPPED,
        }

    @property
    def skipped(self) -> bool:
        return self.status is ProvisioningStatus.SKIPPED


@dataclass(frozen=True)
class _AgentSpec:
    agent: Agent
    display_name: str
    skill_root: tuple[str, ...]
    detection_markers: tuple[tuple[str, ...], ...]
    executable: str | None
    global_install: bool = False
    notes: tuple[str, ...] = ()


_CURSOR_RULE = """---
description: UIdetox Anti-Slop Guidelines
globs: "*.tsx, *.jsx, *.ts, *.js, *.css, *.html, *.vue, *.svelte"
---
Before generating or reviewing frontend code, use the UIdetox skill at
`.cursor/skills/uidetox/SKILL.md`. Follow its bundled `AGENTS.md` workflow. Preserve
project-owned root instructions and never replace unrelated skills or commands.
"""

_SPECS = {
    Agent.CLAUDE: _AgentSpec(
        agent=Agent.CLAUDE,
        display_name="Claude",
        skill_root=(".claude", "skills", "uidetox"),
        detection_markers=((".claude",),),
        executable="claude",
        notes=(
            "Claude Code will auto-detect the skill from .claude/skills/.",
            "Paste the agent prompt from the README to start the loop.",
        ),
    ),
    Agent.CURSOR: _AgentSpec(
        agent=Agent.CURSOR,
        display_name="Cursor",
        skill_root=(".cursor", "skills", "uidetox"),
        detection_markers=((".cursor",),),
        executable="cursor",
        notes=(
            "Enable Agent Skills in Cursor Settings → Beta → Agent Skills.",
            "The .cursor/rules/uidetox.mdc will auto-activate on frontend files.",
        ),
    ),
    Agent.GEMINI: _AgentSpec(
        agent=Agent.GEMINI,
        display_name="Gemini",
        skill_root=(".gemini", "skills", "uidetox"),
        detection_markers=((".gemini",),),
        executable="gemini",
        notes=("Gemini will discover UIdetox from .gemini/skills/.",),
    ),
    Agent.CODEX: _AgentSpec(
        agent=Agent.CODEX,
        display_name="Codex",
        skill_root=(".codex", "skills", "uidetox"),
        detection_markers=((".codex",),),
        executable="codex",
        global_install=True,
    ),
    Agent.WINDSURF: _AgentSpec(
        agent=Agent.WINDSURF,
        display_name="Windsurf",
        skill_root=(".windsurf", "skills", "uidetox"),
        detection_markers=((".windsurf",),),
        executable="windsurf",
        notes=("Windsurf will discover UIdetox from .windsurf/skills/.",),
    ),
    Agent.COPILOT: _AgentSpec(
        agent=Agent.COPILOT,
        display_name="Copilot",
        skill_root=(".github", "skills", "uidetox"),
        detection_markers=(
            (".github", "skills"),
            (".github", "copilot-instructions.md"),
        ),
        executable=None,
        notes=("Copilot will discover UIdetox from .github/skills/.",),
    ),
}

_REQUIRED_ASSETS = (
    (("SKILL.md",), "file"),
    (("commands",), "directory"),
    (("reference",), "directory"),
)


def default_data_dir() -> Path:
    """Locate bundled data, retaining editable-install development support."""

    package_data = Path(__file__).resolve().parent / "data"
    if package_data.exists():
        return package_data
    return Path(__file__).resolve().parent.parent


class _InstallRecorder:
    def __init__(self) -> None:
        self.changed = False
        self.messages: list[str] = []

    def record(self, message: str, changed: bool) -> None:
        self.changed = self.changed or changed
        self.messages.append(message)


def _same_file(source: Path, destination: Path) -> bool:
    try:
        return destination.is_file() and source.read_bytes() == destination.read_bytes()
    except OSError:
        return False


def _copy_file(
    source: Path,
    destination: Path,
    recorder: _InstallRecorder,
    *,
    label: str | None = None,
) -> None:
    changed = not _same_file(source, destination)
    if changed:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    recorder.record(f"  ✓ {label or destination.name} → {destination}", changed)


def _merge_directory(
    source: Path,
    destination: Path,
    recorder: _InstallRecorder,
    *,
    label: str | None = None,
) -> None:
    changed = False
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        target = destination / item.relative_to(source)
        item_changed = not _same_file(item, target)
        if item_changed:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
        changed = changed or item_changed
    recorder.record(f"  ✓ {label or source.name}/ → {destination}/", changed)


def _write_text(
    destination: Path,
    content: str,
    recorder: _InstallRecorder,
    *,
    label: str,
) -> None:
    current = None
    try:
        current = destination.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        pass
    changed = current != content
    if changed:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    recorder.record(f"  ✓ {label} → {destination}", changed)


def _skill_destination(
    spec: _AgentSpec,
    environment: AgentIntegrationEnvironment,
) -> Path:
    root = environment.home if spec.global_install else environment.project_root
    return root.joinpath(*spec.skill_root)


def _destination_is_within_root(destination: Path, root: Path) -> bool:
    try:
        destination.resolve().relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _copy_project_skill(
    data_root: Path,
    destination: Path,
    recorder: _InstallRecorder,
) -> None:
    _copy_file(data_root / "SKILL.md", destination / "SKILL.md", recorder)
    agents_file = data_root / "AGENTS.md"
    if agents_file.is_file():
        _copy_file(agents_file, destination / "AGENTS.md", recorder)
    _merge_directory(
        data_root / "reference",
        destination / "reference",
        recorder,
    )
    _merge_directory(
        data_root / "commands",
        destination / "commands",
        recorder,
    )


class _ProviderAdapter:
    def __init__(self, spec: _AgentSpec) -> None:
        self.spec = spec

    def destinations(
        self,
        environment: AgentIntegrationEnvironment,
    ) -> tuple[Path, ...]:
        return (_skill_destination(self.spec, environment),)

    def install(
        self,
        environment: AgentIntegrationEnvironment,
        recorder: _InstallRecorder,
    ) -> None:
        _copy_project_skill(
            environment.data_root,
            self.destinations(environment)[0],
            recorder,
        )

    def verify(self, environment: AgentIntegrationEnvironment) -> bool:
        destination = self.destinations(environment)[0]
        return _tree_matches(environment.data_root, destination)


class _CursorAdapter(_ProviderAdapter):
    def destinations(
        self,
        environment: AgentIntegrationEnvironment,
    ) -> tuple[Path, ...]:
        skill = _skill_destination(self.spec, environment)
        rule = environment.project_root / ".cursor" / "rules" / "uidetox.mdc"
        return skill, rule

    def install(
        self,
        environment: AgentIntegrationEnvironment,
        recorder: _InstallRecorder,
    ) -> None:
        skill, rule = self.destinations(environment)
        _copy_project_skill(environment.data_root, skill, recorder)
        _write_text(rule, _CURSOR_RULE, recorder, label="uidetox.mdc")

    def verify(self, environment: AgentIntegrationEnvironment) -> bool:
        skill, rule = self.destinations(environment)
        return (
            _tree_matches(environment.data_root, skill)
            and rule.is_file()
            and rule.read_text(encoding="utf-8") == _CURSOR_RULE
        )


class _CodexAdapter(_ProviderAdapter):
    def destinations(
        self,
        environment: AgentIntegrationEnvironment,
    ) -> tuple[Path, ...]:
        skill = _skill_destination(self.spec, environment)
        prompts = environment.home / ".codex" / "prompts" / "uidetox"
        return skill, prompts

    def install(
        self,
        environment: AgentIntegrationEnvironment,
        recorder: _InstallRecorder,
    ) -> None:
        skill, prompts = self.destinations(environment)
        _copy_project_skill(environment.data_root, skill, recorder)
        _merge_directory(
            environment.data_root / "commands",
            prompts,
            recorder,
            label="commands (as prompts)",
        )

    def verify(self, environment: AgentIntegrationEnvironment) -> bool:
        skill, prompts = self.destinations(environment)
        return _tree_matches(
            environment.data_root,
            skill,
        ) and _directory_matches(environment.data_root / "commands", prompts)


_ADAPTERS = {
    agent: (
        _CursorAdapter(spec)
        if agent is Agent.CURSOR
        else _CodexAdapter(spec)
        if agent is Agent.CODEX
        else _ProviderAdapter(spec)
    )
    for agent, spec in _SPECS.items()
}


def _missing_assets(data_root: Path) -> tuple[Path, ...]:
    missing: list[Path] = []
    for parts, expected_kind in _REQUIRED_ASSETS:
        path = data_root.joinpath(*parts)
        present = path.is_file() if expected_kind == "file" else path.is_dir()
        if not present:
            missing.append(path)
    return tuple(missing)


def _directory_matches(source: Path, destination: Path) -> bool:
    return all(
        not item.is_file() or _same_file(item, destination / item.relative_to(source))
        for item in source.rglob("*")
    )


def _tree_matches(data_root: Path, destination: Path) -> bool:
    agents_file = data_root / "AGENTS.md"
    return (
        _same_file(data_root / "SKILL.md", destination / "SKILL.md")
        and (
            not agents_file.exists()
            or _same_file(agents_file, destination / "AGENTS.md")
        )
        and _directory_matches(data_root / "commands", destination / "commands")
        and _directory_matches(data_root / "reference", destination / "reference")
    )


def install_agent(
    agent: Agent | str,
    environment: AgentIntegrationEnvironment | None = None,
) -> AgentInstallResult:
    """Install one supported provider and verify every required destination."""

    environment = environment or AgentIntegrationEnvironment.from_system()
    requested = agent.value if isinstance(agent, Agent) else str(agent)
    try:
        resolved_agent = agent if isinstance(agent, Agent) else Agent(agent)
    except ValueError:
        return AgentInstallResult(
            agent=None,
            requested_agent=requested,
            outcome=InstallOutcome.ERROR,
            verified=False,
            changed=False,
            destinations=(),
            error_code="unsupported_agent",
            error=(
                f"Unknown agent '{requested}'. Valid options: "
                f"{', '.join(sorted(SUPPORTED_AGENT_NAMES))}"
            ),
        )

    missing = _missing_assets(environment.data_root)
    if missing:
        return AgentInstallResult(
            agent=resolved_agent,
            requested_agent=requested,
            outcome=InstallOutcome.ERROR,
            verified=False,
            changed=False,
            destinations=(),
            error_code="missing_assets",
            error="Missing bundled assets: " + ", ".join(str(path) for path in missing),
        )

    spec = _SPECS[resolved_agent]
    adapter = _ADAPTERS[resolved_agent]
    destinations = adapter.destinations(environment)
    allowed_root = environment.home if spec.global_install else environment.project_root
    unsafe_destination = next(
        (
            destination
            for destination in destinations
            if not _destination_is_within_root(destination, allowed_root)
        ),
        None,
    )
    if unsafe_destination is not None:
        return AgentInstallResult(
            agent=resolved_agent,
            requested_agent=requested,
            outcome=InstallOutcome.ERROR,
            verified=False,
            changed=False,
            destinations=destinations,
            error_code="unsafe_destination",
            error=(
                f"Refusing to write outside the allowed root {allowed_root}: "
                f"{unsafe_destination}"
            ),
        )

    recorder = _InstallRecorder()
    try:
        adapter.install(environment, recorder)
        verified = adapter.verify(environment)
    except (OSError, UnicodeError) as error:
        return AgentInstallResult(
            agent=resolved_agent,
            requested_agent=requested,
            outcome=InstallOutcome.ERROR,
            verified=False,
            changed=recorder.changed,
            destinations=destinations,
            messages=tuple(recorder.messages),
            error_code="write_failed",
            error=str(error),
        )
    if not verified:
        return AgentInstallResult(
            agent=resolved_agent,
            requested_agent=requested,
            outcome=InstallOutcome.ERROR,
            verified=False,
            changed=recorder.changed,
            destinations=destinations,
            messages=tuple(recorder.messages),
            error_code="verification_failed",
            error="Installed files did not match the bundled guidance.",
        )

    guide_path = environment.data_root / "docs" / f"{resolved_agent.value.upper()}.md"
    guide = None
    if guide_path.is_file():
        try:
            guide = guide_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            guide = None
    messages = (*recorder.messages, *(f"  {note}" for note in spec.notes))
    return AgentInstallResult(
        agent=resolved_agent,
        requested_agent=requested,
        outcome=InstallOutcome.VERIFIED,
        verified=True,
        changed=recorder.changed,
        destinations=destinations,
        messages=messages,
        guide=guide,
    )


def detect_agent_candidates(
    environment: AgentIntegrationEnvironment | None = None,
) -> tuple[AgentCandidate, ...]:
    """Return recognizable providers without writing to project or home."""

    environment = environment or AgentIntegrationEnvironment.from_system()
    candidates: list[AgentCandidate] = []
    for agent in Agent:
        spec = _SPECS[agent]
        reasons: list[str] = []
        marker_root = (
            environment.home if spec.global_install else environment.project_root
        )
        for marker in spec.detection_markers:
            marker_path = marker_root.joinpath(*marker)
            if marker_path.exists():
                reasons.append(f"found {marker_path}")
                break
        if spec.executable and environment.which(spec.executable):
            reasons.append(f"found `{spec.executable}` executable")
        adapter = _ADAPTERS[agent]
        installed = False
        try:
            installed = adapter.verify(environment)
        except (OSError, UnicodeError):
            installed = False
        if installed:
            reasons.append("UIdetox guidance already installed")
        if reasons:
            candidates.append(
                AgentCandidate(
                    agent=agent,
                    reasons=tuple(reasons),
                    installed=installed,
                )
            )
    return tuple(candidates)


def _parse_selection(
    value: str,
    defaults: tuple[Agent, ...],
) -> tuple[Agent, ...] | None:
    normalized = value.strip().lower()
    if normalized in {"", "y", "yes", "all"}:
        return defaults
    requested = {item.strip() for item in normalized.split(",") if item.strip()}
    if not requested or not requested <= set(SUPPORTED_AGENT_NAMES):
        return None
    return tuple(agent for agent in Agent if agent.value in requested)


def provision_agent_integration(
    environment: AgentIntegrationEnvironment | None = None,
) -> AgentProvisioningResult:
    """Detect, confirm, install, and verify selected provider integrations."""

    environment = environment or AgentIntegrationEnvironment.from_system()
    candidates = detect_agent_candidates(environment)
    if not environment.interactive:
        return AgentProvisioningResult(
            status=ProvisioningStatus.INCOMPLETE,
            candidates=candidates,
            results=(),
        )

    try:
        if candidates:
            defaults = tuple(candidate.agent for candidate in candidates)
            names = ", ".join(agent.value for agent in defaults)
            environment.output_fn(f"Detected agent candidates: {names}")
            answer = environment.input_fn(
                "Install UIdetox guidance for all detected agents? [Y/n/custom] "
            )
            if answer.strip().lower() in {"n", "no", "skip"}:
                return AgentProvisioningResult(
                    status=ProvisioningStatus.SKIPPED,
                    candidates=candidates,
                    results=(),
                )
            if answer.strip().lower() == "custom":
                answer = environment.input_fn(
                    f"Agents ({', '.join(SUPPORTED_AGENT_NAMES)}; comma-separated): "
                )
            selected = _parse_selection(answer, defaults)
        else:
            answer = environment.input_fn(
                "No agent detected. Choose one "
                f"({', '.join(SUPPORTED_AGENT_NAMES)}) or `skip`: "
            )
            if answer.strip().lower() in {"n", "no", "skip", "none"}:
                return AgentProvisioningResult(
                    status=ProvisioningStatus.SKIPPED,
                    candidates=(),
                    results=(),
                )
            selected = _parse_selection(answer, ())
    except (EOFError, KeyboardInterrupt, StopIteration):
        selected = None

    if not selected:
        environment.output_fn("No supported agent was selected; nothing was written.")
        return AgentProvisioningResult(
            status=ProvisioningStatus.INCOMPLETE,
            candidates=candidates,
            results=(),
        )

    results = tuple(install_agent(agent, environment) for agent in selected)
    for result in results:
        for message in result.messages:
            environment.output_fn(message)
        if result.success:
            environment.output_fn(f"{result.requested_agent}: verified")
            if result.guide is not None:
                environment.output_fn(result.guide)
        else:
            environment.output_fn(
                f"{result.requested_agent}: {result.error_code} — {result.error}"
            )
    status = (
        ProvisioningStatus.COMPLETE
        if all(result.success for result in results)
        else ProvisioningStatus.INCOMPLETE
    )
    return AgentProvisioningResult(
        status=status,
        candidates=candidates,
        results=results,
    )
