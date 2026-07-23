from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("NEXUSFLOW_DB_PATH", "data/nexusflow.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect() -> sqlite3.Connection:
    """Open an isolated request-safe connection with a bounded lock wait."""
    connection = sqlite3.connect(DB_PATH, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _ensure_activity_foreign_key(connection: sqlite3.Connection) -> None:
    foreign_keys = connection.execute("PRAGMA foreign_key_list(activity)").fetchall()
    if any(
        foreign_key["table"] == "projects"
        and foreign_key["from"] == "project_id"
        and foreign_key["on_delete"] == "CASCADE"
        for foreign_key in foreign_keys
    ):
        return

    connection.execute("ALTER TABLE activity RENAME TO activity_without_foreign_key")
    connection.execute(
        """
        CREATE TABLE activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO activity (id, project_id, actor, action, detail, created_at)
        SELECT
            activity.id,
            CASE
                WHEN activity.project_id IS NULL OR projects.id IS NOT NULL
                THEN activity.project_id
                ELSE NULL
            END,
            activity.actor,
            activity.action,
            activity.detail,
            activity.created_at
        FROM activity_without_foreign_key AS activity
        LEFT JOIN projects ON projects.id = activity.project_id
        """
    )
    connection.execute("DROP TABLE activity_without_foreign_key")


def init_database() -> None:
    connection = connect()
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
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
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

        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_name TEXT NOT NULL,
            trigger_kind TEXT NOT NULL,
            cron_expression TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_run_at TEXT,
            destination_url TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT NOT NULL,
            customer_label TEXT NOT NULL,
            amount_due TEXT NOT NULL,
            payment_state TEXT NOT NULL,
            issued_on TEXT NOT NULL,
            due_on TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_body TEXT NOT NULL,
            severity_code TEXT NOT NULL,
            is_seen INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            legal_name TEXT NOT NULL,
            arr_text TEXT NOT NULL,
            lifecycle_stage TEXT NOT NULL,
            health_code TEXT NOT NULL,
            owner_ref TEXT NOT NULL,
            primary_contact_email TEXT NOT NULL,
            notes_blob TEXT NOT NULL,
            last_touch_date TEXT
        );

        CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connector_label TEXT NOT NULL,
            provider_key TEXT NOT NULL,
            sync_state TEXT NOT NULL,
            row_estimate TEXT NOT NULL,
            last_success_at TEXT,
            credential_hint TEXT NOT NULL,
            destination_table TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approval_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_title TEXT NOT NULL,
            request_kind TEXT NOT NULL,
            decision_state TEXT NOT NULL,
            requestor_ref TEXT NOT NULL,
            reviewer_refs TEXT NOT NULL,
            risk_band TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            context_blob TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS journey_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journey_label TEXT NOT NULL,
            entry_event TEXT NOT NULL,
            step_count_text TEXT NOT NULL,
            active_flag INTEGER NOT NULL DEFAULT 0,
            audience_query TEXT NOT NULL,
            last_published_at TEXT,
            owner_email TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS experiments (
            experiment_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            rollout_percent INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            audience_json TEXT NOT NULL
        );
        """
    )
    _ensure_activity_foreign_key(connection)
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
    if connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO workflows
                (workflow_name, trigger_kind, cron_expression, is_active, last_run_at, destination_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "Synchronize all customer lifecycle events into the unified intelligence warehouse",
                    "schedule",
                    "*/15 * * * *",
                    1,
                    "2026-07-21T13:42:00Z",
                    "https://warehouse.internal.example.com/import/nexusflow/customer-events",
                ),
                (
                    "Generate magical weekly executive digest",
                    "schedule",
                    "0 5 * * MON",
                    1,
                    "2026-07-20T05:03:11Z",
                    "mailto:leadership-everyone-and-contractors@example.com",
                ),
                (
                    "Post celebration confetti whenever revenue changes",
                    "webhook",
                    "event:invoice.updated",
                    0,
                    None,
                    "https://hooks.example.com/extremely-long-and-poorly-managed-revenue-celebration-channel",
                ),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO invoices
                (invoice_number, customer_label, amount_due, payment_state, issued_on, due_on)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("NF-2026-000000184", "Acme Global Transformation Holdings", "12890.40", "awaiting_wire", "2026-07-01", "2026-07-31"),
                ("NF-2026-000000183", "Northstar Innovation Partnership", "4200", "settled", "2026-06-01", "2026-06-30"),
                ("NF-2026-000000182", "Example Customer With An Impossibly Long Procurement Department Name", "999.99", "disputed_by_customer", "2026-05-01", "2026-05-31"),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO notifications (message_body, severity_code, is_seen, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("Your workspace is approaching an unspecified limit. Upgrade immediately to continue innovating without interruption.", "urgent-purple", 0, "2026-07-21T14:03:00Z"),
                ("The customer lifecycle automation completed with 14 warnings that are not available in this view.", "warning", 0, "2026-07-21T12:11:00Z"),
                ("Jane mentioned everyone in Website Redesign: please review the newest thirty-seven attachments before standup.", "social", 1, "2026-07-20T22:48:00Z"),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO accounts
                (legal_name, arr_text, lifecycle_stage, health_code, owner_ref, primary_contact_email, notes_blob, last_touch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "Acme Global Transformation Holdings and Associated Operating Companies",
                    "$128,900.00 annual recurring maybe",
                    "expansion_candidate",
                    "greenish-92",
                    "usr_001_Jane_Doe",
                    "procurement-digital-transformation-office@example.com",
                    "Customer is excited about strategic alignment but has fourteen unresolved security questionnaires and an unclear renewal committee.",
                    "2026-07-21",
                ),
                (
                    "Northstar Innovation Partnership",
                    "42000",
                    "onboarding_forever",
                    "amber-but-optimistic",
                    "john.smith",
                    "primary.person@example.com",
                    "Implementation kickoff happened twice. The customer requested a consolidated success plan in a format nobody owns.",
                    "2026-06-30",
                ),
                (
                    "Example Customer With An Impossibly Long Procurement Department Name",
                    "USD 999.99 MRR converted later",
                    "at_risk_probably",
                    "critical-purple",
                    "42",
                    "a.very.long.shared.mailbox.address.for.buyers@example.com",
                    "Payment is disputed, product usage is unmapped, and the executive sponsor appears in three systems under different identifiers.",
                    None,
                ),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO data_sources
                (connector_label, provider_key, sync_state, row_estimate, last_success_at, credential_hint, destination_table)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Enterprise CRM Production Primary", "sf_prod_us_4", "mostly_healthy", "1.2M-ish", "2026-07-22T03:14:00Z", "oauth:user-who-left@example.com", "raw_salesforce_account_everything"),
                ("Marketing Events and Behavioral Intent Lake", "segment_legacy", "backfill_blocked", "unknown over 9m", "2026-07-16T11:08:00Z", "write-key ending 7A2", "events_unified_final_v8"),
                ("Billing Provider Plus Manual Finance Upload", "stripe-and-csv", "warning_47", "88,004", "2026-07-21T23:59:59Z", "two credentials combined", "finance_customer_revenue_current"),
                ("Customer Success Spreadsheet maintained by everybody", "google_sheet", "connected_no_owner", "about 600", None, "shared link", "success_plan_import_temp"),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM approval_requests").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO approval_requests
                (request_title, request_kind, decision_state, requestor_ref, reviewer_refs, risk_band, submitted_at, context_blob)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "Allow the revenue intelligence copilot to automatically email every stalled enterprise opportunity",
                    "AI_AGENT_EXTERNAL_ACTION",
                    "WAITING_ON_SOMEONE",
                    "usr_jane_001",
                    '["legal-team", "security_person_7", "revops-all"]',
                    "elevated-87-percent",
                    "2026-07-22T08:04:00Z",
                    "The request includes a draft prompt, a disconnected privacy review, and a link to an expired experiment nobody can open.",
                ),
                (
                    "Export complete customer conversation history for quarterly strategic alignment workshop",
                    "DATA_EXPORT_BULK",
                    "needs_context",
                    "john.smith@example.com",
                    '["compliance", "usr_001_Jane_Doe"]',
                    "medium-ish",
                    "2026-07-21T18:31:00Z",
                    "Contains unclassified notes from support, sales, onboarding, and a spreadsheet import marked temporary in 2024.",
                ),
                (
                    "Publish generative success-plan journey to all customers without a renewal date",
                    "JOURNEY_PUBLISH",
                    "APPROVED_BUT_NOT_ACTIVE",
                    "42",
                    '[]',
                    "purple-critical",
                    "2026-07-20T12:00:00Z",
                    "Reviewer list was lost during migration. The customer audience query currently includes trial, churned, and internal demo records.",
                ),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM journey_definitions").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO journey_definitions
                (journey_label, entry_event, step_count_text, active_flag, audience_query, last_published_at, owner_email)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "Magical white-glove onboarding acceleration experience for every segment",
                    "account.created OR spreadsheet.row_added",
                    "7 steps plus two hidden",
                    1,
                    "lifecycle_stage != 'not_onboarding' AND health_code LIKE '%green%' OR 1=1",
                    "2026-07-18T05:00:00Z",
                    "customer-success-operations-and-strategy@example.com",
                ),
                (
                    "At-risk rescue, expansion discovery, and surprise executive escalation",
                    "health.score.changed",
                    "eleven",
                    0,
                    "arr > 50000 AND sentiment = maybe_negative",
                    None,
                    "jane@example.com",
                ),
                (
                    "Invoice overdue celebration and helpful payment reminder sequence",
                    "invoice.overdue",
                    "4?",
                    1,
                    "payment_state IN ('overdue','disputed_by_customer','awaiting_wire')",
                    "2026-06-30T23:59:00Z",
                    "finance-automation-owner-who-left@example.com",
                ),
            ],
        )
    if connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0:
        connection.executemany(
            """
            INSERT INTO experiments
                (experiment_key, title, description, rollout_percent, enabled, audience_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "guided-onboarding",
                    "Guided onboarding sequence",
                    "Compare a concise setup path with the current open-ended experience.",
                    50,
                    1,
                    json.dumps(["new-workspaces", "trial-admins"]),
                ),
                (
                    "weekly-summary",
                    "Weekly operations summary",
                    "Test whether a focused weekly digest improves follow-through.",
                    25,
                    0,
                    json.dumps(["workspace-owners"]),
                ),
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
    connection.close()


def rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as connection:
        return [dict(item) for item in connection.execute(sql, params).fetchall()]


def row(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as connection:
        result = connection.execute(sql, params).fetchone()
        return dict(result) if result else None


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with connect() as connection:
        cursor = connection.execute(sql, params)
        return int(cursor.lastrowid)


init_database()
