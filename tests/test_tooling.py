from pathlib import Path

from uidetox.tooling import _dlx_or_local, _npx_or_local


def test_npx_or_local_prefers_local_binary(tmp_path):
    local_bin = tmp_path / "node_modules" / ".bin"
    local_bin.mkdir(parents=True)
    (local_bin / "eslint").write_text("#!/bin/sh\n", encoding="utf-8")

    assert _npx_or_local(tmp_path, "eslint --fix .") == "./node_modules/.bin/eslint --fix ."


def test_npx_or_local_uses_detected_package_manager(tmp_path):
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    assert _npx_or_local(tmp_path, "tsc --noEmit") == "pnpm exec tsc --noEmit"

    yarn_root = tmp_path / "yarn"
    yarn_root.mkdir()
    (yarn_root / "yarn.lock").write_text("# yarn lockfile\n", encoding="utf-8")
    assert _npx_or_local(yarn_root, "vite build") == "yarn vite build"

    bun_root = tmp_path / "bun"
    bun_root.mkdir()
    (bun_root / "bun.lockb").write_bytes(b"lock")
    assert _npx_or_local(bun_root, "biome check .") == "bunx biome check ."


def test_dlx_or_local_uses_scoped_package_runner(tmp_path):
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    assert (
        _dlx_or_local(tmp_path, "@redocly/cli", "redocly", "lint openapi.yaml")
        == "pnpm dlx @redocly/cli lint openapi.yaml"
    )