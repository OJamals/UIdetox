"""Constrained JSON worker for isolated local visual-evidence processing."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from uidetox.visual_evidence import (
    VisualEvidenceError,
    build_visual_evidence,
)
from uidetox.visual_worker_protocol import (
    HARD_MAX_REQUEST_BYTES,
    WORKER_PROTOCOL_VERSION,
    assert_request_paths_allowed,
    visual_request_from_dict,
    worker_policy_from_dict,
)


class _NonFiniteJsonError(ValueError):
    """Raised when the worker receives a non-standard JSON number."""


def _reject_json_constant(value: str) -> None:
    raise _NonFiniteJsonError(f"Non-finite JSON number is unsupported: {value}")


def _response_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_response(
    payload: dict[str, Any],
    *,
    limit: int,
) -> bool:
    encoded = _response_bytes(payload)
    oversized = len(encoded) > limit
    if oversized:
        encoded = _response_bytes(
            {
                "protocol_version": WORKER_PROTOCOL_VERSION,
                "ok": False,
                "error": {
                    "code": "worker_output_too_large",
                    "message": (
                        "Visual worker response exceeded the configured "
                        f"{limit:,}-byte limit."
                    ),
                },
            }
        )
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    return bool(payload.get("ok")) and not oversized


def _error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, VisualEvidenceError):
        code = error.code
        message = str(error)
    else:
        code = "worker_internal"
        message = f"{type(error).__name__}: {error}"
    return {
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "ok": False,
        "error": {
            "code": code,
            "message": " ".join(message.split())[:1000],
        },
    }


def _apply_resource_limits(policy: Any) -> None:
    try:
        import resource
    except ImportError:
        return

    resource.setrlimit(
        resource.RLIMIT_CPU,
        (policy.cpu_seconds, policy.cpu_seconds),
    )
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (policy.max_file_bytes, policy.max_file_bytes),
    )
    nofile_limit = min(64, resource.getrlimit(resource.RLIMIT_NOFILE)[1])
    resource.setrlimit(
        resource.RLIMIT_NOFILE,
        (nofile_limit, nofile_limit),
    )
    if sys.platform.startswith("linux") and hasattr(resource, "RLIMIT_AS"):
        resource.setrlimit(
            resource.RLIMIT_AS,
            (policy.max_memory_bytes, policy.max_memory_bytes),
        )
    elif sys.platform != "darwin" and hasattr(resource, "RLIMIT_DATA"):
        resource.setrlimit(
            resource.RLIMIT_DATA,
            (policy.max_memory_bytes, policy.max_memory_bytes),
        )


def main() -> int:
    raw = sys.stdin.buffer.read(HARD_MAX_REQUEST_BYTES + 1)
    if len(raw) > HARD_MAX_REQUEST_BYTES:
        _write_response(
            _error_payload(
                VisualEvidenceError(
                    "worker_request_too_large",
                    (
                        "Visual worker request exceeded the hard "
                        f"{HARD_MAX_REQUEST_BYTES:,}-byte limit."
                    ),
                )
            ),
            limit=64 * 1024,
        )
        return 1
    try:
        envelope = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
        if not isinstance(envelope, dict):
            raise VisualEvidenceError(
                "worker_protocol",
                "Visual worker envelope must be a JSON object.",
            )
        if envelope.get("protocol_version") != WORKER_PROTOCOL_VERSION:
            raise VisualEvidenceError(
                "worker_protocol",
                "Unsupported visual worker protocol version.",
            )
        policy = worker_policy_from_dict(envelope.get("policy"))
        if len(raw) > policy.max_request_bytes:
            raise VisualEvidenceError(
                "worker_request_too_large",
                (
                    f"Visual worker request has {len(raw):,} bytes; "
                    f"configured limit is {policy.max_request_bytes:,}."
                ),
            )
        _apply_resource_limits(policy)
        request = visual_request_from_dict(envelope.get("request"))
        assert_request_paths_allowed(request, policy)
        manifest = build_visual_evidence(request)
        response = {
            "protocol_version": WORKER_PROTOCOL_VERSION,
            "ok": True,
            "manifest": manifest.to_dict(),
        }
        success = _write_response(
            response,
            limit=policy.max_output_bytes,
        )
        return 0 if success else 1
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _NonFiniteJsonError,
    ) as error:
        output_limit = policy.max_output_bytes if "policy" in locals() else 64 * 1024
        _write_response(
            _error_payload(
                VisualEvidenceError(
                    "worker_request",
                    f"Visual worker request is not valid UTF-8 JSON: {error}",
                )
            ),
            limit=output_limit,
        )
        return 1
    except Exception as error:
        output_limit = policy.max_output_bytes if "policy" in locals() else 64 * 1024
        _write_response(_error_payload(error), limit=output_limit)
        return 1


if __name__ == "__main__":
    os.environ.setdefault("TZ", "UTC")
    raise SystemExit(main())
