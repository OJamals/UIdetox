from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from uidetox import (
    frontend_map,
    intent_journal,
    memory,
    persistence,
    state,
    visual_evidence,
)
from uidetox.commands import capture
from uidetox.persistence import atomic_replace_text


class _WriteFailingStream:
    def __init__(self, stream) -> None:
        self._stream = stream

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self._stream.close()

    def write(self, content: str) -> int:
        raise OSError("write failed")

    def flush(self) -> None:
        self._stream.flush()

    def fileno(self) -> int:
        return self._stream.fileno()


def test_atomic_replace_text_writes_exact_unicode_and_replaces_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    target = tmp_path / "dir with spaces 雪" / "artifact.txt"
    target.parent.mkdir()
    try:
        target.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    assert atomic_replace_text(target, "new 雪\n") is None

    assert target.read_bytes() == "new 雪\n".encode()
    assert not target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside"


def test_atomic_replace_text_uses_unique_temps_under_contention(
    tmp_path: Path,
) -> None:
    target = tmp_path / "shared.json"
    payloads = [f'{{"writer":{index},"value":"雪"}}\n' for index in range(64)]

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda content: atomic_replace_text(target, content), payloads))

    assert target.read_text(encoding="utf-8") in payloads
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_capture_json_adapter_is_atomic_under_contention(tmp_path: Path) -> None:
    target = tmp_path / "capture.json"
    payloads = [{"writer": index, "value": "雪"} for index in range(64)]

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda payload: capture._atomic_write_json(target, payload), payloads))

    assert json.loads(target.read_text(encoding="utf-8")) in payloads
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_replace_text_preserves_target_and_cleans_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("prior", encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise PermissionError("replace denied")

    monkeypatch.setattr(persistence.os, "replace", fail_replace)

    with pytest.raises(PermissionError, match="replace denied"):
        atomic_replace_text(target, "replacement")

    assert target.read_text(encoding="utf-8") == "prior"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.parametrize("fault", ["write", "fsync"])
def test_atomic_replace_text_preserves_target_on_pre_replace_failure(
    fault: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("prior", encoding="utf-8")
    if fault == "write":
        real_fdopen = persistence.os.fdopen

        def failing_fdopen(*args, **kwargs):
            return _WriteFailingStream(real_fdopen(*args, **kwargs))

        monkeypatch.setattr(persistence.os, "fdopen", failing_fdopen)
    else:

        def fail_fsync(descriptor: int) -> None:
            raise OSError("fsync failed")

        monkeypatch.setattr(persistence.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match=f"{fault} failed"):
        atomic_replace_text(target, "replacement")

    assert target.read_text(encoding="utf-8") == "prior"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_replace_text_closes_raw_descriptor_when_fdopen_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    descriptor: list[int] = []
    real_mkstemp = persistence.tempfile.mkstemp

    def recording_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        descriptor.append(fd)
        return fd, name

    def fail_fdopen(*args, **kwargs):
        raise RuntimeError("fdopen failed")

    monkeypatch.setattr(persistence.tempfile, "mkstemp", recording_mkstemp)
    monkeypatch.setattr(persistence.os, "fdopen", fail_fdopen)

    with pytest.raises(RuntimeError, match="fdopen failed"):
        atomic_replace_text(tmp_path / "artifact.txt", "content")

    assert len(descriptor) == 1
    with pytest.raises(OSError):
        os.fstat(descriptor[0])
    assert list(tmp_path.iterdir()) == []


def test_atomic_replace_text_preserves_fdopen_error_when_first_close_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_calls = 0
    real_close = persistence.os.close

    def fail_fdopen(*args, **kwargs):
        raise RuntimeError("fdopen failed")

    def flaky_close(descriptor: int) -> None:
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise OSError("close failed")
        real_close(descriptor)

    monkeypatch.setattr(persistence.os, "fdopen", fail_fdopen)
    monkeypatch.setattr(persistence.os, "close", flaky_close)

    with pytest.raises(RuntimeError, match="fdopen failed"):
        atomic_replace_text(tmp_path / "artifact.txt", "content")

    assert close_calls == 2
    assert list(tmp_path.iterdir()) == []


def test_atomic_replace_text_forwards_explicit_temp_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefixes: list[str | None] = []
    real_mkstemp = persistence.tempfile.mkstemp

    def recording_mkstemp(*args, **kwargs):
        prefixes.append(kwargs.get("prefix"))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(persistence.tempfile, "mkstemp", recording_mkstemp)

    atomic_replace_text(
        tmp_path / "artifact.txt",
        "content",
        temp_prefix="state_",
    )

    assert prefixes == ["state_"]
    assert list(tmp_path.glob("state_*.tmp")) == []


def test_state_owned_writers_preserve_exact_temp_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefixes: list[str | None] = []

    def capture_write(
        path: Path,
        content: str,
        *,
        temp_prefix: str | None = None,
    ) -> None:
        prefixes.append(temp_prefix)

    monkeypatch.setattr(state, "atomic_replace_text", capture_write)

    state.save_config({})
    state.save_state({})
    memory.save_memory({})

    assert prefixes == ["config_", "state_", "memory_"]


def test_json_writer_adapters_preserve_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"unicode": "雪", "order": [2, 1]}
    sorted_json = (
        '{\n  "order": [\n    2,\n    1\n  ],\n'
        '  "unicode": "\\u96ea"\n}\n'
    ).encode()
    state_json = (
        '{\n  "unicode": "\\u96ea",\n  "order": [\n'
        "    2,\n    1\n  ]\n}"
    ).encode()
    monkeypatch.chdir(tmp_path)

    state._save_json(payload, "state file.json", "state_")
    capture._atomic_write_json(tmp_path / "capture" / "artifact.json", payload)
    visual_evidence._atomic_write_json(tmp_path / "visual" / "artifact.json", payload)
    frontend_map._atomic_write_json(tmp_path / "map" / "artifact.json", payload)

    assert (tmp_path / ".uidetox" / "state file.json").read_bytes() == state_json
    assert (tmp_path / "capture" / "artifact.json").read_bytes() == sorted_json
    assert (tmp_path / "visual" / "artifact.json").read_bytes() == sorted_json
    assert (tmp_path / "map" / "artifact.json").read_bytes() == sorted_json


def test_json_writer_adapters_serialize_before_creating_temp_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"bad": {1}}

    def unexpected_write(*args, **kwargs):
        pytest.fail("atomic_replace_text called after serialization failure")

    for module in (state, capture, visual_evidence, frontend_map):
        monkeypatch.setattr(module, "atomic_replace_text", unexpected_write)

    calls = (
        lambda: state._save_json(payload, "bad.json", "bad_"),
        lambda: capture._atomic_write_json(tmp_path / "capture.json", payload),
        lambda: visual_evidence._atomic_write_json(tmp_path / "visual.json", payload),
        lambda: frontend_map._atomic_write_json(tmp_path / "map.json", payload),
    )
    for call in calls:
        with pytest.raises(TypeError, match="not JSON serializable"):
            call()

    assert not (tmp_path / ".uidetox").exists()
    assert list(tmp_path.iterdir()) == []


def test_intent_journal_uses_shared_atomic_writer() -> None:
    assert not hasattr(intent_journal, "_atomic_replace_text")
    assert intent_journal.atomic_replace_text is atomic_replace_text
