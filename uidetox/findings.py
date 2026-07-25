"""Canonical evidence-bound finding lifecycle.

All detector families cross persistence, remediation, scoring, and release
seams through :class:`Finding`. Producer-specific candidates may exist inside a
detector implementation, but must be converted before leaving that module.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from uidetox.prompt_safety import sanitize_untrusted_data
from uidetox.utils import now_iso

FINDING_SCHEMA_VERSION = 2
_VOLATILE_EVIDENCE_KEYS = {
    "checked_at",
    "created_at",
    "generated_at",
    "source_hash",
    "timestamp",
}
_SEVERITY_TO_TIER = {"info": "T1", "warning": "T2", "error": "T3", "critical": "T4"}
_TIER_TO_SEVERITY = {value: key for key, value in _SEVERITY_TO_TIER.items()}
_SEVERITY_WEIGHT = {"info": 3.0, "warning": 10.0, "error": 20.0, "critical": 30.0}
_CANONICAL_KEYS = {
    "schema_version",
    "fingerprint",
    "id",
    "code",
    "detector_id",
    "category",
    "severity",
    "confidence",
    "message",
    "status",
    "provenance",
    "evidence",
    "evidence_freshness",
    "source_anchor",
    "runtime_anchor",
    "contract_anchor",
    "suppression_key",
    "verifier",
    "last_verification",
    "display_excerpt",
    "legacy",
    "extensions",
    "file",
    "tier",
    "issue",
    "command",
    "line",
    "column",
    "snippet",
    "metrics",
    "kind",
    "normalized_path",
    "frontend",
    "backend",
    "detail",
}


class _FrozenMapping(Mapping[str, Any]):
    """Recursively immutable mapping; never a ``dict`` mutation backdoor."""

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
        return _FrozenMapping(
            (str(key), _freeze(item))
            for key, item in value.items()
        )
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


def _clean_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _FrozenMapping()  # type: ignore[return-value]
    return _freeze(value)  # type: ignore[return-value]


def _safe_payload(value: Mapping[str, Any], *, matched_evidence: object = None) -> dict:
    matched = matched_evidence if isinstance(matched_evidence, (str, bytes)) else None
    cleaned = sanitize_untrusted_data(dict(value), matched_evidence=matched)
    return dict(cleaned) if isinstance(cleaned, Mapping) else {}


def _normalized_identity(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _normalized_identity(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_EVIDENCE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_normalized_identity(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _fingerprint(
    detector_id: str,
    source_anchor: Mapping[str, Any],
    runtime_anchor: Mapping[str, Any],
    contract_anchor: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> str:
    identity = {
        "detector_id": detector_id,
        "source_anchor": _normalized_identity(source_anchor),
        "runtime_anchor": _normalized_identity(runtime_anchor),
        "contract_anchor": _normalized_identity(contract_anchor),
        "evidence": _normalized_identity(evidence),
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class VerificationResult:
    """Result of rerunning a finding's originating verifier."""

    outcome: str
    checked_at: str
    verifier_kind: str
    detail: str = ""
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "outcome": self.outcome,
            "checked_at": self.checked_at,
            "verifier_kind": self.verifier_kind,
            "detail": self.detail,
            "evidence_hash": self.evidence_hash,
        }

    @classmethod
    def from_dict(cls, value: object) -> VerificationResult | None:
        if not isinstance(value, Mapping):
            return None
        return cls(
            outcome=str(value.get("outcome", "")),
            checked_at=str(value.get("checked_at", "")),
            verifier_kind=str(value.get("verifier_kind", "")),
            detail=str(value.get("detail", "")),
            evidence_hash=str(value.get("evidence_hash", "")),
        )


