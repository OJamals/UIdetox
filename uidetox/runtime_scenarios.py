"""Immutable contracts for bounded browser scenario observation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

_MAX_ACTION_TIMEOUT_MS = 30_000
_MAX_DOM_SCAN = 50_000
_MAX_DOM_CANDIDATES = 10_000
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
    values = [urls] if isinstance(urls, str) else list(urls)
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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeViewport":
        return cls(
            name=str(value["name"]),
            width=int(value["width"]),
            height=int(value["height"]),
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
    value: str = ""
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
        if self.state:
            _safe_identifier(self.state, "action state")
        if self.env and not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.env):
            raise ValueError("Runtime action env must name an environment variable.")
        secret_selector = re.search(
            r"(?:password|token|secret|credential)",
            self.selector,
            flags=re.IGNORECASE,
        )
        if self.kind == "fill" and secret_selector and self.value:
            raise ValueError(
                "Runtime secret fills require an environment variable reference."
            )
        if self.value and self.env:
            raise ValueError("Runtime fill accepts value or env, not both.")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeScenarioAction":
        allowed = {
            "kind",
            "selector",
            "value",
            "env",
            "key",
            "state",
            "timeout_ms",
        }
        _reject_unknown(value, allowed, "action")
        return cls(
            kind=str(value.get("kind", "")),
            selector=str(value.get("selector", "")),
            value=str(value.get("value", "")),
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
        value = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Runtime scenario file is unreadable: {scenario_path}") from exc
    if not isinstance(value, list):
        raise ValueError("Runtime scenario file must contain a JSON array.")
    scenarios = tuple(
        RuntimeScenario.from_dict(dict(item)) for item in value if isinstance(item, dict)
    )
    if len(scenarios) != len(value) or not scenarios:
        raise ValueError("Runtime scenario file must contain scenario objects.")
    if len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise ValueError("Runtime scenario names must be unique.")
    return scenarios
