"""Adversarial tests for the isolated visual-evidence worker boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

import uidetox.visual_worker_client as worker_client
from uidetox.visual_evidence import (
    VisualEvidenceCase,
    VisualEvidenceError,
    VisualEvidenceRequest,
    VisualRegion,
    build_visual_evidence,
)
from uidetox.visual_worker_client import (
    build_visual_evidence_isolated,
    visual_worker_argv,
)
from uidetox.visual_worker_protocol import (
    WORKER_PROTOCOL_VERSION,
    VisualWorkerPolicy,
    validate_worker_manifest,
)


def _request(
    tmp_path: Path,
    *,
    before: Path | None = None,
    after: Path | None = None,
    context: dict[str, object] | None = None,
) -> VisualEvidenceRequest:
    before_path = before or tmp_path / "before.png"
    after_path = after or tmp_path / "after.png"
    if before is None:
        Image.new("RGB", (3, 2), (0, 0, 0)).save(before_path)
    if after is None:
        changed = Image.new("RGB", (3, 2), (0, 0, 0))
        changed.putpixel((1, 1), (31, 0, 0))
        changed.save(after_path)
    return VisualEvidenceRequest(
        comparisons=(
            VisualEvidenceCase(
                case_id="desktop",
                before_path=before_path,
                after_path=after_path,
                viewport=(3, 2),
            ),
        ),
        output_dir=tmp_path / "evidence",
        manifest_path=tmp_path / "evidence" / "manifest.json",
        context=context or {},
    )


def _policy(tmp_path: Path, **overrides: object) -> VisualWorkerPolicy:
    values: dict[str, object] = {"allowed_roots": (tmp_path,)}
    values.update(overrides)
    return VisualWorkerPolicy(**values)  # type: ignore[arg-type]


def _fake_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    script = tmp_path / "fake_worker.py"
    script.write_text(source, encoding="utf-8")
    monkeypatch.setattr(
        worker_client,
        "visual_worker_argv",
        lambda: [sys.executable, str(script)],
    )


def test_isolated_worker_builds_and_parent_validates_manifest(
    tmp_path: Path,
) -> None:
    manifest = build_visual_evidence_isolated(
        _request(tmp_path),
        policy=_policy(tmp_path),
    )

    assert manifest.status == "complete"
    assert manifest.comparisons[0].metrics.pixels_changed == 1
    assert (tmp_path / "evidence" / "manifest.json").is_file()


def test_worker_argv_is_explicit_isolated_python_module() -> None:
    assert visual_worker_argv() == [
        sys.executable,
        "-I",
        "-m",
        "uidetox.visual_worker",
    ]


def test_worker_returns_structured_nonzero_error_for_corrupt_json(
    tmp_path: Path,
) -> None:
    process = subprocess.run(
        visual_worker_argv(),
        input=b"{not-json\n",
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    response = json.loads(process.stdout)
    assert process.returncode != 0
    assert response["protocol_version"] == WORKER_PROTOCOL_VERSION
    assert response["ok"] is False
    assert response["error"]["code"] == "worker_request"


def test_worker_rejects_nonstandard_nonfinite_json_number(
    tmp_path: Path,
) -> None:
    process = subprocess.run(
        visual_worker_argv(),
        input=b'{"protocol_version":NaN}\n',
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    response = json.loads(process.stdout)
    assert process.returncode != 0
    assert response["ok"] is False
    assert response["error"]["code"] == "worker_request"


def test_parent_rejects_oversized_serialized_request(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        context={"padding": "x" * 4_000},
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            request,
            policy=_policy(tmp_path, max_request_bytes=1024),
        )

    assert captured.value.code == "worker_request_too_large"


def test_parent_rejects_oversized_input_before_decode(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.png"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    request = _request(tmp_path, before=oversized)

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            request,
            policy=_policy(tmp_path, max_file_bytes=1024 * 1024),
        )

    assert captured.value.code == "worker_input_too_large"


def test_parent_rejects_source_path_outside_allowed_root(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    before = tmp_path / "outside.png"
    Image.new("RGB", (3, 2), (0, 0, 0)).save(before)
    request = _request(allowed, before=before)

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            request,
            policy=VisualWorkerPolicy(allowed_roots=(allowed,)),
        )

    assert captured.value.code == "worker_path"


def test_parent_terminates_worker_at_wall_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_worker(
        tmp_path,
        monkeypatch,
        "import time\ntime.sleep(10)\n",
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            _request(tmp_path),
            policy=_policy(tmp_path, timeout_seconds=0.1),
        )

    assert captured.value.code == "worker_timeout"


def test_wall_timeout_includes_non_reading_worker_stdin_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_worker(
        tmp_path,
        monkeypatch,
        "import time\ntime.sleep(2)\n",
    )
    request = replace(
        _request(tmp_path),
        context={"padding": "x" * 180_000},
    )

    started = time.monotonic()
    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            request,
            policy=_policy(tmp_path, timeout_seconds=0.1),
        )

    assert captured.value.code == "worker_timeout"
    assert time.monotonic() - started < 0.8


def test_timeout_terminates_worker_process_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_file = tmp_path / "child.pid"
    _fake_worker(
        tmp_path,
        monkeypatch,
        "import subprocess, sys, time\n"
        "child = subprocess.Popen("
        "[sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"open({str(pid_file)!r}, 'w', encoding='utf-8').write(str(child.pid))\n"
        "time.sleep(30)\n",
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            _request(tmp_path),
            policy=_policy(tmp_path, timeout_seconds=0.2),
        )

    assert captured.value.code == "worker_timeout"
    child_pid = int(pid_file.read_text(encoding="utf-8"))
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("worker descendant survived process-group termination")


def test_parent_terminates_worker_on_oversized_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_worker(
        tmp_path,
        monkeypatch,
        "import sys\nsys.stdout.write('x' * 2048)\n",
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            _request(tmp_path),
            policy=_policy(tmp_path, max_output_bytes=1024),
        )

    assert captured.value.code == "worker_stdout_too_large"


def test_parent_preserves_nonzero_exit_and_bounded_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_worker(
        tmp_path,
        monkeypatch,
        "import sys\nsys.stderr.write('decoder exploded')\nraise SystemExit(9)\n",
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            _request(tmp_path),
            policy=_policy(tmp_path),
        )

    assert captured.value.code == "worker_failed"
    assert "status 9" in str(captured.value)
    assert "decoder exploded" in str(captured.value)


def test_worker_structures_unexpected_nested_json_failure(
    tmp_path: Path,
) -> None:
    nested = (
        '{"protocol_version":1,"payload":' + "[" * 100_000 + "0" + "]" * 100_000 + "}\n"
    ).encode()

    process = subprocess.run(
        visual_worker_argv(),
        input=nested,
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )

    response = json.loads(process.stdout)
    assert process.returncode != 0
    assert response["ok"] is False
    assert response["error"]["code"] == "worker_internal"
    assert b"Traceback" not in process.stderr


def test_parent_preserves_missing_pillow_worker_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = {
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "ok": False,
        "error": {
            "code": "missing_dependency",
            "message": "Install the visual extra.",
        },
    }
    _fake_worker(
        tmp_path,
        monkeypatch,
        f"import json\nprint(json.dumps({response!r}))\nraise SystemExit(2)\n",
    )

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            _request(tmp_path),
            policy=_policy(tmp_path),
        )

    assert captured.value.code == "missing_dependency"
    assert "visual extra" in str(captured.value)


def test_parent_rejects_tampered_worker_manifest(tmp_path: Path) -> None:
    request = _request(tmp_path)
    build_visual_evidence(request)
    assert request.manifest_path is not None
    payload = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    payload["comparisons"][0]["metrics"]["pixels_changed"] = 999

    with pytest.raises(VisualEvidenceError) as captured:
        validate_worker_manifest(
            payload,
            request=request,
            policy=_policy(tmp_path),
        )

    assert captured.value.code == "worker_response"


def test_parent_rejects_forged_image_metric_and_context_evidence(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    build_visual_evidence(request)
    assert request.manifest_path is not None
    original = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    mutations = (
        (
            "after width",
            lambda payload: payload["comparisons"][0]["after"].__setitem__("width", -7),
        ),
        (
            "after frames",
            lambda payload: payload["comparisons"][0]["after"].__setitem__(
                "frames", 99
            ),
        ),
        (
            "threshold",
            lambda payload: payload["comparisons"][0]["metrics"].__setitem__(
                "threshold", -123
            ),
        ),
        (
            "mean delta",
            lambda payload: payload["comparisons"][0]["metrics"].__setitem__(
                "mean_channel_delta",
                [-1.0, 999_999.0, 0.0],
            ),
        ),
        (
            "extrema",
            lambda payload: payload["comparisons"][0]["metrics"].__setitem__(
                "extrema",
                [[0, 999], [0, 0], [0, 0]],
            ),
        ),
        (
            "exact match",
            lambda payload: payload["comparisons"][0]["metrics"].__setitem__(
                "exact_match",
                not payload["comparisons"][0]["metrics"]["exact_match"],
            ),
        ),
        (
            "coverage",
            lambda payload: payload["comparisons"][0]["metrics"].__setitem__(
                "coverage_band",
                "forged",
            ),
        ),
        (
            "context",
            lambda payload: payload.__setitem__(
                "context",
                {"intent": "forged"},
            ),
        ),
    )

    for label, mutate in mutations:
        payload = copy.deepcopy(original)
        mutate(payload)
        with pytest.raises(
            VisualEvidenceError,
            match="Worker",
        ) as captured:
            validate_worker_manifest(
                payload,
                request=request,
                policy=_policy(tmp_path),
            )
        assert captured.value.code == "worker_response", label


def test_parent_rejects_malformed_region_bounds_as_worker_response(
    tmp_path: Path,
) -> None:
    base = _request(tmp_path)
    case = replace(
        base.comparisons[0],
        semantic_regions=(
            VisualRegion(
                region_id="hero",
                kind="semantic",
                bounds=(0.0, 0.0, 2.0, 2.0),
                provenance="runtime",
            ),
        ),
    )
    request = replace(base, comparisons=(case,))
    build_visual_evidence(request)
    assert request.manifest_path is not None
    payload = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    payload["comparisons"][0]["regions"][0]["bounds"] = [0]

    with pytest.raises(VisualEvidenceError) as captured:
        validate_worker_manifest(
            payload,
            request=request,
            policy=_policy(tmp_path),
        )

    assert captured.value.code == "worker_response"


def test_parent_rejects_nonfinite_manifest_context_as_worker_response(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    build_visual_evidence(request)
    assert request.manifest_path is not None
    payload = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    payload["context"] = {"forged": float("nan")}

    with pytest.raises(VisualEvidenceError) as captured:
        validate_worker_manifest(
            payload,
            request=request,
            policy=_policy(tmp_path),
        )

    assert captured.value.code == "worker_response"
    assert "finite JSON" in str(captured.value)


def test_parent_rejects_oversized_worker_artifact_before_hashing(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    build_visual_evidence(request)
    assert request.manifest_path is not None
    payload = json.loads(request.manifest_path.read_text(encoding="utf-8"))
    oversized = request.output_dir / "oversized.png"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    artifact = payload["comparisons"][0]["artifacts"][0]
    artifact["path"] = str(oversized)
    artifact["sha256"] = hashlib.sha256(oversized.read_bytes()).hexdigest()

    with pytest.raises(VisualEvidenceError) as captured:
        validate_worker_manifest(
            payload,
            request=request,
            policy=_policy(tmp_path, max_file_bytes=1024 * 1024),
        )

    assert captured.value.code == "worker_response"
    assert "exceeds" in str(captured.value)


def test_isolated_worker_rejects_multiframe_png(tmp_path: Path) -> None:
    before = tmp_path / "animated.png"
    after = tmp_path / "after.png"
    frames = [
        Image.new("RGB", (3, 2), (0, 0, 0)),
        Image.new("RGB", (3, 2), (255, 0, 0)),
    ]
    frames[0].save(
        before,
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        format="PNG",
    )
    Image.new("RGB", (3, 2), (0, 0, 0)).save(after)

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(
            _request(tmp_path, before=before, after=after),
            policy=_policy(tmp_path),
        )

    assert captured.value.code == "animated_image"


def test_worker_policy_requires_integer_byte_and_cpu_limits(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    policy = replace(_policy(tmp_path), cpu_seconds=1.5)  # type: ignore[arg-type]

    with pytest.raises(VisualEvidenceError) as captured:
        build_visual_evidence_isolated(request, policy=policy)

    assert captured.value.code == "worker_policy"