@dataclass(frozen=True)
class Finding(Mapping[str, Any]):
    """Immutable typed finding with a versioned JSON representation."""

    detector_id: str
    category: str
    severity: str
    confidence: float
    message: str
    status: str
    provenance: str
    evidence: dict[str, Any] = field(default_factory=dict)
    evidence_freshness: str = "fresh"
    source_anchor: dict[str, Any] = field(default_factory=dict)
    runtime_anchor: dict[str, Any] = field(default_factory=dict)
    contract_anchor: dict[str, Any] = field(default_factory=dict)
    suppression_key: str = ""
    verifier: dict[str, Any] = field(default_factory=dict)
    last_verification: VerificationResult | None = None
    display_excerpt: str = ""
    legacy: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict, repr=False)
    fingerprint: str = ""
    schema_version: int = FINDING_SCHEMA_VERSION
    id: str = field(init=False)
    code: str = field(init=False)
    metrics: dict[str, Any] = field(init=False)
    kind: str = field(init=False)
    normalized_path: str = field(init=False)
    frontend: tuple[str, ...] = field(init=False)
    backend: tuple[str, ...] = field(init=False)
    detail: str = field(init=False)

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
            object.__setattr__(self, name, _clean_mapping(getattr(self, name)))
        actual = self.fingerprint or _fingerprint(
            self.detector_id,
            self.source_anchor,
            self.runtime_anchor,
            self.contract_anchor,
            self.evidence,
        )
        object.__setattr__(self, "fingerprint", actual)
        object.__setattr__(self, "id", actual)
        object.__setattr__(self, "code", self.detector_id)
        metrics = self.evidence.get("metrics", self.evidence)
        object.__setattr__(
            self,
            "metrics",
            _clean_mapping(metrics),
        )
        object.__setattr__(
            self, "kind", str(self.contract_anchor.get("kind", ""))
        )
        object.__setattr__(
            self,
            "normalized_path",
            str(self.contract_anchor.get("normalized_path", "")),
        )
        object.__setattr__(
            self,
            "frontend",
            tuple(str(item) for item in self.evidence.get("frontend", [])),
        )
        object.__setattr__(
            self,
            "backend",
            tuple(str(item) for item in self.evidence.get("backend", [])),
        )
        object.__setattr__(self, "detail", self.message)

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
        evidence: Mapping[str, Any] | None = None,
        evidence_freshness: str = "fresh",
        source_anchor: Mapping[str, Any] | None = None,
        runtime_anchor: Mapping[str, Any] | None = None,
        contract_anchor: Mapping[str, Any] | None = None,
        suppression_key: str = "",
        verifier: Mapping[str, Any] | None = None,
        last_verification: VerificationResult | None = None,
        status: str = "pending",
        display_excerpt: str = "",
        legacy: Mapping[str, Any] | None = None,
    ) -> Finding:
        raw = {
            "detector_id": detector_id,
            "category": category,
            "severity": severity,
            "confidence": confidence,
            "message": message,
            "status": status,
            "provenance": provenance,
            "evidence": dict(evidence or {}),
            "evidence_freshness": evidence_freshness,
            "source_anchor": dict(source_anchor or {}),
            "runtime_anchor": dict(runtime_anchor or {}),
            "contract_anchor": dict(contract_anchor or {}),
            "suppression_key": suppression_key,
            "verifier": dict(verifier or {}),
            "display_excerpt": display_excerpt,
            "legacy": dict(legacy or {}),
        }
        matched = raw["evidence"].get("matched_text")
        clean = _safe_payload(raw, matched_evidence=matched)
        return cls(
            detector_id=str(clean.get("detector_id", detector_id)),
            category=str(clean.get("category", category)),
            severity=str(clean.get("severity", severity)).lower(),
            confidence=max(0.0, min(1.0, float(clean.get("confidence", confidence)))),
            message=str(clean.get("message", message)),
            status=str(clean.get("status", status)),
            provenance=str(clean.get("provenance", provenance)),
            evidence=_clean_mapping(clean.get("evidence")),
            evidence_freshness=str(
                clean.get("evidence_freshness", evidence_freshness)
            ),
            source_anchor=_clean_mapping(clean.get("source_anchor")),
            runtime_anchor=_clean_mapping(clean.get("runtime_anchor")),
            contract_anchor=_clean_mapping(clean.get("contract_anchor")),
            suppression_key=str(clean.get("suppression_key", suppression_key)),
            verifier=_clean_mapping(clean.get("verifier")),
            last_verification=last_verification,
            display_excerpt=str(clean.get("display_excerpt", display_excerpt)),
            legacy=_clean_mapping(clean.get("legacy")),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Finding:
        raw = _safe_payload(value, matched_evidence=value.get("matched_evidence"))
        version = int(raw.get("schema_version", 0) or 0)
        if version != FINDING_SCHEMA_VERSION or "detector_id" not in raw:
            return cls._from_legacy(raw)

        known = {key: raw.get(key) for key in _CANONICAL_KEYS}
        extensions = _clean_mapping(raw.get("extensions"))
        extensions = {
            **_thaw(extensions),  # type: ignore[arg-type]
            **{key: item for key, item in raw.items() if key not in _CANONICAL_KEYS},
        }
        verification = VerificationResult.from_dict(known.get("last_verification"))
        finding = cls(
            detector_id=str(known.get("detector_id", known.get("code", "unknown"))),
            category=str(known.get("category", "quality")),
            severity=str(known.get("severity", "warning")).lower(),
            confidence=max(
                0.0, min(1.0, float(known.get("confidence", 0.5) or 0.5))
            ),
            message=str(known.get("message", known.get("issue", "Finding"))),
            status=str(known.get("status", "pending")),
            provenance=str(known.get("provenance", "static")),
            evidence=_clean_mapping(known.get("evidence")),
            evidence_freshness=str(known.get("evidence_freshness", "fresh")),
            source_anchor=_clean_mapping(known.get("source_anchor")),
            runtime_anchor=_clean_mapping(known.get("runtime_anchor")),
            contract_anchor=_clean_mapping(known.get("contract_anchor")),
            suppression_key=str(known.get("suppression_key", "")),
            verifier=_clean_mapping(known.get("verifier")),
            last_verification=verification,
            display_excerpt=str(known.get("display_excerpt", known.get("snippet", ""))),
            legacy=_clean_mapping(known.get("legacy")),
            extensions=extensions,
            fingerprint=str(known.get("fingerprint", "")),
            schema_version=FINDING_SCHEMA_VERSION,
        )
        expected = _fingerprint(
            finding.detector_id,
            finding.source_anchor,
            finding.runtime_anchor,
            finding.contract_anchor,
            finding.evidence,
        )
        if finding.fingerprint != expected:
            object.__setattr__(finding, "fingerprint", expected)
            object.__setattr__(finding, "id", expected)
        return finding

    @classmethod
    def _from_legacy(cls, raw: Mapping[str, Any]) -> Finding:
        if "kind" in raw and "normalized_path" in raw:
            kind = str(raw.get("kind", "unresolved"))
            path = str(raw.get("normalized_path", ""))
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
                status=(
                    "investigate"
                    if kind in {"unresolved", "backend_only"}
                    else "pending"
                ),
                legacy=raw,
            )
        if "code" in raw and ("metrics" in raw or "runtime_anchor" in raw):
            code = str(raw.get("code", "runtime-layout-finding"))
            metrics = _clean_mapping(raw.get("metrics"))
            return cls.create(
                detector_id=code,
                category=str(raw.get("category", "layout")),
                severity=str(raw.get("severity", "warning")),
                confidence=float(raw.get("confidence", 0.9) or 0.9),
                message=str(raw.get("message", "Rendered layout needs review.")),
                provenance="runtime",
                evidence={"metrics": metrics},
                runtime_anchor=_clean_mapping(raw.get("runtime_anchor")),
                suppression_key=code,
                verifier={"kind": "runtime", "detector_id": code},
                legacy=raw,
            )

        detector_id = str(raw.get("detector_id", raw.get("rule_id", ""))).strip()
        queue_id = str(raw.get("id", "")).strip()
        if not detector_id:
            if queue_id and not queue_id.startswith("SCAN-"):
                detector_id = queue_id
            else:
                manual_identity = "|".join(
                    str(raw.get(key, "")).strip()
                    for key in ("file", "issue", "command")
                )
                detector_id = (
                    "manual-"
                    + hashlib.sha256(manual_identity.encode("utf-8")).hexdigest()[:16]
                )
        source_anchor = {
            "path": str(raw.get("file", "")),
            "line": int(raw.get("line", 0) or 0),
            "column": int(raw.get("column", 0) or 0),
        }
        if raw.get("start") is not None:
            source_anchor["start"] = int(raw["start"])
        if raw.get("end") is not None:
            source_anchor["end"] = int(raw["end"])
        severity = str(raw.get("severity", "")).lower() or _TIER_TO_SEVERITY.get(
            str(raw.get("tier", "T2")), "warning"
        )
        return cls.create(
            detector_id=detector_id,
            category=str(raw.get("category", "quality")),
            severity=severity,
            confidence=float(raw.get("confidence", 0.8) or 0.8),
            message=str(raw.get("message", raw.get("issue", "Finding"))),
            provenance=str(raw.get("provenance", "static")),
            evidence=_clean_mapping(raw.get("evidence")),
            evidence_freshness=str(raw.get("evidence_freshness", "fresh")),
            source_anchor=source_anchor,
            suppression_key=str(raw.get("suppression_key", detector_id)),
            verifier=_clean_mapping(raw.get("verifier"))
            or {
                "kind": "static" if source_anchor["path"] else "manual",
                "detector_id": detector_id,
            },
            status=str(raw.get("status", "pending")),
            display_excerpt=str(raw.get("display_excerpt", raw.get("snippet", ""))),
            legacy=raw,
        )

    @property
    def tier(self) -> str:
        return _SEVERITY_TO_TIER.get(self.severity, "T2")

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self.extensions)
        assert isinstance(payload, dict)
        payload.update(
            {
                "schema_version": FINDING_SCHEMA_VERSION,
                "fingerprint": self.fingerprint,
                "id": str(self.legacy.get("id", self.id)),
                "code": self.code,
                "detector_id": self.detector_id,
                "category": self.category,
                "severity": self.severity,
                "confidence": self.confidence,
                "message": self.message,
                "status": self.status,
                "provenance": self.provenance,
                "evidence": _thaw(self.evidence),
                "evidence_freshness": self.evidence_freshness,
                "source_anchor": _thaw(self.source_anchor),
                "runtime_anchor": _thaw(self.runtime_anchor),
                "contract_anchor": _thaw(self.contract_anchor),
                "suppression_key": self.suppression_key,
                "verifier": _thaw(self.verifier),
                "last_verification": (
                    self.last_verification.to_dict()
                    if self.last_verification is not None
                    else None
                ),
                "display_excerpt": self.display_excerpt,
                "legacy": _thaw(self.legacy),
                # Compatibility display fields are derived, never mutable truth.
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


def coerce_finding(value: Finding | Mapping[str, Any]) -> Finding:
    return value if isinstance(value, Finding) else Finding.from_dict(value)


def score_current_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    """Score only current evidence; resolved history never increases score."""
    pending = [
        coerce_finding(item)
        for item in state.get("issues", [])
        if isinstance(item, (Finding, Mapping))
    ]
    snapshot = _clean_mapping(state.get("current_snapshot"))
    coverage = snapshot.get("qualified_coverage", 0.0)
    if not isinstance(coverage, (int, float)) or isinstance(coverage, bool):
        coverage = 0.0
    qualified_coverage = max(0.0, min(1.0, float(coverage)))
    current_slop = round(
        sum(
            _SEVERITY_WEIGHT.get(finding.severity, 10.0) * finding.confidence
            for finding in pending
            if finding.status
            not in {"informational", "investigate", "suppressed", "verified_resolved"}
        ),
        2,
    )
    objective_score = max(
        0, min(100, round(100 * qualified_coverage - current_slop))
    )
    subjective = _clean_mapping(state.get("subjective"))
    structured_score = _structured_review_score(subjective)
    subjective_score = (
        structured_score if structured_score is not None and not subjective.get("stale") else None
    )
    blended_score = (
        round(objective_score * 0.6 + subjective_score * 0.4)
        if subjective_score is not None
        else objective_score
    )
    return {
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "blended_score": blended_score,
        "current_slop": current_slop,
        "resolved_slop": 0,
        "total_slop": current_slop,
        "qualified_coverage": qualified_coverage,
    }


@dataclass(frozen=True)
class EligibilityBlocker:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _clean_mapping(self.details))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": _thaw(self.details),
        }


