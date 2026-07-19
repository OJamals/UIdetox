from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("NEXUSFLOW_DB_PATH", "data/nexusflow.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Intentionally poor architecture: one process-global connection shared by every route.
connection = sqlite3.connect(DB_PATH, check_same_thread=False)
connection.row_factory = sqlite3.Row
write_lock = threading.Lock()


def init_database() -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL,
            budget REAL NOT NULL,
            due_date TEXT,
            owner_name TEXT NOT NULL,
            tags TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            avatar TEXT NOT NULL,
            online INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            workspace_name TEXT NOT NULL,
            weekly_digest INTEGER NOT NULL,
            dark_mode INTEGER NOT NULL,
            default_view TEXT NOT NULL
        );
        """
    )
    if connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO projects
                (name, description, status, progress, budget, due_date, owner_name, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "Website Redesign",
                    "Transform our digital presence with a magical new experience.",
                    "active",
                    72,
                    48000,
                    "2026-08-30",
                    "Jane Doe",
                    json.dumps(["design", "growth", "urgent"]),
                ),
                (
                    "AI Content Engine",
                    "Unleash next-generation content workflows at scale.",
                    "at-risk",
                    43,
                    92000,
                    "2026-09-12",
                    "John Smith",
                    json.dumps(["ai", "platform"]),
                ),
                (
                    "Mobile Experience",
                    "Seamlessly empower customers wherever they are.",
                    "planning",
                    18,
                    65000,
                    "2026-10-01",
                    "Sarah Johnson",
                    json.dumps(["mobile", "customer"]),
                ),
                (
                    "Data Migration",
                    "Move legacy accounts into the innovative cloud platform.",
                    "completed",
                    100,
                    31000,
                    "2026-06-21",
                    "Mike Wilson",
                    json.dumps(["data", "backend"]),
                ),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM team_members").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO team_members (name, email, role, avatar, online)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("Jane Doe", "jane@example.com", "Admin", "JD", 1),
                ("John Smith", "john@example.com", "Developer", "JS", 1),
                ("Sarah Johnson", "sarah@example.com", "Designer", "SJ", 0),
                ("Mike Wilson", "mike@example.com", "Analyst", "MW", 0),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM activity").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO activity (project_id, actor, action, detail)
            VALUES (?, ?, ?, ?)
            """,
            [
                (1, "Jane Doe", "updated", "Changed project progress to 72%"),
                (2, "John Smith", "commented", "Added a note about API latency"),
                (3, "Sarah Johnson", "uploaded", "Added 12 new mobile mockups"),
                (1, "Mike Wilson", "completed", "Closed the analytics milestone"),
            ],
        )
    connection.execute(
        """
        INSERT OR IGNORE INTO settings
            (id, workspace_name, weekly_digest, dark_mode, default_view)
        VALUES (1, 'NexusFlow Labs', 1, 0, 'dashboard')
        """
    )
    connection.commit()


def rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def row(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    result = connection.execute(sql, params).fetchone()
    return dict(result) if result else None


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with write_lock:
        cursor = connection.execute(sql, params)
        connection.commit()
        return int(cursor.lastrowid)


init_database()

