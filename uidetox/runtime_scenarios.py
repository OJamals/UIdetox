"""Immutable contracts for bounded browser scenario observation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

from uidetox.fileset import ProjectFileSet
from uidetox.prompt_safety import (
    SENSITIVE_EVIDENCE_REDACTION,
    sanitize_untrusted_data,
)

_MAX_ACTION_TIMEOUT_MS = 30_000
_MAX_DOM_SCAN = 50_000
_MAX_DOM_CANDIDATES = 10_000
_MAX_RESPONSIVE_BOUNDARIES = 8
_MAX_RESPONSIVE_SOURCE_BYTES = 1_000_000
_URL_IN_TEXT_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?P<key>authorization|api[_-]?key|access[_-]?token|password|passwd|"
    r"secret|token)\b(?P<separator>\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_SUPPORTED_ACTIONS = frozenset(
    {
        "click",
        "fill",
        "key",
        "wait-for-selector",
        "wait-for-state",
        "capture",
    }
)
_SELECTOR_STATES = frozenset({"attached", "detached", "visible", "hidden"})
_LOAD_STATES = frozenset({"load", "domcontentloaded", "networkidle"})
_ACTION_FIELDS = {
    "click": {"kind", "selector", "timeout_ms"},
    "fill": {"kind", "selector", "env", "timeout_ms"},
    "key": {"kind", "selector", "key", "timeout_ms"},
    "wait-for-selector": {"kind", "selector", "timeout_ms"},
    "wait-for-state": {"kind", "selector", "state", "timeout_ms"},
    "capture": {"kind", "state"},
}
_RESPONSIVE_BOUNDARY_PATTERN = re.compile(
    r"@(?P<kind>media|container)\b[^{}]{0,500}?"
    r"\(\s*(?:(?:min-|max-)?(?:width|inline-size)\s*:\s*"
    r"|(?:width|inline-size)\s*(?:<=|>=|<|>)\s*)"
    r"(?P<width>\d+)px\s*\)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class RuntimeObservationLimits:
    scenario_file_bytes: int = 1_000_000
    scenarios: int = 32
    actions_per_scenario: int = 64
    actions_total: int = 512
    viewports: int = 20
    capture_matrix: int = 256
    timeout_ms: int = _MAX_ACTION_TIMEOUT_MS
    settle_ms: int = _MAX_ACTION_TIMEOUT_MS
    work_units: int = 2_048
    time_budget_ms: int = 900_000


RUNTIME_OBSERVATION_LIMITS = RuntimeObservationLimits()
_T = TypeVar("_T")


def bounded_tuple(
    values: Iterable[_T],
    *,
    limit: int,
    label: str,
) -> tuple[_T, ...]:
    """Collect at most ``limit + 1`` items and reject without exhausting input."""

    collected = tuple(islice(values, limit + 1))
    if len(collected) > limit:
        raise ValueError(f"{label} exceeds {limit}.")
    return collected


def sanitize_runtime_url(value: str) -> str:
    """Remove URL credentials and request-specific query data from diagnostics."""

    parsed = urlsplit(str(value))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return str(sanitize_untrusted_data(str(value)))
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def sanitize_runtime_text(value: object) -> str:
    """Redact secrets and scrub embedded URLs before runtime evidence exists."""

    text = _URL_IN_TEXT_PATTERN.sub(
        lambda match: sanitize_runtime_url(match.group(0)),
        str(value),
    )
    text = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: (
            f"{match.group('key')}{match.group('separator')}"
            f"{SENSITIVE_EVIDENCE_REDACTION}"
        ),
        text,
    )
    text = _BEARER_PATTERN.sub(
        f"Bearer {SENSITIVE_EVIDENCE_REDACTION}",
        text,
    )
    return str(sanitize_untrusted_data(text))


def _reject_unknown(
    value: dict[str, Any],
    allowed: set[str],
    label: str,
) -> None:
    if unknown := set(value) - allowed:
        raise ValueError(f"Unknown runtime {label} fields: {', '.join(sorted(unknown))}")


def _safe_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError(f"Runtime {label} must be a safe identifier.")


def normalize_runtime_urls(urls: str | Iterable[str]) -> tuple[str, ...]:
    values = (
        (urls,)
        if isinstance(urls, str)
        else bounded_tuple(
            urls,
            limit=RUNTIME_OBSERVATION_LIMITS.scenarios,
            label="Runtime URL count",
        )
    )
    normalized: list[str] = []
    for value in values:
        url = str(value).strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Runtime URL must be absolute HTTP(S): {url}")
        if url not in normalized:
            normalized.append(url)
    if not normalized:
        raise ValueError("At least one runtime URL is required.")
    return tuple(normalized)


@dataclass(frozen=True)
class RuntimeViewport:
    name: str
    width: int
    height: int
    kind: str = "registry"
    boundary_px: int | None = None
    relation: str = ""
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _safe_identifier(self.name, "viewport name")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Runtime viewport dimensions must be positive.")
        if self.relation not in {"", "below", "above"}:
            raise ValueError("Runtime viewport relation must be below or above.")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeViewport":
        return cls(
            name=str(value["name"]),
            width=int(value["width"]),
            height=int(value["height"]),
            kind=str(value.get("kind", "registry")),
            boundary_px=(
                int(value["boundary_px"])
                if value.get("boundary_px") is not None
                else None
            ),
            relation=str(value.get("relation", "")),
            sources=tuple(str(item) for item in value.get("sources", [])),
        )


VIEWPORT_REGISTRY = MappingProxyType(
    {
        "mobile": RuntimeViewport("mobile", 390, 844),
        "tablet": RuntimeViewport("tablet", 768, 1024),
        "desktop": RuntimeViewport("desktop", 1440, 900),
        "wide": RuntimeViewport("wide", 1920, 1080),
    }
)
DEFAULT_VIEWPORTS = tuple(
    VIEWPORT_REGISTRY[name] for name in ("mobile", "tablet", "desktop")
)


@dataclass(frozen=True)
class RuntimeResponsiveBoundary:
    width: int
    kinds: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeViewportDiscovery:
    viewports: tuple[RuntimeViewport, ...]
    boundaries: tuple[RuntimeResponsiveBoundary, ...] = ()
    total_boundaries: int = 0
    truncated: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeViewportDiscovery":
        return cls(
            viewports=tuple(
                RuntimeViewport.from_dict(dict(item))
                for item in value.get("viewports", [])
                if isinstance(item, dict)
            ),
            boundaries=tuple(
                RuntimeResponsiveBoundary(
                    width=int(item["width"]),
                    kinds=tuple(str(kind) for kind in item.get("kinds", [])),
                    sources=tuple(str(source) for source in item.get("sources", [])),
                )
                for item in value.get("boundaries", [])
                if isinstance(item, dict)
            ),
            total_boundaries=int(value.get("total_boundaries", 0)),
            truncated=bool(value.get("truncated", False)),
        )


def discover_runtime_viewports(
    root: str | Path,
    *,
    base_viewports: Iterable[RuntimeViewport] = DEFAULT_VIEWPORTS,
    max_boundaries: int = _MAX_RESPONSIVE_BOUNDARIES,
) -> RuntimeViewportDiscovery:
    """Supplement the canonical registry with source-derived boundary probes."""

    if not 1 <= max_boundaries <= _MAX_RESPONSIVE_BOUNDARIES:
        raise ValueError(
            f"Runtime responsive boundary budget must be 1-{_MAX_RESPONSIVE_BOUNDARIES}."
        )
    base = bounded_tuple(
        base_viewports,
        limit=RUNTIME_OBSERVATION_LIMITS.viewports,
        label="Runtime viewport count",
    )
    if not base:
        raise ValueError("At least one runtime viewport is required.")
    root_path = Path(root).expanduser().resolve()
    discovered: dict[int, dict[str, set[str]]] = {}
    for path in ProjectFileSet(root_path).discover():
        try:
            if path.stat().st_size > _MAX_RESPONSIVE_SOURCE_BYTES:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(root_path).as_posix()
        for match in _RESPONSIVE_BOUNDARY_PATTERN.finditer(content):
            width = int(match.group("width"))
            if not 240 <= width <= 2_560:
                continue
            evidence = discovered.setdefault(
                width,
                {"kinds": set(), "sources": set()},
            )
            evidence["kinds"].add(match.group("kind").lower())
            evidence["sources"].add(relative)

    widths = sorted(discovered)
    if len(widths) > max_boundaries:
        selected_indexes = (
            {len(widths) // 2}
            if max_boundaries == 1
            else {
                round(index * (len(widths) - 1) / (max_boundaries - 1))
                for index in range(max_boundaries)
            }
        )
        selected_widths = [widths[index] for index in sorted(selected_indexes)]
    else:
        selected_widths = widths
    boundaries = tuple(
        RuntimeResponsiveBoundary(
            width=width,
            kinds=tuple(sorted(discovered[width]["kinds"])),
            sources=tuple(sorted(discovered[width]["sources"])),
        )
        for width in selected_widths
    )
    viewports = list(base)
    occupied_widths = {viewport.width for viewport in viewports}
    for boundary in boundaries:
        probe_kind = "-".join(boundary.kinds)
        for relation, width in (
            ("below", boundary.width - 1),
            ("above", boundary.width + 1),
        ):
            if width < 240 or width > 2_560 or width in occupied_widths:
                continue
            occupied_widths.add(width)
            viewports.append(
                RuntimeViewport(
                    name=f"{probe_kind}-{boundary.width}-{relation}",
                    width=width,
                    height=VIEWPORT_REGISTRY["desktop"].height,
                    kind="boundary",
                    boundary_px=boundary.width,
                    relation=relation,
                    sources=boundary.sources,
                )
            )
    return RuntimeViewportDiscovery(
        viewports=tuple(viewports),
        boundaries=boundaries,
        total_boundaries=len(widths),
        truncated=len(widths) > len(boundaries),
    )


@dataclass(frozen=True)
class RuntimeDomBudget:
    scan: int = 10_000
    candidates: int = 3_000

    def __post_init__(self) -> None:
        if not 1 <= self.scan <= _MAX_DOM_SCAN:
            raise ValueError(f"Runtime DOM scan budget must be 1-{_MAX_DOM_SCAN}.")
        if not 1 <= self.candidates <= _MAX_DOM_CANDIDATES:
            raise ValueError(
                f"Runtime DOM candidate budget must be 1-{_MAX_DOM_CANDIDATES}."
            )
        if self.candidates > self.scan:
            raise ValueError("Runtime DOM candidate budget cannot exceed scan budget.")


@dataclass(frozen=True)
class RuntimeCoverage:
    total: int
    candidates: int
    eligible: int
    emitted: int
    budget: int
    truncated: bool = False

    @classmethod
    def empty(cls, budget: int) -> "RuntimeCoverage":
        return cls(0, 0, 0, 0, budget)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeCoverage":
        return cls(
            total=int(value.get("total", 0)),
            candidates=int(value.get("candidates", 0)),
            eligible=int(value.get("eligible", 0)),
            emitted=int(value.get("emitted", 0)),
            budget=int(value.get("budget", 0)),
            truncated=bool(value.get("truncated", False)),
        )


@dataclass(frozen=True)
class RuntimeDiagnostic:
    kind: str
    code: str
    message: str
    severity: str
    scenario: str
    state: str
    url: str
    viewport: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", sanitize_runtime_text(self.message))
        object.__setattr__(self, "url", sanitize_runtime_url(self.url))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeDiagnostic":
        return cls(
            kind=str(value.get("kind", "browser")),
            code=str(value.get("code", "browser-error")),
            message=str(value.get("message", "")),
            severity=str(value.get("severity", "error")),
            scenario=str(value.get("scenario", "default")),
            state=str(value.get("state", "initial")),
            url=str(value.get("url", "")),
            viewport=str(value.get("viewport", "")),
            source=str(value.get("source", "")),
        )


@dataclass(frozen=True)
class RuntimeReadiness:
    status: str
    strategy: str
    duration_ms: int
    detail: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeReadiness":
        return cls(
            status=str(value.get("status", "degraded")),
            strategy=str(value.get("strategy", "legacy")),
            duration_ms=int(value.get("duration_ms", 0)),
            detail=str(value.get("detail", "")),
        )


@dataclass(frozen=True)
class RuntimeReadinessPolicy:
    selector: str = ""
    app_hook: str = ""
    mutation_idle_ms: int = 0
    request_idle_ms: int = 3_000
    settle_ms: int = 250

    def __post_init__(self) -> None:
        if self.selector and self.app_hook:
            raise ValueError("Runtime readiness accepts one explicit readiness signal.")
        for name, value in (
            ("mutation_idle_ms", self.mutation_idle_ms),
            ("request_idle_ms", self.request_idle_ms),
            ("settle_ms", self.settle_ms),
        ):
            if not 0 <= value <= _MAX_ACTION_TIMEOUT_MS:
                raise ValueError(
                    f"Runtime readiness {name} must be 0-{_MAX_ACTION_TIMEOUT_MS}."
                )
        if self.app_hook and not re.fullmatch(r"[A-Za-z_$][\w$.-]*", self.app_hook):
            raise ValueError("Runtime app hook must be a dotted identifier.")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeReadinessPolicy":
        allowed = {
            "selector",
            "app_hook",
            "mutation_idle_ms",
            "request_idle_ms",
            "settle_ms",
        }
        _reject_unknown(value, allowed, "readiness")
        return cls(
            selector=str(value.get("selector", "")),
            app_hook=str(value.get("app_hook", "")),
            mutation_idle_ms=int(value.get("mutation_idle_ms", 0)),
            request_idle_ms=int(value.get("request_idle_ms", 3_000)),
            settle_ms=int(value.get("settle_ms", 250)),
        )


@dataclass(frozen=True)
class RuntimeScenarioAction:
    kind: str
    selector: str = ""
    env: str = ""
    key: str = ""
    state: str = ""
    timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if self.kind not in _SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported runtime action: {self.kind}")
        if not 1 <= self.timeout_ms <= _MAX_ACTION_TIMEOUT_MS:
            raise ValueError(
                f"Runtime action timeout_ms must be 1-{_MAX_ACTION_TIMEOUT_MS}."
            )
        if self.kind in {"click", "fill", "wait-for-selector"} and not self.selector:
            raise ValueError(f"Runtime {self.kind} action requires selector.")
        if self.kind == "key" and (not self.selector or not self.key):
            raise ValueError("Runtime key action requires selector and key.")
        if self.kind == "wait-for-state" and not self.state:
            raise ValueError("Runtime wait-for-state action requires state.")
        if self.kind == "capture" and not self.state:
            raise ValueError("Runtime capture action requires state.")
        if self.kind == "fill" and not self.env:
            raise ValueError(
                "Runtime fill values require an environment variable reference."
            )
        if self.state:
            _safe_identifier(self.state, "action state")
        if self.env and not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.env):
            raise ValueError("Runtime action env must name an environment variable.")
        if self.kind != "fill" and self.env:
            raise ValueError("Runtime action env is only valid for fill.")
        if self.kind != "key" and self.key:
            raise ValueError("Runtime action key is only valid for key.")
        if self.kind not in {"wait-for-state", "capture"} and self.state:
            raise ValueError(f"Runtime {self.kind} action does not accept state.")
        if self.kind == "capture" and self.selector:
            raise ValueError("Runtime capture action does not accept selector.")
        if self.kind == "wait-for-state":
            allowed_states = _SELECTOR_STATES if self.selector else _LOAD_STATES
            if self.state not in allowed_states:
                domain = ", ".join(sorted(allowed_states))
                raise ValueError(
                    f"Runtime wait-for-state must be one of: {domain}."
                )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeScenarioAction":
        kind = str(value.get("kind", ""))
        if kind not in _SUPPORTED_ACTIONS:
            raise ValueError(f"Unsupported runtime action: {kind}")
        allowed = _ACTION_FIELDS[kind]
        _reject_unknown(value, allowed, "action")
        return cls(
            kind=kind,
            selector=str(value.get("selector", "")),
            env=str(value.get("env", "")),
            key=str(value.get("key", "")),
            state=str(value.get("state", "")),
            timeout_ms=int(value.get("timeout_ms", 5_000)),
        )


@dataclass(frozen=True)
class RuntimeScenario:
    name: str
    url: str
    actions: tuple[RuntimeScenarioAction, ...] = ()
    expected_state: str = "initial"
    viewports: tuple[str, ...] = ()
    readiness: RuntimeReadinessPolicy = field(default_factory=RuntimeReadinessPolicy)

    def __post_init__(self) -> None:
        _safe_identifier(self.name, "scenario name")
        normalize_runtime_urls(self.url)
        _safe_identifier(self.expected_state, "scenario expected_state")
        unknown_viewports = set(self.viewports) - set(VIEWPORT_REGISTRY)
        if unknown_viewports:
            raise ValueError(
                f"Unknown runtime viewports: {', '.join(sorted(unknown_viewports))}"
            )
        states = [
            action.state for action in self.actions if action.kind == "capture"
        ]
        if len(states) != len(set(states)):
            raise ValueError("Runtime scenario capture states must be unique.")
        if len(self.actions) > RUNTIME_OBSERVATION_LIMITS.actions_per_scenario:
            raise ValueError(
                "Runtime scenario action count exceeds "
                f"{RUNTIME_OBSERVATION_LIMITS.actions_per_scenario}."
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeScenario":
        allowed = {
            "name",
            "url",
            "actions",
            "expected_state",
            "viewports",
            "readiness",
        }
        _reject_unknown(value, allowed, "scenario")
        actions = value.get("actions", [])
        readiness = value.get("readiness", {})
        if not isinstance(actions, list) or not isinstance(readiness, dict):
            raise ValueError("Runtime scenario actions/readiness have invalid types.")
        if any(not isinstance(action, dict) for action in actions):
            raise ValueError("Runtime scenario actions must be objects.")
        return cls(
            name=str(value.get("name", "")),
            url=str(value.get("url", "")),
            actions=tuple(
                RuntimeScenarioAction.from_dict(dict(action)) for action in actions
            ),
            expected_state=str(value.get("expected_state", "initial")),
            viewports=tuple(str(item) for item in value.get("viewports", [])),
            readiness=RuntimeReadinessPolicy.from_dict(dict(readiness)),
        )


@dataclass(frozen=True)
class RuntimeCaptureRecord:
    capture_id: str
    scenario: str
    state: str
    url: str
    viewport: RuntimeViewport
    status: str
    readiness: RuntimeReadiness
    coverage: RuntimeCoverage
    started_at: str
    completed_at: str
    diagnostics: tuple[RuntimeDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"completed", "failed"}:
            raise ValueError("Runtime capture status must be completed or failed.")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeCaptureRecord":
        return cls(
            capture_id=str(value.get("capture_id", "")),
            scenario=str(value.get("scenario", "default")),
            state=str(value.get("state", "initial")),
            url=str(value.get("url", "")),
            viewport=RuntimeViewport.from_dict(dict(value["viewport"])),
            status=str(value.get("status", "failed")),
            readiness=RuntimeReadiness.from_dict(dict(value.get("readiness", {}))),
            coverage=RuntimeCoverage.from_dict(dict(value.get("coverage", {}))),
            started_at=str(value.get("started_at", "")),
            completed_at=str(value.get("completed_at", "")),
            diagnostics=tuple(
                RuntimeDiagnostic.from_dict(dict(item))
                for item in value.get("diagnostics", [])
                if isinstance(item, dict)
            ),
        )


def runtime_capture_id(
    scenario: str,
    state: str,
    url: str,
    viewport: RuntimeViewport,
) -> str:
    digest = hashlib.sha1(
        f"{scenario}\0{state}\0{url}\0{viewport.name}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return f"{scenario}:{state}:{viewport.name}:{digest}"


def validate_runtime_observation_plan(
    scenarios: Iterable[RuntimeScenario],
    viewports: Iterable[RuntimeViewport],
    *,
    timeout_ms: int,
    settle_ms: int,
) -> None:
    """Reject an observation plan whose complete execution exceeds one policy."""

    limits = RUNTIME_OBSERVATION_LIMITS
    scenario_list = bounded_tuple(
        scenarios,
        limit=limits.scenarios,
        label="Runtime scenario count",
    )
    viewport_list = bounded_tuple(
        viewports,
        limit=limits.viewports,
        label="Runtime viewport count",
    )
    if not 1 <= timeout_ms <= limits.timeout_ms:
        raise ValueError(f"timeout_ms must be 1-{limits.timeout_ms}.")
    if not 0 <= settle_ms <= limits.settle_ms:
        raise ValueError(f"settle_ms must be 0-{limits.settle_ms}.")
    if not 1 <= len(scenario_list) <= limits.scenarios:
        raise ValueError(f"Runtime scenario count must be 1-{limits.scenarios}.")
    total_actions = sum(len(scenario.actions) for scenario in scenario_list)
    if total_actions > limits.actions_total:
        raise ValueError(
            f"Runtime total action count exceeds {limits.actions_total}."
        )
    if not 1 <= len(viewport_list) <= limits.viewports:
        raise ValueError(f"Runtime viewport count must be 1-{limits.viewports}.")

    matrix_size = 0
    work_units = 0
    time_budget_ms = 0
    available_names = {viewport.name for viewport in viewport_list}
    for scenario in scenario_list:
        requested_viewports = set(scenario.viewports)
        if requested_viewports - available_names:
            raise ValueError(
                "Scenario viewports were not provided: "
                f"{', '.join(sorted(requested_viewports - available_names))}"
            )
        selected_viewports = (
            len(requested_viewports)
            if requested_viewports
            else len(viewport_list)
        )
        capture_count = (
            sum(action.kind == "capture" for action in scenario.actions) or 1
        )
        matrix_size += selected_viewports * capture_count
        work_units += selected_viewports * (
            1 + len(scenario.actions) + capture_count
        )
        action_time = sum(
            action.timeout_ms
            for action in scenario.actions
            if action.kind != "capture"
        )
        time_budget_ms += selected_viewports * (
            timeout_ms
            + action_time
            + scenario.readiness.request_idle_ms
            + scenario.readiness.settle_ms
        )
    if matrix_size > limits.capture_matrix:
        raise ValueError(
            f"Runtime capture matrix exceeds {limits.capture_matrix}."
        )
    if work_units > limits.work_units:
        raise ValueError(
            f"Runtime observation work exceeds {limits.work_units} units."
        )
    if time_budget_ms > limits.time_budget_ms:
        raise ValueError(
            "Runtime observation time budget exceeds "
            f"{limits.time_budget_ms}ms."
        )


def load_runtime_scenarios(
    path: str | Path,
    *,
    root: str | Path,
) -> tuple[RuntimeScenario, ...]:
    scenario_root = Path(root).expanduser().resolve()
    scenario_path = Path(path).expanduser().resolve()
    if not scenario_path.is_relative_to(scenario_root):
        raise ValueError("Runtime scenario file must be inside the allowed project root.")
    try:
        file_size = scenario_path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Runtime scenario file is unreadable: {scenario_path}") from exc
    if file_size > RUNTIME_OBSERVATION_LIMITS.scenario_file_bytes:
        raise ValueError(
            "Runtime scenario file exceeds "
            f"{RUNTIME_OBSERVATION_LIMITS.scenario_file_bytes} bytes."
        )
    try:
        payload = scenario_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Runtime scenario file is unreadable: {scenario_path}") from exc
    if len(payload) > RUNTIME_OBSERVATION_LIMITS.scenario_file_bytes:
        raise ValueError(
            "Runtime scenario file exceeds "
            f"{RUNTIME_OBSERVATION_LIMITS.scenario_file_bytes} bytes."
        )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Runtime scenario file is unreadable: {scenario_path}") from exc
    if not isinstance(value, list):
        raise ValueError("Runtime scenario file must contain a JSON array.")
    if len(value) > RUNTIME_OBSERVATION_LIMITS.scenarios:
        raise ValueError(
            f"Runtime scenario count exceeds {RUNTIME_OBSERVATION_LIMITS.scenarios}."
        )
    if any(not isinstance(item, dict) for item in value) or not value:
        raise ValueError("Runtime scenario file must contain scenario objects.")
    raw_action_counts = []
    for item in value:
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError("Runtime scenario actions/readiness have invalid types.")
        if len(actions) > RUNTIME_OBSERVATION_LIMITS.actions_per_scenario:
            raise ValueError(
                "Runtime scenario action count exceeds "
                f"{RUNTIME_OBSERVATION_LIMITS.actions_per_scenario}."
            )
        raw_action_counts.append(len(actions))
    if sum(raw_action_counts) > RUNTIME_OBSERVATION_LIMITS.actions_total:
        raise ValueError(
            "Runtime total action count exceeds "
            f"{RUNTIME_OBSERVATION_LIMITS.actions_total}."
        )
    scenarios = tuple(
        RuntimeScenario.from_dict(dict(item)) for item in value
    )
    if len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise ValueError("Runtime scenario names must be unique.")
    return scenarios
