from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any


def _seed_if_empty(
    connection: sqlite3.Connection,
    table: str,
    sql: str,
    values: Iterable[tuple[Any, ...]],
) -> None:
    if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0:
        connection.executemany(sql, values)


def init_extended_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_name TEXT NOT NULL,
            account_label TEXT NOT NULL,
            stage_code TEXT NOT NULL,
            amount_text TEXT NOT NULL,
            probability_percent INTEGER NOT NULL,
            owner_ref TEXT NOT NULL,
            expected_close_date TEXT NOT NULL,
            next_action_blob TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS opportunity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            action_code TEXT NOT NULL,
            detail_blob TEXT NOT NULL,
            actor_ref TEXT NOT NULL,
            happened_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS support_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_line TEXT NOT NULL,
            account_label TEXT NOT NULL,
            priority_code TEXT NOT NULL,
            state_code TEXT NOT NULL,
            assignee_ref TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            last_reply_at TEXT NOT NULL,
            sla_minutes_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES support_cases(id) ON DELETE CASCADE,
            author_ref TEXT NOT NULL,
            message_blob TEXT NOT NULL,
            source_channel TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sla_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_label TEXT NOT NULL,
            priority_code TEXT NOT NULL,
            first_response_text TEXT NOT NULL,
            resolution_text TEXT NOT NULL,
            coverage_window TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS catalog_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_code TEXT NOT NULL UNIQUE,
            display_label TEXT NOT NULL,
            category_label TEXT NOT NULL,
            price_text TEXT NOT NULL,
            state_code TEXT NOT NULL,
            inventory_policy TEXT NOT NULL,
            description_blob TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL UNIQUE,
            account_label TEXT NOT NULL,
            fulfillment_state TEXT NOT NULL,
            total_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            promised_date TEXT NOT NULL,
            channel_code TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            sku_code TEXT NOT NULL,
            item_label TEXT NOT NULL,
            quantity_text TEXT NOT NULL,
            unit_price_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_code TEXT NOT NULL,
            item_label TEXT NOT NULL,
            location_code TEXT NOT NULL,
            on_hand_text TEXT NOT NULL,
            reserved_text TEXT NOT NULL,
            reorder_point_text TEXT NOT NULL,
            stock_state TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL,
            carrier_label TEXT NOT NULL,
            tracking_reference TEXT NOT NULL,
            shipment_state TEXT NOT NULL,
            eta_at TEXT,
            hold_reason_blob TEXT
        );

        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_label TEXT NOT NULL,
            channel_code TEXT NOT NULL,
            state_code TEXT NOT NULL,
            audience_estimate TEXT NOT NULL,
            budget_text TEXT NOT NULL,
            owner_ref TEXT NOT NULL,
            scheduled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_label TEXT NOT NULL,
            definition_blob TEXT NOT NULL,
            member_estimate TEXT NOT NULL,
            refresh_state TEXT NOT NULL,
            owner_ref TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS content_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_title TEXT NOT NULL,
            asset_kind TEXT NOT NULL,
            publication_state TEXT NOT NULL,
            owner_ref TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            usage_count_text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_title TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            response_count_text TEXT NOT NULL,
            completion_rate_text TEXT NOT NULL,
            owner_ref TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_ref TEXT NOT NULL,
            action_code TEXT NOT NULL,
            resource_ref TEXT NOT NULL,
            detail_blob TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ip_hint TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS feature_flags (
            flag_key TEXT PRIMARY KEY,
            display_label TEXT NOT NULL,
            enabled_flag INTEGER NOT NULL,
            rollout_text TEXT NOT NULL,
            audience_query TEXT NOT NULL,
            owner_ref TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_title TEXT NOT NULL,
            severity_code TEXT NOT NULL,
            incident_state TEXT NOT NULL,
            service_ref TEXT NOT NULL,
            started_at TEXT NOT NULL,
            acknowledged_flag INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS marketplace_apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_label TEXT NOT NULL,
            category_code TEXT NOT NULL,
            installed_flag INTEGER NOT NULL DEFAULT 0,
            permissions_blob TEXT NOT NULL,
            description_blob TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_title TEXT NOT NULL,
            work_kind TEXT NOT NULL,
            state_code TEXT NOT NULL,
            owner_ref TEXT,
            due_at TEXT NOT NULL,
            priority_text TEXT NOT NULL,
            source_ref TEXT NOT NULL
        );
        """
    )

    _seed_if_empty(
        connection,
        "opportunities",
        """
        INSERT INTO opportunities
            (deal_name, account_label, stage_code, amount_text, probability_percent,
             owner_ref, expected_close_date, next_action_blob)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "Acme expansion and platform consolidation",
                "Acme Global Transformation Holdings",
                "qualification",
                "$248,000.00",
                62,
                "Mara Voss",
                "2026-09-28",
                "Reconcile the legal review, security workbook, and pricing exception before the executive alignment session.",
            ),
            (
                "Northstar data activation renewal",
                "Northstar Innovation Partnership",
                "proposal",
                "USD 84,500",
                71,
                "Imani Cole",
                "2026-08-19",
                "Send the revised expansion matrix after finance confirms the nonstandard ramp.",
            ),
            (
                "Example customer rescue-to-growth motion",
                "Example Customer With An Impossibly Long Procurement Department Name",
                "negotiation",
                "99000 maybe",
                38,
                "Theo Rami",
                "2026-10-31",
                "Determine whether the sponsor, procurement owner, and product champion are three people or one shared mailbox.",
            ),
        ],
    )
    _seed_if_empty(
        connection,
        "opportunity_history",
        """
        INSERT INTO opportunity_history
            (opportunity_id, action_code, detail_blob, actor_ref, happened_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "stage_changed", "Moved from discovery to qualification after a broad alignment call.", "Mara Voss", "2026-07-29T14:20:00Z"),
            (1, "note_added", "Pricing workbook contains two contradictory discount ladders.", "Finance Bot", "2026-07-30T09:11:00Z"),
            (2, "proposal_sent", "Proposal sent to an alias that forwards to eleven stakeholders.", "Imani Cole", "2026-07-28T17:42:00Z"),
            (3, "risk_detected", "Renewal and expansion opportunities may share the same external identifier.", "Theo Rami", "2026-07-30T21:08:00Z"),
        ],
    )
    _seed_if_empty(
        connection,
        "support_cases",
        """
        INSERT INTO support_cases
            (subject_line, account_label, priority_code, state_code, assignee_ref,
             opened_at, last_reply_at, sla_minutes_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Export job never finishes and the progress bar keeps celebrating", "Acme Global Transformation Holdings", "urgent-purple", "OPEN_NOW", "Unassigned", "2026-07-30T08:14:00Z", "2026-07-31T12:04:00Z", "15-ish"),
            ("Imported contacts appear twice but only in analytics", "Northstar Innovation Partnership", "highish", "waiting_customer_or_us", "Imani Cole", "2026-07-29T10:22:00Z", "2026-07-31T09:48:00Z", "60"),
            ("Invoice PDF uses last quarter's workspace name", "Example Customer With An Impossibly Long Procurement Department Name", "normal", "resolved_maybe", "Mara Voss", "2026-07-25T18:02:00Z", "2026-07-30T16:31:00Z", "240 minutes"),
        ],
    )
    _seed_if_empty(
        connection,
        "support_messages",
        """
        INSERT INTO support_messages
            (case_id, author_ref, message_blob, source_channel, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "procurement-ops@example.com", "The export has shown 99 percent for six hours. Refreshing creates another job.", "email", "2026-07-30T08:14:00Z"),
            (1, "NexusFlow Support", "We are reviewing queue ownership and worker lease evidence.", "internal-reply", "2026-07-30T08:28:00Z"),
            (1, "procurement-ops@example.com", "A third export appeared without anyone clicking the button.", "email", "2026-07-31T12:04:00Z"),
            (2, "primary.person@example.com", "Dashboard says 9,412 people while the contacts page says 4,706.", "chat", "2026-07-29T10:22:00Z"),
            (3, "a.very.long.shared.mailbox.address.for.buyers@example.com", "The legal entity in the PDF is no longer our workspace name.", "email", "2026-07-25T18:02:00Z"),
        ],
    )
    _seed_if_empty(
        connection,
        "sla_policies",
        """
        INSERT INTO sla_policies
            (policy_label, priority_code, first_response_text, resolution_text, coverage_window)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("Enterprise urgent white-glove promise", "urgent", "15", "240", "24/7 except regional holidays"),
            ("Growth plan high-priority support", "high", "60 minutes", "480", "Business hours in account timezone"),
            ("Everything else best effort", "normal", "four hours", "2880", "Monday through Friday maybe"),
        ],
    )
    _seed_if_empty(
        connection,
        "catalog_items",
        """
        INSERT INTO catalog_items
            (sku_code, display_label, category_label, price_text, state_code,
             inventory_policy, description_blob)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("NF-PLATFORM-ENT", "NexusFlow Enterprise Intelligence Platform", "Platform", "12990000", "ACTIVE_VISIBLE", "not-stocked", "Annual platform entitlement with vague unlimited language and a separately metered data layer."),
            ("NF-ONBOARD-PLUS", "White-glove transformation onboarding accelerator", "Services", "$18,500.00", "active", "capacity-managed-ish", "A six-week implementation package described as both fixed scope and fully customized."),
            ("NF-DATA-10M", "Additional ten million event processing bundle", "Usage", "420000", "DRAFT_INTERNAL", "virtual", "Event allowance that resets on a billing schedule not shown in this catalog."),
            ("NF-SUCCESS-QBR", "Executive strategic alignment and quarterly value ritual", "Services", "USD 7500", "archived-but-orderable", "manual-approval", "A premium workshop with three nearly identical deliverables and no visible cancellation policy."),
        ],
    )
    _seed_if_empty(
        connection,
        "orders",
        """
        INSERT INTO orders
            (order_number, account_label, fulfillment_state, total_text, created_at,
             promised_date, channel_code)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("NF-ORDER-2401", "Acme Global Transformation Holdings", "CONFIRMED_PENDING_EVERYTHING", "$148,400.00", "2026-07-28", "2026-08-04", "sales-assisted"),
            ("NF-ORDER-2400", "Northstar Innovation Partnership", "packing-ish", "USD 22,700", "2026-07-27", "2026-08-01", "self-serve-plus-human"),
            ("NF-ORDER-2399", "Example Customer With An Impossibly Long Procurement Department Name", "shipped", "999.99", "2026-07-21", "2026-07-25", "spreadsheet-import"),
        ],
    )
    _seed_if_empty(
        connection,
        "order_lines",
        """
        INSERT INTO order_lines
            (order_id, sku_code, item_label, quantity_text, unit_price_text)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "NF-PLATFORM-ENT", "NexusFlow Enterprise Intelligence Platform", "1", "12990000"),
            (1, "NF-ONBOARD-PLUS", "White-glove transformation onboarding accelerator", "1", "1850000"),
            (2, "NF-DATA-10M", "Additional ten million event processing bundle", "10", "420000"),
            (2, "NF-SUCCESS-QBR", "Executive strategic alignment and quarterly value ritual", "2-ish", "750000"),
            (3, "NF-SUCCESS-QBR", "Executive strategic alignment and quarterly value ritual", "1", "99999"),
        ],
    )
    _seed_if_empty(
        connection,
        "inventory_stock",
        """
        INSERT INTO inventory_stock
            (sku_code, item_label, location_code, on_hand_text, reserved_text,
             reorder_point_text, stock_state)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("NF-SECURITY-KEY", "Branded hardware security key welcome kit", "DET-A-14", "128", "44", "30", "fine"),
            ("NF-EXEC-BOX", "Executive value realization presentation box", "DET-B-02", "18 units", "17", "12", "almost-low"),
            ("NF-SWAG-M", "Magical transformation hoodie medium", "REMOTE-3PL", "0", "4", "24", "negative-available"),
            ("NF-CABLE-BUNDLE", "Universal conference room cable bundle", "DET-A-14", "902", "12", "80", "too-many"),
        ],
    )
    _seed_if_empty(
        connection,
        "shipments",
        """
        INSERT INTO shipments
            (order_number, carrier_label, tracking_reference, shipment_state,
             eta_at, hold_reason_blob)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("NF-ORDER-2401", "ParcelCo Priority Enterprise", "PC-992810000184721", "label_only", "2026-08-04", None),
            ("NF-ORDER-2400", "Northstar Regional Freight and Parcel", "NRF-VERY-LONG-0000441099", "exception_weather_but_not_weather", "2026-08-02", "Address normalized to a different campus after label purchase."),
            ("NF-ORDER-2399", "Manual Courier Upload", "spreadsheet row 48", "delivered_probably", None, None),
        ],
    )
    _seed_if_empty(
        connection,
        "campaigns",
        """
        INSERT INTO campaigns
            (campaign_label, channel_code, state_code, audience_estimate,
             budget_text, owner_ref, scheduled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Enterprise revival orchestration", "email-plus-ads-plus-sales-task", "DRAFT_NEEDS_EVERYONE", "18,400-ish", "$92,000", "Growth Council", "2026-08-11T13:00:00Z"),
            ("Magical product adoption acceleration wave", "in-app", "scheduled", "42000", "1800000", "Lifecycle Team", "2026-08-03T09:00:00Z"),
            ("Quarterly strategic alignment celebration", "all channels", "paused_for_brand", "about 6k", "USD 32,500", "Executive Programs", None),
        ],
    )
    _seed_if_empty(
        connection,
        "segments",
        """
        INSERT INTO segments
            (segment_label, definition_blob, member_estimate, refresh_state, owner_ref)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("Enterprise accounts with stalled momentum and unclear champions", "arr > 50000 AND last_touch > 30 days OR health looks concerning", "18400", "fresh-ish", "Revenue Operations"),
            ("Power users who might be admins depending on imported roles", "events_30d > 500 AND role IN ('owner','admin','workspace-admin?')", "4.7k", "refreshing forever", "Product Growth"),
            ("Customers eligible for everything except the exclusions", "not churned OR trial OR internal_demo = false", "unknown", "warning_12", "Lifecycle Team"),
        ],
    )
    _seed_if_empty(
        connection,
        "content_assets",
        """
        INSERT INTO content_assets
            (asset_title, asset_kind, publication_state, owner_ref, updated_at,
             usage_count_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("The definitive enterprise transformation readiness playbook final v12", "playbook", "review_again", "Content Council", "2026-07-31T08:00:00Z", "42 placements"),
            ("Executive value realization calculator with benchmark magic", "calculator", "PUBLISHED_GLOBAL", "Growth Engineering", "2026-07-29T12:30:00Z", "1200"),
            ("Customer story placeholder awaiting customer approval", "case-study", "draft", "Field Marketing", "2026-07-18T18:00:00Z", "used in 9 campaigns"),
        ],
    )
    _seed_if_empty(
        connection,
        "surveys",
        """
        INSERT INTO surveys
            (survey_title, lifecycle_state, response_count_text,
             completion_rate_text, owner_ref)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("How seamlessly empowered do you feel this quarter?", "OPEN_ALWAYS", "1,842", "68 percent maybe", "Customer Experience"),
            ("Implementation kickoff retrospective pulse", "draft", "0", "0", "Onboarding Operations"),
            ("Executive sponsor strategic alignment index", "closing_soon", "92", "104%", "Value Consulting"),
        ],
    )
    _seed_if_empty(
        connection,
        "audit_events",
        """
        INSERT INTO audit_events
            (actor_ref, action_code, resource_ref, detail_blob, created_at, ip_hint)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("jane@example.com", "permission.changed", "workspace:primary", "Changed export scope from selected records to all records after an approval that is not linked here.", "2026-07-31T12:01:00Z", "10.4.x.x"),
            ("system:sync-worker-legacy", "credential.rotated", "connector:sf_prod_us_4", "Rotation completed but prior owner remains visible in the data source screen.", "2026-07-31T11:46:00Z", "internal"),
            ("john@example.com", "campaign.published", "campaign:2", "Published adoption wave to a segment with an unresolved audience warning.", "2026-07-31T09:12:00Z", "172.16.x.x"),
            ("unknown-service", "export.created", "export:44819", "Created a duplicate export while the previous export held the same idempotency label.", "2026-07-30T23:59:59Z", "internal"),
            ("sarah@example.com", "flag.updated", "flag:confetti-revenue", "Set rollout to 101 percent through a retired admin screen.", "2026-07-30T20:05:00Z", "10.1.x.x"),
        ],
    )
    _seed_if_empty(
        connection,
        "feature_flags",
        """
        INSERT INTO feature_flags
            (flag_key, display_label, enabled_flag, rollout_text, audience_query, owner_ref)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("new-revenue-command-center", "New revenue command center experience", 1, "62%", "enterprise AND not_control_group", "Revenue Platform"),
            ("confetti-revenue", "Celebrate every revenue mutation", 0, "101 maybe", "everyone-including-api-users", "Growth Council"),
            ("autonomous-account-rescue", "Autonomous account rescue agent", 0, "5", "health < 40 OR sentiment unknown", "AI Governance"),
        ],
    )
    _seed_if_empty(
        connection,
        "incidents",
        """
        INSERT INTO incidents
            (incident_title, severity_code, incident_state, service_ref,
             started_at, acknowledged_flag)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("Bulk exports remain at 99 percent while duplicate jobs spawn", "SEV_ONE", "investigating_now", "exports-worker-primary-and-legacy", "2026-07-31T07:58:00Z", 0),
            ("Analytics counts differ across three customer surfaces", "sev-2", "monitoring", "metrics-aggregation-v4", "2026-07-30T18:20:00Z", 1),
            ("Marketplace install receipts delayed", "minor-purple", "resolved_maybe", "integration-install-webhook", "2026-07-29T14:00:00Z", 1),
        ],
    )
    _seed_if_empty(
        connection,
        "marketplace_apps",
        """
        INSERT INTO marketplace_apps
            (app_label, category_code, installed_flag, permissions_blob,
             description_blob)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("Enterprise Spreadsheet Super Sync", "Data and absolutely everything", 0, 'read:all,write:contacts,admin:workspace?', "Synchronize every business-critical spreadsheet through a confident one-click workflow."),
            ("Revenue Celebration Studio", "Engagement", 1, 'read:revenue,write:notifications', "Transform ordinary revenue updates into delightful multi-channel moments."),
            ("Universal AI Meeting Intelligence Connector", "AI productivity", 0, 'read:meetings,read:calendar,read:contacts,write:tasks', "Seamlessly turn every conversation into aligned, proactive, high-impact work."),
        ],
    )
    _seed_if_empty(
        connection,
        "work_items",
        """
        INSERT INTO work_items
            (work_title, work_kind, state_code, owner_ref, due_at,
             priority_text, source_ref)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Reconcile Acme pricing exception before executive alignment", "deal-task", "UNCLAIMED_NEW", None, "2026-08-01T14:00:00Z", "99", "opportunity:1"),
            ("Respond to export job duplicate report", "support-escalation", "claimed-ish", "Imani Cole", "2026-07-31T13:00:00Z", "urgent-120", "case:1"),
            ("Approve campaign audience with twelve warnings", "governance", "blocked_by_everyone", None, "2026-08-02T09:00:00Z", "82", "campaign:1"),
            ("Confirm shipment exception campus address", "fulfillment", "not_started", None, "2026-08-01T10:30:00Z", "55", "shipment:2"),
        ],
    )
