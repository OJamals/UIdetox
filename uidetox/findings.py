"""Canonical evidence-bound finding, verification, score, and release lifecycle."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from uidetox.prompt_safety import sanitize_untrusted_data
from uidetox.utils import now_iso

FINDING_SCHEMA_VERSION = 2
_VOLATILE = frozenset("checked_at created_at generated_at source_hash timestamp".split())
_TIERS = {"info": "T1", "warning": "T2", "error": "T3", "critical": "T4"}
_SEVERITY = {tier: severity for severity, tier in _TIERS.items()}
_WEIGHTS = {"info": 3.0, "warning": 10.0, "error": 20.0, "critical": 30.0}
_NON_DEFECT = {"informational", "investigate", "suppressed", "verified_resolved"}
_CANONICAL = frozenset(
    """schema_version fingerprint id code detector_id category severity confidence
    message status provenance evidence evidence_freshness source_anchor runtime_anchor
    contract_anchor suppression_key verifier last_verification display_excerpt legacy
    extensions file tier issue command line column snippet metrics kind normalized_path
    frontend backend detail""".split()
)
class _FrozenMapping(Mapping[str, Any]):
    __slots__ = ("_data",)
    def __init__(self, items: object = ()) -> None:
        self._data = MappingProxyType(dict(items))  # type: ignore[arg-type]
    def __getitem__(self, key: str) -> Any:
        return self._data[key]
    def __iter__(self) -> Iterator[str]:
        return iter(self._data)
    def __len__(self) -> int:
        return len(self._data)
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Mapping) and dict(self.items()) == dict(other.items())
    def __deepcopy__(self, _memo: dict[int, object]) -> _FrozenMapping:
        return self
def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return _FrozenMapping((str(key), _freeze(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value
def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_thaw(item) for item in value]
    return value
def _mapping(value: object) -> dict[str, Any]:
    return _freeze(value) if isinstance(value, Mapping) else _FrozenMapping()  # type: ignore[return-value]
def _safe(value: Mapping[str, Any], matched: object = None) -> dict[str, Any]:
    evidence = matched if isinstance(matched, (str, bytes)) else None
    clean = sanitize_untrusted_data(dict(value), matched_evidence=evidence)
    return dict(clean) if isinstance(clean, Mapping) else {}
def _identity(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _identity(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE
        }
    if isinstance(value, (list, tuple)):
        return [_identity(item) for item in value]
    return round(value, 6) if isinstance(value, float) else value
def _hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
def _fingerprint(finding: Finding) -> str:
    return _hash(
        {
            "detector_id": finding.detector_id,
            "source_anchor": _identity(finding.source_anchor),
            "runtime_anchor": _identity(finding.runtime_anchor),
            "contract_anchor": _identity(finding.contract_anchor),
            "evidence": _identity(finding.evidence),
        }
    )
@dataclass(frozen=True)
class VerificationResult:
    outcome: str
    checked_at: str
    verifier_kind: str
    detail: str = ""
    evidence_hash: str = ""
    def to_dict(self) -> dict[str, str]:
        return {name: str(getattr(self, name)) for name in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls, value: object) -> VerificationResult | None:
        if not isinstance(value, Mapping):
            return None
        return cls(*(str(value.get(name, "")) for name in cls.__dataclass_fields__))
@dataclass(frozen=True)
class Finding(Mapping[str, Any]):
    """Immutable typed finding; compatibility display fields are derived only."""
    detector_id: str
    category: str
    severity: str
    confidence: float
    message: str
    status: str
    provenance: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    evidence_freshness: str = "fresh"
    source_anchor: Mapping[str, Any] = field(default_factory=dict)
    runtime_anchor: Mapping[str, Any] = field(default_factory=dict)
    contract_anchor: Mapping[str, Any] = field(default_factory=dict)
    suppression_key: str = ""
    verifier: Mapping[str, Any] = field(default_factory=dict)
    last_verification: VerificationResult | None = None
    display_excerpt: str = ""
    legacy: Mapping[str, Any] = field(default_factory=dict)
    extensions: Mapping[str, Any] = field(default_factory=dict, repr=False)
    fingerprint: str = field(init=False)
    schema_version: int = FINDING_SCHEMA_VERSION
    def __post_init__(self) -> None:
        for name in (
            "evidence",
            "source_anchor",
            "runtime_anchor",
            "contract_anchor",
            "verifier",
            "legacy",
            "extensions",
        ):
            object.__setattr__(self, name, _mapping(getattr(self, name)))
        object.__setattr__(self, "fingerprint", _fingerprint(self))
    @classmethod
    def create(
        cls,
        *,
        detector_id: str,
        category: str,
        severity: str,
        confidence: float,
        message: str,
        provenance: str,
        **values: Any,
    ) -> Finding:
        verification = values.pop("last_verification", None)
        extensions = values.pop("extensions", {})
        raw = {
            "detector_id": detector_id,
            "category": category,
            "severity": severity,
            "confidence": confidence,
            "message": message,
            "provenance": provenance,
            "status": "pending",
            **values,
        }
        clean = _safe(raw, _mapping(raw.get("evidence")).get("matched_text"))
        return cls._canonical(clean, verification, extensions)
    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Finding:
        raw = _safe(value, value.get("matched_evidence"))
        try:
            version = int(raw.get("schema_version", 0) or 0)
        except (TypeError, ValueError):
            version = 0
        if version < FINDING_SCHEMA_VERSION or "detector_id" not in raw:
            return cls._legacy(raw)
        stored_extensions = raw.get("extensions", {})
        extensions = {
            **(dict(stored_extensions) if isinstance(stored_extensions, Mapping) else {}),
            **{key: item for key, item in raw.items() if key not in _CANONICAL},
        }
        return cls._canonical(
            raw, VerificationResult.from_dict(raw.get("last_verification")), extensions
        )
    @classmethod
    def _canonical(
        cls,
        raw: Mapping[str, Any],
        verification: VerificationResult | None,
        extensions: Mapping[str, Any],
    ) -> Finding:
        confidence = raw.get("confidence", 0.5)
        return cls(
            detector_id=str(raw.get("detector_id", raw.get("code", "unknown"))),
            category=str(raw.get("category", "quality")),
            severity=str(raw.get("severity", "warning")).lower(),
            confidence=max(0.0, min(1.0, float(confidence or 0.5))),
            message=str(raw.get("message", raw.get("issue", "Finding"))),
            status=str(raw.get("status", "pending")),
            provenance=str(raw.get("provenance", "static")),
            evidence=_mapping(raw.get("evidence")),
            evidence_freshness=str(raw.get("evidence_freshness", "fresh")),
            source_anchor=_mapping(raw.get("source_anchor")),
            runtime_anchor=_mapping(raw.get("runtime_anchor")),
            contract_anchor=_mapping(raw.get("contract_anchor")),
            suppression_key=str(raw.get("suppression_key", "")),
            verifier=_mapping(raw.get("verifier")),
            last_verification=verification,
            display_excerpt=str(raw.get("display_excerpt", raw.get("snippet", ""))),
            legacy=_mapping(raw.get("legacy")),
            extensions=_mapping(extensions),
            schema_version=max(FINDING_SCHEMA_VERSION, int(raw.get("schema_version", 0) or 0)),
        )
    @classmethod
    def _legacy(cls, raw: Mapping[str, Any]) -> Finding:
        if "kind" in raw and "normalized_path" in raw:
            kind, path = str(raw.get("kind", "unresolved")), str(
                raw.get("normalized_path", "")
            )
            return cls.create(
                detector_id=f"contract-{kind.replace('_', '-')}",
                category="contract",
                severity="info" if kind in {"unresolved", "backend_only"} else "warning",
                confidence=0.5 if kind == "unresolved" else 0.85,
                message=str(raw.get("detail", "Contract operation needs review.")),
                provenance="contract",
                evidence={
                    "frontend": list(raw.get("frontend", [])),
                    "backend": list(raw.get("backend", [])),
                },
                contract_anchor={"kind": kind, "normalized_path": path},
                suppression_key=f"contract:{kind}:{path}",
                verifier={"kind": "contract", "normalized_path": path},
                status="investigate" if kind in {"unresolved", "backend_only"} else "pending",
                legacy=raw,
            )
        if "code" in raw and ("metrics" in raw or "runtime_anchor" in raw):
            code = str(raw.get("code", "runtime-layout-finding"))
            return cls.create(
                detector_id=code,
                category=str(raw.get("category", "layout")),
                severity=str(raw.get("severity", "warning")),
                confidence=float(raw.get("confidence", 0.9) or 0.9),
                message=str(raw.get("message", "Rendered layout needs review.")),
                provenance="runtime",
                evidence={"metrics": _mapping(raw.get("metrics"))},
                runtime_anchor=_mapping(raw.get("runtime_anchor")),
                suppression_key=code,
                verifier={"kind": "runtime", "detector_id": code},
                legacy=raw,
            )
        detector = str(raw.get("detector_id", raw.get("rule_id", ""))).strip()
        queue_id = str(raw.get("id", "")).strip()
        if not detector:
            identity = "|".join(str(raw.get(key, "")).strip() for key in ("file", "issue", "command"))
            detector = (
                queue_id
                if queue_id and not queue_id.startswith("SCAN-")
                else "manual-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
            )
        anchor = {
            "path": str(raw.get("file", "")),
            "line": int(raw.get("line", 0) or 0),
            "column": int(raw.get("column", 0) or 0),
            **{
                key: int(raw[key])
                for key in ("start", "end")
                if raw.get(key) is not None
            },
        }
        severity = str(raw.get("severity", "")).lower() or _SEVERITY.get(
            str(raw.get("tier", "T2")), "warning"
        )
        return cls.create(
            detector_id=detector,
            category=str(raw.get("category", "quality")),
            severity=severity,
            confidence=float(raw.get("confidence", 0.8) or 0.8),
            message=str(raw.get("message", raw.get("issue", "Finding"))),
            provenance=str(raw.get("provenance", "static")),
            evidence=_mapping(raw.get("evidence")),
            evidence_freshness=str(raw.get("evidence_freshness", "fresh")),
            source_anchor=anchor,
            suppression_key=str(raw.get("suppression_key", detector)),
            verifier=_mapping(raw.get("verifier"))
            or {
                "kind": "static" if anchor["path"] else "manual",
                "detector_id": detector,
            },
            status=str(raw.get("status", "pending")),
            display_excerpt=str(raw.get("display_excerpt", raw.get("snippet", ""))),
            legacy=raw,
            extensions=raw,
        )
    id = property(lambda self: self.fingerprint)
    code = property(lambda self: self.detector_id)
    tier = property(lambda self: _TIERS.get(self.severity, "T2"))
    metrics = property(lambda self: _mapping(self.evidence.get("metrics", self.evidence)))
    kind = property(lambda self: str(self.contract_anchor.get("kind", "")))
    normalized_path = property(
        lambda self: str(self.contract_anchor.get("normalized_path", ""))
    )
    frontend = property(
        lambda self: tuple(str(item) for item in self.evidence.get("frontend", ()))
    )
    backend = property(
        lambda self: tuple(str(item) for item in self.evidence.get("backend", ()))
    )
    detail = property(lambda self: self.message)
    def to_dict(self) -> dict[str, Any]:
        payload = dict(_thaw(self.extensions))  # type: ignore[arg-type]
        fields = """detector_id category severity confidence message status provenance
        evidence evidence_freshness source_anchor runtime_anchor contract_anchor
        suppression_key verifier display_excerpt legacy""".split()
        payload.update({name: _thaw(getattr(self, name)) for name in fields})
        payload.update(
            {
                "schema_version": self.schema_version,
                "fingerprint": self.fingerprint,
                "id": str(self.legacy.get("id", self.id)),
                "code": self.code,
                "last_verification": self.last_verification.to_dict()
                if self.last_verification
                else None,
                "file": str(self.source_anchor.get("path", "")),
                "tier": self.tier,
                "issue": self.message,
                "command": str(self.legacy.get("command", "")),
                "line": int(self.source_anchor.get("line", 0) or 0),
                "column": int(self.source_anchor.get("column", 0) or 0),
                "snippet": self.display_excerpt,
                "metrics": _thaw(self.metrics),
                "kind": self.kind,
                "normalized_path": self.normalized_path,
                "frontend": list(self.frontend),
                "backend": list(self.backend),
                "detail": self.detail,
            }
        )
        return payload
    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]
    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())
    def __len__(self) -> int:
        return len(self.to_dict())
    def with_runtime_anchor(
        self, *, url: str, viewport: str, selector: str, scenario: str = "default"
    ) -> Finding:
        anchor = {
            "url": url,
            "viewport": viewport,
            "selector": selector,
            "scenario": scenario,
        }
        return replace(
            self, runtime_anchor=anchor, verifier={**dict(self.verifier), **anchor}
        )
def coerce_finding(value: Finding | Mapping[str, Any]) -> Finding:
    return value if isinstance(value, Finding) else Finding.from_dict(value)
def score_current_snapshot(
    state: Mapping[str, Any], *, evidence_hashes: Mapping[str, str] | None = None
) -> dict[str, Any]:
    findings = [
        coerce_finding(item)
        for item in state.get("issues", [])
        if isinstance(item, (Finding, Mapping))
    ]
    coverage = _mapping(state.get("current_snapshot")).get("qualified_coverage", 0)
    coverage = (
        max(0.0, min(1.0, float(coverage)))
        if isinstance(coverage, (int, float)) and not isinstance(coverage, bool)
        else 0.0
    )
    slop = round(
        sum(
            _WEIGHTS.get(item.severity, 10) * item.confidence
            for item in findings
            if item.status not in _NON_DEFECT
        ),
        2,
    )
    objective = max(0, min(100, round(100 * coverage - slop)))
    review = _mapping(state.get("subjective"))
    subjective = (
        _structured_review_score(review)
        if structured_review_current(review, evidence_hashes)
        else None
    )
    blended = round(objective * 0.6 + subjective * 0.4) if subjective is not None else objective
    return {
        "objective_score": objective,
        "subjective_score": subjective,
        "blended_score": blended,
        "current_slop": slop,
        "resolved_slop": 0,
        "total_slop": slop,
        "qualified_coverage": coverage,
    }
@dataclass(frozen=True)
class EligibilityBlocker:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _mapping(self.details))
    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": _thaw(self.details)}
@dataclass(frozen=True)
class EligibilityContext:
    target_score: int = 95
    current_branch: str = ""
    session_branch: str = ""
    dirty: bool = False
    verification_fresh: bool = True
    require_session_branch: bool = False
    evidence_hashes: Mapping[str, str] = field(default_factory=dict)
    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_hashes", _mapping(self.evidence_hashes))
@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    score: Mapping[str, Any]
    blockers: tuple[EligibilityBlocker, ...]
    def __post_init__(self) -> None:
        object.__setattr__(self, "score", _mapping(self.score))
    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "score": _thaw(self.score),
            "blockers": [item.to_dict() for item in self.blockers],
        }
def _structured_review_score(review: Mapping[str, Any]) -> int | None:
    dimensions, caps = review.get("dimensions"), {"A": 40, "B": 30, "C": 20, "D": 10}
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(caps):
        return None
    values = list(dimensions.values())
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 <= float(value) <= caps[key]
        for key, value in dimensions.items()
    ):
        return None
    total, score = sum(float(value) for value in values), review.get("score")
    return round(total) if isinstance(score, (int, float)) and not isinstance(score, bool) and score == total else None
def _structured_review_complete(review: Mapping[str, Any]) -> bool:
    lists = ("finding_links", "routes", "states", "viewports")
    hashes = review.get("evidence_hashes")
    return bool(
        _structured_review_score(review) is not None
        and str(review.get("rationale", "")).strip()
        and str(review.get("reviewer", "")).strip()
        and all(
            isinstance(review.get(key), (list, tuple))
            and all(isinstance(item, str) for item in review[key])
            for key in lists
        )
        and isinstance(hashes, Mapping)
        and set(hashes) == {"source", "map", "runtime"}
        and all(str(hashes[key]).strip() for key in hashes)
    )
def structured_review_current(
    review: Mapping[str, Any], evidence_hashes: Mapping[str, str] | None = None
) -> bool:
    return bool(
        _structured_review_complete(review)
        and not review.get("stale")
        and (
            not evidence_hashes
            or _mapping(review.get("evidence_hashes")) == evidence_hashes
        )
    )
def evaluate_eligibility(
    state: Mapping[str, Any], context: EligibilityContext
) -> EligibilityResult:
    blockers: list[EligibilityBlocker] = []
    def add(condition: object, code: str, message: str, **details: Any) -> None:
        if condition:
            blockers.append(EligibilityBlocker(code, message, details))
    pending = sum(
        coerce_finding(item).status not in _NON_DEFECT
        for item in state.get("issues", [])
        if isinstance(item, (Finding, Mapping))
    )
    score = score_current_snapshot(state, evidence_hashes=context.evidence_hashes)
    review = _mapping(state.get("subjective"))
    add(pending, "pending_findings", f"{pending} finding(s) still require verified resolution.", count=pending)
    add(
        score["blended_score"] < context.target_score,
        "target_score",
        f"Current score {score['blended_score']} is below target {context.target_score}.",
        score=score["blended_score"],
        target=context.target_score,
    )
    add(score["qualified_coverage"] < 1, "incomplete_qualification", "Current detector qualification coverage is incomplete.", coverage=score["qualified_coverage"])
    add(not context.verification_fresh, "stale_evidence", "Current source/map/runtime verification evidence is stale.")
    complete = _structured_review_complete(review)
    add(not complete, "missing_structured_review", "Structured A/B/C/D subjective review evidence is required.")
    add(
        complete
        and (
            review.get("stale")
            or (
                context.evidence_hashes
                and _mapping(review.get("evidence_hashes")) != context.evidence_hashes
            )
        ),
        "stale_review",
        "Subjective review hashes do not match current evidence.",
    )
    add(context.dirty, "dirty_tree", "Git worktree must be clean to finalize.")
    add(
        context.require_session_branch
        and context.current_branch != context.session_branch,
        "session_branch_required",
        "Finalization must run from the active UIdetox session branch.",
        current_branch=context.current_branch,
        session_branch=context.session_branch,
    )
    return EligibilityResult(not blockers, score, tuple(blockers))
def verification_result(
    outcome: str, verifier_kind: str, detail: str = "", *, evidence_hash: str = ""
) -> VerificationResult:
    return VerificationResult(outcome, now_iso(), verifier_kind, detail, evidence_hash)
def current_evidence_hashes(root: str | Path | None = None) -> dict[str, str]:
    from uidetox.state import get_project_root
    root_path = Path(root or get_project_root()).resolve()
    map_path = root_path / ".uidetox" / "frontend-map.json"
    try:
        raw, mapped = map_path.read_bytes(), json.loads(map_path.read_text())
        if not isinstance(mapped, Mapping):
            mapped = {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raw, mapped = b"absent", {}
    evidence = mapped.get("evidence", {})
    evidence = evidence if isinstance(evidence, Mapping) else {}
    manifest = evidence.get("source_manifest", {})
    paths = {
        str(path)
        for group in (manifest.get("files", {}), manifest.get("project_files", {}))
        if isinstance(group, Mapping)
        for path in group
    }
    live = {}
    for path in sorted(paths):
        source = Path(path) if Path(path).is_absolute() else root_path / path
        try:
            live[path] = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError:
            live[path] = "missing"
    runtime = {
        "status": evidence.get("runtime_status", "absent"),
        "nodes": [
            node
            for node in mapped.get("nodes", [])
            if str(node.get("kind", "")).startswith("runtime_")
        ],
    }
    return {
        "source": _hash(live or {"status": "absent"}),
        "map": hashlib.sha256(raw).hexdigest(),
        "runtime": _hash(runtime),
    }
def current_verification_fresh(root: str | Path | None = None) -> bool:
    from uidetox.frontend_map import frontend_map_is_fresh, load_frontend_map
    from uidetox.state import get_project_root
    root_path = Path(root or get_project_root()).resolve()
    try:
        frontend_map = load_frontend_map(root_path / ".uidetox" / "frontend-map.json")
        return frontend_map_is_fresh(
            frontend_map, root_path, frontend_map.target
        ) and frontend_map.evidence.get("runtime_status") != "stale"
    except (FileNotFoundError, ValueError, OSError):
        return False
_Verifier = Callable[[Finding, Mapping[str, Any], Path], VerificationResult]
def verify_finding(
    value: Finding | Mapping[str, Any],
    *,
    state: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> VerificationResult:
    finding = coerce_finding(value)
    kind = str(finding.verifier.get("kind", finding.provenance or "manual"))
    handlers: dict[str, _Verifier] = {
        "static": _verify_static,
        "runtime": _verify_runtime,
        "contract": _verify_contract,
        "manual": _verify_manual,
    }
    try:
        handler = handlers[kind]
        return handler(finding, state or {}, Path(root or Path.cwd()).resolve())
    except KeyError:
        return verification_result("stale_evidence", kind, f"Unsupported verifier kind: {kind}")
    except (OSError, ValueError, TypeError) as error:
        return verification_result("stale_evidence", kind, str(error))
def _same_anchor(left: Finding, right: Finding) -> bool:
    keys = ("start", "end") if {"start", "end"} & set(left.source_anchor) else ("line", "column")
    return all(left.source_anchor.get(key) == right.source_anchor.get(key) for key in keys)
def _verify_static(
    finding: Finding, _state: Mapping[str, Any], root: Path
) -> VerificationResult:
    from uidetox.analyzer import analyze_file
    source = Path(str(finding.source_anchor.get("path", "")))
    source = source if source.is_absolute() else root / source
    if not source.exists():
        evidence_hash = _hash({"path": str(source), "status": "missing"})
        return verification_result("absent", "static", "Source no longer exists.", evidence_hash=evidence_hash)
    evidence_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    matches = [item for item in analyze_file(source) if item.detector_id == finding.detector_id]
    if any(_same_anchor(finding, item) for item in matches):
        return verification_result("reproduced", "static", "Detector reproduced at source anchor.", evidence_hash=evidence_hash)
    if matches:
        return verification_result("stale_anchor", "static", "Detector moved to a different source anchor.", evidence_hash=evidence_hash)
    return verification_result("absent", "static", "Detector no longer reproduces.", evidence_hash=evidence_hash)
def _verify_runtime(
    finding: Finding, _state: Mapping[str, Any], root: Path
) -> VerificationResult:
    from uidetox.frontend_map import frontend_map_is_fresh, load_frontend_map
    frontend_map = load_frontend_map(root / ".uidetox" / "frontend-map.json")
    map_hash = current_evidence_hashes(root)["map"]
    if frontend_map.evidence.get("runtime_status") != "current" or not frontend_map_is_fresh(
        frontend_map, root, frontend_map.target
    ):
        return verification_result("stale_evidence", "runtime", "Runtime map is not current.", evidence_hash=map_hash)
    anchor = finding.runtime_anchor
    if any(not str(anchor.get(key, "")).strip() for key in ("url", "viewport", "selector", "scenario")):
        evidence_hash = _hash({"map": map_hash, "anchor": _identity(anchor)})
        return verification_result("stale_evidence", "runtime", "Route/scenario/viewport/selector evidence is incomplete.", evidence_hash=evidence_hash)
    observed = [
        node
        for node in frontend_map.nodes
        if node.metadata.get("runtime_url") == anchor["url"]
        and node.metadata.get("viewport") == anchor["viewport"]
        and node.metadata.get("scenario", "default") == anchor["scenario"]
    ]
    scenario_hash = _hash({"map": map_hash, "anchor": _identity(anchor), "nodes": [
        {"id": node.id, "metadata": _identity(node.metadata)} for node in observed
    ]})
    if not observed:
        return verification_result("stale_evidence", "runtime", "Requested route/viewport/scenario was not observed.", evidence_hash=scenario_hash)
    exact = next((node for node in observed if node.metadata.get("selector") == anchor["selector"]), None)
    if exact is None:
        return verification_result("absent", "runtime", "Selector is absent from the current scenario.", evidence_hash=scenario_hash)
    reproduced = any(
        coerce_finding(item).detector_id == finding.detector_id
        for item in exact.metadata.get("findings", [])
        if isinstance(item, Mapping)
    )
    outcome, detail = ("reproduced", "Runtime detector reproduced.") if reproduced else ("absent", "Runtime detector no longer reproduces.")
    return verification_result(outcome, "runtime", detail, evidence_hash=scenario_hash)
def _verify_contract(
    finding: Finding, _state: Mapping[str, Any], root: Path
) -> VerificationResult:
    from uidetox.frontend_map import frontend_map_is_fresh, load_frontend_map
    from uidetox.project_map import build_project_map
    frontend_map = load_frontend_map(root / ".uidetox" / "frontend-map.json")
    map_hash = current_evidence_hashes(root)["map"]
    if not frontend_map_is_fresh(frontend_map, root, frontend_map.target):
        return verification_result("stale_evidence", "contract", "Frontend map is not current.", evidence_hash=map_hash)
    current = build_project_map(root, frontend_map.nodes)
    path = finding.contract_anchor.get("normalized_path")
    current_slice = [
        item for item in current.findings if item.contract_anchor.get("normalized_path") == path
    ]
    evidence_hash = _hash({"map": map_hash, "slice": [item.fingerprint for item in current_slice]})
    reproduced = any(
        item.detector_id == finding.detector_id
        and item.contract_anchor == finding.contract_anchor
        for item in current_slice
    )
    outcome, detail = ("reproduced", "Contract mismatch reproduced.") if reproduced else ("absent", "Contract mismatch no longer reproduces.")
    return verification_result(outcome, "contract", detail, evidence_hash=evidence_hash)
def _verify_manual(
    finding: Finding, state: Mapping[str, Any], root: Path
) -> VerificationResult:
    review = _mapping(state.get("subjective"))
    hashes = current_evidence_hashes(root)
    evidence_hash = _hash({"review": _identity(review), "current": hashes})
    if structured_review_current(review, hashes) and finding.fingerprint in review.get(
        "finding_links", ()
    ):
        return verification_result("absent", "manual", "Linked structured review confirms remediation.", evidence_hash=evidence_hash)
    return verification_result("stale_evidence", "manual", "A current linked structured review is required.", evidence_hash=evidence_hash)