@dataclass(frozen=True)
class EligibilityContext:
    target_score: int = 95
    current_branch: str = ""
    session_branch: str = ""
    dirty: bool = False
    verification_fresh: bool = True
    require_session_branch: bool = False
    evidence_hashes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_hashes", _clean_mapping(self.evidence_hashes))


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    score: dict[str, Any]
    blockers: tuple[EligibilityBlocker, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", _clean_mapping(self.score))
        object.__setattr__(self, "blockers", tuple(self.blockers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "score": _thaw(self.score),
            "blockers": [item.to_dict() for item in self.blockers],
        }


def _structured_review_score(review: Mapping[str, Any]) -> int | None:
    dimensions = review.get("dimensions")
    if not isinstance(dimensions, Mapping) or set(dimensions) != {"A", "B", "C", "D"}:
        return None
    caps = {"A": 40, "B": 30, "C": 20, "D": 10}
    values: dict[str, float] = {}
    for key, cap in caps.items():
        value = dimensions[key]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 <= float(value) <= cap
        ):
            return None
        values[key] = float(value)
    total = sum(values.values())
    score = review.get("score")
    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not 0 <= float(score) <= 100
        or float(score) != total
    ):
        return None
    return round(total)


def _structured_review_complete(review: Mapping[str, Any]) -> bool:
    if _structured_review_score(review) is None:
        return False
    if not str(review.get("rationale", "")).strip():
        return False
    if not str(review.get("reviewer", "")).strip():
        return False
    for key in ("finding_links", "routes", "states", "viewports"):
        values = review.get(key)
        if not isinstance(values, (list, tuple)) or not all(
            isinstance(item, str) for item in values
        ):
            return False
    hashes = review.get("evidence_hashes")
    return (
        isinstance(hashes, Mapping)
        and set(hashes) == {"source", "map", "runtime"}
        and all(str(hashes[key]).strip() for key in ("source", "map", "runtime"))
    )


