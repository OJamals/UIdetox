from __future__ import annotations

import os
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

os.environ["NEXUSFLOW_DB_PATH"] = str(
    Path(tempfile.mkdtemp(prefix="nexusflow-tests-")) / "test.db"
)

from backend import database
from backend.app import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_and_seeded_projects() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert len(response.json()) >= 4


def test_project_create_update_and_delete() -> None:
    created = client.post(
        "/api/projects",
        json={
            "name": "Beta Project",
            "description": "Created by API test",
            "budget": 12000,
            "tags": ["beta"],
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    updated = client.patch(
        f"/api/projects/{project_id}",
        json={"progress": 61, "status": "active"},
    )
    assert updated.status_code == 200
    assert updated.json()["progress"] == 61
    activity = client.get(f"/api/projects/{project_id}").json()["activity"]
    assert activity[0]["actor"] == "Northstar Operator"
    assert (
        activity[0]["detail"] == "Changed project progress to 61% and status to active"
    )

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_metrics_activity_settings_and_recommendations() -> None:
    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["teamVelocity"] == 127
    assert client.get("/api/activity").status_code == 200

    settings = client.get("/api/settings").json()
    settings["workspace_name"] = "Beta Workspace"
    settings.pop("id")
    saved = client.put("/api/settings", json=settings)
    assert saved.status_code == 200
    assert saved.json()["workspace_name"] == "Beta Workspace"

    recommendations = client.get("/api/recommendations")
    assert recommendations.status_code == 200
    assert recommendations.json()
    assert {"project_id", "title", "score"} <= set(recommendations.json()[0])


def test_team_invite_and_delete_are_persistent() -> None:
    invited = client.post(
        "/api/team/invite",
        json={"email": "beta.tester@example.com", "role": "Viewer"},
    )
    assert invited.status_code == 201
    member_id = invited.json()["id"]
    assert client.delete(f"/api/team/{member_id}").status_code == 204
    assert all(item["id"] != member_id for item in client.get("/api/team").json())


def test_workflow_contract_and_pause_action() -> None:
    response = client.get("/api/workflows")
    assert response.status_code == 200
    workflow = response.json()[0]
    assert {
        "id",
        "name",
        "trigger",
        "schedule",
        "enabled",
        "lastRun",
        "destination",
    } == set(workflow)

    paused = client.post(f"/api/workflows/{workflow['id']}/pause")
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False


def test_invoice_and_notification_contracts_and_seen_action() -> None:
    invoices = client.get("/api/billing/invoices")
    assert invoices.status_code == 200
    assert {
        "id",
        "invoiceNo",
        "accountName",
        "amountCents",
        "status",
        "createdAt",
        "dueAt",
    } == set(invoices.json()[0])

    notifications = client.get("/api/notifications")
    assert notifications.status_code == 200
    notification = notifications.json()[0]
    assert {"id", "subject", "body", "read", "createdAt", "sender"} == set(notification)

    seen = client.post(f"/api/notifications/{notification['id']}/seen")
    assert seen.status_code == 200
    assert seen.json()["read"] is True


def test_experiment_contract_and_update_action() -> None:
    experiments = client.get("/api/experiments")
    assert experiments.status_code == 200
    experiment = experiments.json()[0]
    assert {
        "key",
        "title",
        "description",
        "rolloutPercent",
        "enabled",
        "audience",
    } == set(experiment)

    experiment["enabled"] = not experiment["enabled"]
    saved = client.put(f"/api/experiments/{experiment['key']}", json=experiment)
    assert saved.status_code == 200
    assert saved.json()["enabled"] == experiment["enabled"]


def test_customer_and_data_source_contracts_and_actions() -> None:
    accounts = client.get("/api/accounts")
    assert accounts.status_code == 200
    customer = accounts.json()[0]
    assert {
        "id",
        "displayName",
        "annualRevenueCents",
        "lifecycleStage",
        "healthScore",
        "owner",
        "primaryContact",
        "notes",
        "lastTouchAt",
    } == set(customer)

    updated = client.patch(f"/api/accounts/{customer['id']}", json={"healthScore": 73})
    assert updated.status_code == 200
    assert updated.json()["healthScore"] == 73

    sources = client.get("/api/data-sources")
    assert sources.status_code == 200
    connector = sources.json()[0]
    assert {
        "id",
        "name",
        "provider",
        "status",
        "recordCount",
        "lastSyncedAt",
        "credentials",
        "destination",
    } == set(connector)

    synced = client.post(f"/api/data-sources/{connector['id']}/sync")
    assert synced.status_code == 200
    assert synced.json()["status"] == "healthy"
    assert synced.json()["lastSyncedAt"]


def test_governance_and_journey_contracts_and_actions() -> None:
    approvals = client.get("/api/governance/approvals")
    assert approvals.status_code == 200
    approval = approvals.json()[0]
    assert {
        "id",
        "title",
        "kind",
        "status",
        "requestor",
        "reviewers",
        "riskScore",
        "submittedAt",
        "context",
    } == set(approval)

    decided = client.post(
        f"/api/governance/approvals/{approval['id']}/decision",
        json={"decision": "approved"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"

    journeys = client.get("/api/journeys")
    assert journeys.status_code == 200
    journey = journeys.json()[0]
    assert {
        "id",
        "name",
        "entryTrigger",
        "stepCount",
        "active",
        "audienceSegments",
        "publishedAt",
        "owner",
    } == set(journey)

    published = client.post(f"/api/journeys/{journey['id']}/publish")
    assert published.status_code == 200
    assert published.json()["active"] is True
    assert published.json()["publishedAt"]


def test_expanded_surface_reaches_declared_full_stack_scale() -> None:
    document = client.get("/openapi.json").json()
    operation_count = sum(
        method in {"get", "post", "put", "patch", "delete"}
        for path_item in document["paths"].values()
        for method in path_item
    )
    tables = {
        item["name"]
        for item in database.rows(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }

    assert operation_count >= 60
    assert len(tables) >= 26
    assert {
        "opportunities",
        "support_cases",
        "catalog_items",
        "orders",
        "inventory_stock",
        "shipments",
        "campaigns",
        "segments",
        "content_assets",
        "surveys",
        "audit_events",
        "feature_flags",
        "incidents",
        "marketplace_apps",
        "work_items",
    } <= tables


def test_revenue_support_and_fulfillment_contracts_and_actions() -> None:
    opportunities = client.get("/api/revenue/opportunities")
    assert opportunities.status_code == 200
    opportunity = opportunities.json()[0]
    assert {
        "id",
        "name",
        "accountName",
        "stage",
        "amountCents",
        "probability",
        "owner",
        "closeAt",
        "nextStep",
    } == set(opportunity)

    detail = client.get(f"/api/revenue/opportunities/{opportunity['id']}")
    assert detail.status_code == 200
    assert detail.json()["history"]
    moved = client.patch(
        f"/api/revenue/opportunities/{opportunity['id']}",
        json={"stage": "proposal", "probability": 74},
    )
    assert moved.status_code == 200
    assert moved.json()["stage"] == "proposal"
    assert client.get("/api/revenue/forecast").status_code == 200
    assert client.get("/api/revenue/targets").status_code == 200

    cases = client.get("/api/support/cases")
    assert cases.status_code == 200
    support_case = cases.json()[0]
    case_detail = client.get(f"/api/support/cases/{support_case['id']}")
    assert case_detail.status_code == 200
    assert case_detail.json()["messages"]
    assigned = client.post(
        f"/api/support/cases/{support_case['id']}/assign",
        json={"assignee": "Mara Voss"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee"] == "Mara Voss"
    assert client.get("/api/support/sla-policies").status_code == 200
    assert client.get("/api/support/macros").status_code == 200

    items = client.get("/api/catalog/items")
    assert items.status_code == 200
    assert client.get("/api/catalog/categories").status_code == 200
    orders = client.get("/api/orders")
    assert orders.status_code == 200
    order = orders.json()[0]
    order_detail = client.get(f"/api/orders/{order['id']}")
    assert order_detail.status_code == 200
    assert order_detail.json()["lines"]
    advanced = client.post(f"/api/orders/{order['id']}/advance")
    assert advanced.status_code == 200
    assert advanced.json()["status"] != order["status"]
    assert client.get("/api/inventory").status_code == 200
    assert client.get("/api/inventory/locations").status_code == 200
    assert client.get("/api/shipments").status_code == 200


def test_growth_and_control_plane_contracts_and_actions() -> None:
    campaigns = client.get("/api/growth/campaigns")
    assert campaigns.status_code == 200
    campaign = campaigns.json()[0]
    launched = client.post(f"/api/growth/campaigns/{campaign['id']}/launch")
    assert launched.status_code == 200
    assert launched.json()["status"] == "running"

    assert client.get("/api/growth/segments").status_code == 200
    assert client.get("/api/growth/attribution").status_code == 200
    assets = client.get("/api/content/assets")
    assert assets.status_code == 200
    published = client.post(f"/api/content/assets/{assets.json()[0]['id']}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    surveys = client.get("/api/surveys")
    assert surveys.status_code == 200
    closed = client.post(f"/api/surveys/{surveys.json()[0]['id']}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    assert client.get("/api/audit/events").status_code == 200
    flags = client.get("/api/platform/feature-flags")
    assert flags.status_code == 200
    flag = flags.json()[0]
    toggled = client.put(
        f"/api/platform/feature-flags/{flag['key']}",
        json={"enabled": not flag["enabled"]},
    )
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is not flag["enabled"]
    incidents = client.get("/api/platform/incidents")
    assert incidents.status_code == 200
    acknowledged = client.post(
        f"/api/platform/incidents/{incidents.json()[0]['id']}/acknowledge"
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged"] is True
    assert client.get("/api/platform/usage").status_code == 200

    apps = client.get("/api/marketplace/apps")
    assert apps.status_code == 200
    installed = client.post(f"/api/marketplace/apps/{apps.json()[0]['id']}/install")
    assert installed.status_code == 200
    assert installed.json()["installed"] is True
    work_items = client.get("/api/work-queue")
    assert work_items.status_code == 200
    claimed = client.post(f"/api/work-queue/{work_items.json()[0]['id']}/claim")
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "claimed"


def test_invalid_action_payloads_and_missing_records_are_rejected() -> None:
    assert client.patch("/api/accounts/1", json={"healthScore": 101}).status_code == 422
    assert (
        client.post(
            "/api/governance/approvals/1/decision", json={"decision": "maybe"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/team/invite", json={"email": "not-an-email", "role": "Owner"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/projects", json={"name": "Invalid state", "status": "almost-done"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/settings",
            json={
                "workspace_name": "Beta",
                "weekly_digest": True,
                "dark_mode": False,
                "default_view": "somewhere",
            },
        ).status_code
        == 422
    )
    assert client.post("/api/workflows/99999/pause").status_code == 404
    assert client.delete("/api/team/99999").status_code == 404
    assert (
        client.patch(
            "/api/revenue/opportunities/1",
            json={"stage": "teleported", "probability": 180},
        ).status_code
        == 422
    )
    assert (
        client.post("/api/support/cases/1/assign", json={"assignee": ""}).status_code
        == 422
    )
    assert client.get("/api/orders/99999").status_code == 404
    assert client.post("/api/work-queue/99999/claim").status_code == 404


def test_request_contracts_reject_unknown_fields() -> None:
    assert (
        client.post(
            "/api/projects",
            json={"name": "Strict request", "database_only_field": True},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/settings",
            json={
                "id": 1,
                "workspace_name": "Strict workspace",
                "weekly_digest": True,
                "dark_mode": False,
                "default_view": "dashboard",
            },
        ).status_code
        == 422
    )


def test_project_activity_foreign_key_cascades_on_delete() -> None:
    foreign_keys = database.rows("PRAGMA foreign_key_list(activity)")
    assert any(
        item["table"] == "projects"
        and item["from"] == "project_id"
        and item["on_delete"] == "CASCADE"
        for item in foreign_keys
    )

    created = client.post("/api/projects", json={"name": "Cascade project"})
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert database.row("SELECT id FROM activity WHERE project_id = ?", (project_id,))

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert (
        database.row("SELECT id FROM activity WHERE project_id = ?", (project_id,))
        is None
    )


def test_activity_foreign_key_migration_preserves_valid_and_orphaned_history() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY)")
    connection.execute(
        """
        CREATE TABLE activity (
            id INTEGER PRIMARY KEY,
            project_id INTEGER,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute("INSERT INTO projects (id) VALUES (1)")
    connection.executemany(
        """
        INSERT INTO activity
            (id, project_id, actor, action, detail, created_at)
        VALUES (?, ?, 'qa', 'migrated', 'history', '2026-07-23')
        """,
        [(1, 1), (2, 999)],
    )

    database._ensure_activity_foreign_key(connection)

    migrated = connection.execute(
        "SELECT id, project_id FROM activity ORDER BY id"
    ).fetchall()
    assert [tuple(item) for item in migrated] == [(1, 1), (2, None)]
    connection.execute("DELETE FROM projects WHERE id = 1")
    assert [
        item["id"] for item in connection.execute("SELECT id FROM activity ORDER BY id")
    ] == [2]
    connection.close()


def test_openapi_exposes_closed_success_response_contracts() -> None:
    document = client.get("/openapi.json").json()
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status, response in operation["responses"].items():
                if not status.startswith("2") or status == "204":
                    continue
                schema = response["content"]["application/json"]["schema"]
                if schema.get("type") == "array":
                    schema = schema["items"]
                assert "$ref" in schema, (
                    f"{method.upper()} {path} {status} must reference an explicit "
                    "response model"
                )


def test_committed_openapi_matches_live_application_contract() -> None:
    committed = yaml.safe_load(
        (Path(__file__).parents[1] / "openapi.yaml").read_text(encoding="utf-8")
    )
    assert committed == client.get("/openapi.json").json()


def test_database_operations_use_isolated_connections_under_concurrency() -> None:
    first = database.connect()
    second = database.connect()
    try:
        assert first is not second
    finally:
        first.close()
        second.close()

    def write_and_read(index: int) -> int:
        database.execute(
            "INSERT INTO activity (project_id, actor, action, detail) VALUES (?, ?, ?, ?)",
            (None, f"qa-{index}", "verified", "concurrent connection lifecycle"),
        )
        return len(database.rows("SELECT id FROM activity"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        counts = list(pool.map(write_and_read, range(24)))

    assert min(counts) >= 1
    assert len(database.rows("SELECT id FROM activity WHERE actor LIKE 'qa-%'")) == 24
