"""Regenerate the committed OpenAPI contract from the FastAPI application."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="nexusflow-openapi-") as temporary:
        os.environ["NEXUSFLOW_DB_PATH"] = str(Path(temporary) / "openapi.db")
        from backend.app import app

        output = yaml.safe_dump(
            app.openapi(),
            allow_unicode=True,
            sort_keys=False,
        )
    (ROOT / "openapi.yaml").write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
