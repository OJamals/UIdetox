from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["NEXUSFLOW_DB_PATH"] = str(
    Path(tempfile.mkdtemp(prefix="nexusflow-tests-")) / "test.db"
)

from fastapi.testclient import TestClient

from backend.app import app

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

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_metrics_activity_and_settings() -> None:
    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["teamVelocity"] == 127

    assert client.get("/api/activity").status_code == 200
    settings = client.get("/api/settings").json()
    settings["workspace_name"] = "Beta Workspace"
    saved = client.put("/api/settings", json=settings)
    assert saved.status_code == 200
    assert saved.json()["workspace_name"] == "Beta Workspace"


def test_team_contract_and_deliberate_method_mismatch() -> None:
    invited = client.post(
        "/api/team/invite",
        json={"email": "beta.tester@example.com", "role": "Viewer"},
    )
    assert invited.status_code == 201
    member_id = invited.json()["id"]

    updated = client.patch(
        f"/api/team/{member_id}",
        json={"role": "Developer"},
    )
    assert updated.status_code == 200
    assert client.delete(f"/api/team/{member_id}").status_code == 405


def test_backend_only_audit_endpoint() -> None:
    response = client.get("/api/internal/audit-log")
    assert response.status_code == 200
    assert "entries" in response.json()
