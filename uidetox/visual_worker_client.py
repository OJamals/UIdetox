"""Parent-side client for the constrained visual-evidence worker."""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from uidetox.visual_evidence import (
    VisualEvidenceError,
    VisualEvidenceManifest,
    VisualEvidenceRequest,
    validate_visual_evidence_request,
    write_visual_evidence_manifest,
)
from uidetox.visual_worker_protocol import (
    WORKER_PROTOCOL_VERSION,
    VisualWorkerPolicy,
    assert_request_paths_allowed,
    normalize_worker_policy,
    validate_worker_manifest,
    visual_request_to_dict,
)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is unsupported: {value}")


def visual_worker_argv() -> list[str]:
    """Return the exact non-shell worker argv."""

    return [
        sys.executable,
        "-I",
        "-m",
        "uidetox.visual_worker",
    ]


def build_visual_evidence_isolated(
    request: VisualEvidenceRequest,
    *,
    policy: VisualWorkerPolicy,
) -> VisualEvidenceManifest:
    """Run exact comparison in a bounded local worker and validate its output."""

    validate_visual_evidence_request(request)
    normalized_policy = normalize_worker_policy(policy)
    assert_request_paths_allowed(request, normalized_policy)
    envelope = {
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "policy": normalized_policy.to_dict(),
        "request": visual_request_to_dict(request),
    }
    encoded = (
        json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(encoded) > normalized_policy.max_request_bytes:
        raise VisualEvidenceError(
            "worker_request_too_large",
            (
                f"Visual worker request has {len(encoded):,} bytes; "
                f"configured limit is {normalized_policy.max_request_bytes:,}."
            ),
        )
    stdout, stderr, returncode = _run_worker(
        encoded,
        policy=normalized_policy,
    )
    try:
        response = json.loads(
            stdout.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        detail = _worker_exit_detail(returncode, stderr)
        code = "worker_failed" if returncode != 0 else "worker_protocol"
        raise VisualEvidenceError(
            code,
            f"Visual worker returned invalid JSON. {detail}".strip(),
        ) from error
    if not isinstance(response, dict):
        raise VisualEvidenceError(
            "worker_protocol",
            "Visual worker response must be a JSON object.",
        )
    if response.get("protocol_version") != WORKER_PROTOCOL_VERSION:
        raise VisualEvidenceError(
            "worker_protocol",
            "Visual worker returned an unsupported protocol version.",
        )
    if returncode != 0 or response.get("ok") is not True:
        error_payload = response.get("error", {})
        if not isinstance(error_payload, dict):
            error_payload = {}
        code = str(error_payload.get("code", "worker_failed"))
        message = str(
            error_payload.get(
                "message",
                stderr.decode("utf-8", errors="replace")
                or (f"Visual worker exited with status {returncode}."),
            )
        )
        raise VisualEvidenceError(code, " ".join(message.split())[:1000])
    manifest = validate_worker_manifest(
        response.get("manifest"),
        request=request,
        policy=normalized_policy,
    )
    if request.manifest_path is not None:
        manifest_path = request.manifest_path.expanduser().resolve()
        if not _path_within(
            manifest_path,
            normalized_policy.allowed_roots,
        ):
            raise VisualEvidenceError(
                "worker_path",
                f"Manifest path escapes allowed roots: {manifest_path}",
            )
        write_visual_evidence_manifest(manifest_path, manifest)
    return manifest


def _run_worker(
    request_bytes: bytes,
    *,
    policy: VisualWorkerPolicy,
) -> tuple[bytes, bytes, int]:
    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "TZ": "UTC",
    }
    process = subprocess.Popen(
        visual_worker_argv(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=policy.allowed_roots[0],
        env=environment,
        shell=False,
        start_new_session=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    deadline = time.monotonic() + policy.timeout_seconds
    selector = selectors.DefaultSelector()
    read_streams = {
        process.stdout: ("stdout", policy.max_output_bytes),
        process.stderr: ("stderr", policy.max_stderr_bytes),
    }
    for stream in read_streams:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, data="read")
    os.set_blocking(process.stdin.fileno(), False)
    selector.register(process.stdin, selectors.EVENT_WRITE, data="write")
    chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    sizes = {"stdout": 0, "stderr": 0}
    request_offset = 0
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_worker(process)
                raise VisualEvidenceError(
                    "worker_timeout",
                    (
                        "Visual worker exceeded the configured "
                        f"{policy.timeout_seconds:g}-second wall timeout."
                    ),
                )
            events = selector.select(timeout=min(remaining, 0.1))
            if not events and process.poll() is not None:
                if not process.stdin.closed:
                    try:
                        selector.unregister(process.stdin)
                    except KeyError:
                        pass
                    process.stdin.close()
                continue
            for key, _ in events:
                stream = key.fileobj
                if key.data == "write":
                    try:
                        written = os.write(
                            stream.fileno(),
                            request_bytes[request_offset : request_offset + 64 * 1024],
                        )
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        written = 0
                    request_offset += written
                    if written == 0 or request_offset == len(request_bytes):
                        selector.unregister(stream)
                        stream.close()
                    continue
                label, limit = read_streams[stream]
                try:
                    chunk = os.read(stream.fileno(), 64 * 1024)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    continue
                sizes[label] += len(chunk)
                if sizes[label] > limit:
                    _terminate_worker(process)
                    raise VisualEvidenceError(
                        f"worker_{label}_too_large",
                        (
                            f"Visual worker {label} exceeded the configured "
                            f"{limit:,}-byte limit."
                        ),
                    )
                chunks[label].append(chunk)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            _terminate_worker(process)
            raise VisualEvidenceError(
                "worker_timeout",
                (
                    "Visual worker exceeded the configured "
                    f"{policy.timeout_seconds:g}-second wall timeout."
                ),
            ) from error
    finally:
        selector.close()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
        process.stderr.close()
    return (
        b"".join(chunks["stdout"]),
        b"".join(chunks["stderr"]),
        returncode,
    )


def _terminate_worker(process: subprocess.Popen[Any]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            if process.poll() is None:
                process.kill()
    elif process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _worker_exit_detail(returncode: int, stderr: bytes) -> str:
    if returncode < 0:
        status = f"terminated by signal {-returncode}"
    else:
        status = f"exited with status {returncode}"
    detail = " ".join(stderr.decode("utf-8", errors="replace").split())[:1000]
    return f"Worker {status}." + (f" stderr: {detail}" if detail else "")


def _path_within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)
