from __future__ import annotations

from pathlib import Path

from uidetox.tooling import detect_database


def _tools_by_name(root: Path):
    return {tool.name: tool for tool in detect_database(root)}


def test_detect_database_finds_nested_stdlib_sqlite_import(tmp_path: Path) -> None:
    database_module = tmp_path / "backend" / "database.py"
    database_module.parent.mkdir()
    database_module.write_text("from sqlite3 import connect\n", encoding="utf-8")

    tools = _tools_by_name(tmp_path)

    assert tools["sqlite"].config_file == "backend/database.py"


def test_detect_database_finds_python_orm_requirement(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "SQLAlchemy==2.0.41\n",
        encoding="utf-8",
    )

    tools = _tools_by_name(tmp_path)

    assert tools["sqlalchemy"].config_file == "requirements.txt"


def test_detect_database_finds_python_orm_import_without_metadata(
    tmp_path: Path,
) -> None:
    models_module = tmp_path / "service" / "models.py"
    models_module.parent.mkdir()
    models_module.write_text(
        "from sqlalchemy.orm import DeclarativeBase\n",
        encoding="utf-8",
    )

    tools = _tools_by_name(tmp_path)

    assert tools["sqlalchemy"].config_file == "service/models.py"


def test_detect_database_ignores_comments_and_skipped_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "notes.py").write_text("# import sqlite3\n", encoding="utf-8")
    vendored_module = tmp_path / ".venv" / "lib" / "database.py"
    vendored_module.parent.mkdir(parents=True)
    vendored_module.write_text("import sqlite3\n", encoding="utf-8")

    assert "sqlite" not in _tools_by_name(tmp_path)


def test_detect_database_preserves_prisma_detection(tmp_path: Path) -> None:
    schema = tmp_path / "prisma" / "schema.prisma"
    schema.parent.mkdir()
    schema.write_text(
        'datasource db { provider = "sqlite" }\n',
        encoding="utf-8",
    )

    assert "prisma" in _tools_by_name(tmp_path)