def evaluate_eligibility(
    state: Mapping[str, Any],
    context: EligibilityContext,
) -> EligibilityResult:
    """Return one shared typed finalization decision."""
    blockers: list[EligibilityBlocker] = []
    pending = [
        item
        for item in state.get("issues", [])
        if isinstance(item, (Finding, Mapping))
        and coerce_finding(item).status
        not in {
            "informational",
            "investigate",
            "suppressed",
            "verified_resolved",
        }
    ]
    if pending:
        blockers.append(
            EligibilityBlocker(
                "pending_findings",
                f"{len(pending)} finding(s) still require verified resolution.",
                {"count": len(pending)},
            )
        )

    score = score_current_snapshot(state)
    if int(score["blended_score"]) < context.target_score:
        blockers.append(
            EligibilityBlocker(
                "target_score",
                (
                    f"Current score {score['blended_score']} is below "
                    f"target {context.target_score}."
                ),
                {
                    "score": score["blended_score"],
                    "target": context.target_score,
                },
            )
        )
    if float(score["qualified_coverage"]) < 1.0:
        blockers.append(
            EligibilityBlocker(
                "incomplete_qualification",
                "Current detector qualification coverage is incomplete.",
                {"coverage": score["qualified_coverage"]},
            )
        )
    if not context.verification_fresh:
        blockers.append(
            EligibilityBlocker(
                "stale_evidence",
                "Current source/map/runtime verification evidence is stale.",
            )
        )

    review = _clean_mapping(state.get("subjective"))
    if not _structured_review_complete(review):
        blockers.append(
            EligibilityBlocker(
                "missing_structured_review",
                "Structured A/B/C/D subjective review evidence is required.",
            )
        )
    elif review.get("stale") or (
        context.evidence_hashes
        and _clean_mapping(review.get("evidence_hashes")) != context.evidence_hashes
    ):
        blockers.append(
            EligibilityBlocker(
                "stale_review",
                "Subjective review hashes do not match current evidence.",
            )
        )
    if context.dirty:
        blockers.append(
            EligibilityBlocker("dirty_tree", "Git worktree must be clean to finalize.")
        )
    if (
        context.require_session_branch
        and context.current_branch != context.session_branch
    ):
        blockers.append(
            EligibilityBlocker(
                "session_branch_required",
                "Finalization must run from the active UIdetox session branch.",
                {
                    "current_branch": context.current_branch,
                    "session_branch": context.session_branch,
                },
            )
        )
    return EligibilityResult(
        eligible=not blockers,
        score=score,
        blockers=tuple(blockers),
    )


def verification_result(
    outcome: str,
    verifier_kind: str,
    detail: str = "",
    *,
    evidence_hash: str = "",
) -> VerificationResult:
    return VerificationResult(
        outcome=outcome,
        checked_at=now_iso(),
        verifier_kind=verifier_kind,
        detail=detail,
        evidence_hash=evidence_hash,
    )
