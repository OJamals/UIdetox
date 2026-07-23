from __future__ import annotations

import json
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend import database
from backend.schemas import (
    AccountHealthUpdate,
    ActivityResponse,
    ApprovalResponse,
    AutomationResponse,
    CustomerResponse,
    DataSourceResponse,
    DecisionUpdate,
    ExperimentResponse,
    ExperimentUpdate,
    HealthResponse,
    InvoiceResponse,
    JourneyResponse,
    MetricsResponse,
    NotificationResponse,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
    RecommendationResponse,
    SettingsUpdate,
    TeamInvite,
    TeamMemberResponse,
    WorkspaceSettingsResponse,
)

app = FastAPI(
    title="NexusFlow AI API",
    description="Intentionally awkward beta fixture for UIdetox.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def project_payload(project: dict[str, Any]) -> dict[str, Any]:
    project["tags"] = json.loads(project.get("tags") or "[]")
    return project


def workflow_payload(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": workflow["id"],
        "name": workflow["workflow_name"],
        "trigger": workflow["trigger_kind"],
        "schedule": workflow["cron_expression"],
        "enabled": bool(workflow["is_active"]),
        "lastRun": workflow["last_run_at"],
        "destination": workflow["destination_url"],
    }


def invoice_payload(invoice: dict[str, Any]) -> dict[str, Any]:
    status = {
        "settled": "paid",
        "awaiting_wire": "open",
        "disputed_by_customer": "overdue",
    }.get(invoice["payment_state"], "open")
    return {
        "id": invoice["id"],
        "invoiceNo": invoice["invoice_number"],
        "accountName": invoice["customer_label"],
        "amountCents": round(float(invoice["amount_due"]) * 100),
        "status": status,
        "createdAt": invoice["issued_on"],
        "dueAt": invoice["due_on"],
    }


def notification_payload(notification: dict[str, Any]) -> dict[str, Any]:
    subject = {
        "urgent-purple": "Workspace limit warning",
        "warning": "Automation completed with warnings",
        "social": "Team mention",
    }.get(notification["severity_code"], "Workspace update")
    return {
        "id": notification["id"],
        "subject": subject,
        "body": notification["message_body"],
        "read": bool(notification["is_seen"]),
        "createdAt": notification["sent_at"],
        "sender": {"id": "nexusflow-system", "displayName": "NexusFlow"},
    }


def _numeric_text(value: str) -> float:
    match = re.search(r"[\d,.]+", value)
    return float(match.group(0).replace(",", "")) if match else 0


def account_payload(account: dict[str, Any]) -> dict[str, Any]:
    revenue = _numeric_text(account["arr_text"])
    if "MRR" in account["arr_text"].upper():
        revenue *= 12
    health_match = re.search(r"\d+", account["health_code"])
    health = int(health_match.group(0)) if health_match else {
        "amber-but-optimistic": 58,
        "critical-purple": 22,
    }.get(account["health_code"], 50)
    owner_name = account["owner_ref"].replace("usr_001_", "").replace("_", " ")
    return {
        "id": account["id"],
        "displayName": account["legal_name"],
        "annualRevenueCents": round(revenue * 100),
        "lifecycleStage": account["lifecycle_stage"],
        "healthScore": health,
        "owner": {"id": account["owner_ref"], "name": owner_name.title()},
        "primaryContact": {
            "name": account["primary_contact_email"].split("@")[0].replace(".", " ").title(),
            "email": account["primary_contact_email"],
        },
        "notes": account["notes_blob"],
        "lastTouchAt": account["last_touch_date"],
    }


def data_source_payload(source: dict[str, Any]) -> dict[str, Any]:
    raw_count = source["row_estimate"].lower().replace(",", "")
    count = _numeric_text(raw_count)
    if "m" in raw_count:
        count *= 1_000_000
    status = "healthy"
    if "blocked" in source["sync_state"]:
        status = "failed"
    elif "warning" in source["sync_state"]:
        status = "warning"
    elif source["sync_state"] == "syncing":
        status = "syncing"
    return {
        "id": source["id"],
        "name": source["connector_label"],
        "provider": source["provider_key"],
        "status": status,
        "recordCount": round(count),
        "lastSyncedAt": source["last_success_at"],
        "credentials": {"mode": source["credential_hint"], "owner": "workspace"},
        "destination": source["destination_table"],
    }


def approval_payload(approval: dict[str, Any]) -> dict[str, Any]:
    status = {
        "WAITING_ON_SOMEONE": "pending",
        "needs_context": "needs-info",
        "APPROVED_BUT_NOT_ACTIVE": "approved",
    }.get(approval["decision_state"], approval["decision_state"].lower())
    reviewer_refs = json.loads(approval["reviewer_refs"])
    risk_match = re.search(r"\d+", approval["risk_band"])
    return {
        "id": approval["id"],
        "title": approval["request_title"],
        "kind": approval["request_kind"].replace("_", " ").title(),
        "status": status,
        "requestor": {
            "id": approval["requestor_ref"],
            "name": approval["requestor_ref"].replace("usr_", "").replace("_", " ").title(),
            "department": "Operations",
        },
        "reviewers": [
            {"id": reviewer, "name": reviewer.replace("-", " ").title()}
            for reviewer in reviewer_refs
        ],
        "riskScore": int(risk_match.group(0)) if risk_match else 50,
        "submittedAt": approval["submitted_at"],
        "context": approval["context_blob"],
    }


def journey_payload(journey: dict[str, Any]) -> dict[str, Any]:
    step_match = re.search(r"\d+", journey["step_count_text"])
    step_count = int(step_match.group(0)) if step_match else {"eleven": 11}.get(
        journey["step_count_text"].lower(), 0
    )
    owner_email = journey["owner_email"]
    return {
        "id": journey["id"],
        "name": journey["journey_label"],
        "entryTrigger": journey["entry_event"],
        "stepCount": step_count,
        "active": bool(journey["active_flag"]),
        "audienceSegments": [journey["audience_query"]],
        "publishedAt": journey["last_published_at"],
        "owner": {
            "id": owner_email,
            "name": owner_email.split("@")[0].replace("-", " ").title(),
            "email": owner_email,
        },
    }


def experiment_payload(experiment: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": experiment["experiment_key"],
        "title": experiment["title"],
        "description": experiment["description"],
        "rolloutPercent": experiment["rollout_percent"],
        "enabled": bool(experiment["enabled"]),
        "audience": json.loads(experiment["audience_json"]),
    }


@app.get("/health", response_model=HealthResponse)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects", response_model=list[ProjectResponse])
def list_projects(
    status: str | None = None, search: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM projects WHERE 1 = 1"
    params: list[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if search:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    sql += " ORDER BY created_at DESC"
    return [project_payload(project) for project in database.rows(sql, tuple(params))]


@app.post("/api/projects", status_code=201, response_model=ProjectResponse)
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    project_id = database.execute(
        """
        INSERT INTO projects
            (name, description, status, progress, budget, due_date, owner_name, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name,
            payload.description,
            payload.status,
            payload.progress,
            payload.budget,
            payload.due_date,
            payload.owner_name,
            json.dumps(payload.tags),
        ),
    )
    database.execute(
        "INSERT INTO activity (project_id, actor, action, detail) VALUES (?, ?, ?, ?)",
        (project_id, payload.owner_name, "created", f"Created {payload.name}"),
    )
    return get_project(project_id)


@app.get("/api/projects/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: int) -> dict[str, Any]:
    project = database.row("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project["activity"] = database.rows(
        "SELECT * FROM activity WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    return project_payload(project)


@app.patch("/api/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: int, payload: ProjectUpdate) -> dict[str, Any]:
    existing = get_project(project_id)
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return existing
    fields = ", ".join(f"{field} = ?" for field in updates)
    database.execute(
        f"UPDATE projects SET {fields} WHERE id = ?",
        (*updates.values(), project_id),
    )
    database.execute(
        "INSERT INTO activity (project_id, actor, action, detail) VALUES (?, ?, ?, ?)",
        (project_id, "Jane Doe", "updated", f"Updated {', '.join(updates)}"),
    )
    return get_project(project_id)


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: int) -> None:
    get_project(project_id)
    database.execute("DELETE FROM projects WHERE id = ?", (project_id,))


@app.get("/api/metrics", response_model=MetricsResponse)
def get_metrics() -> dict[str, Any]:
    projects = database.rows("SELECT status, progress, budget FROM projects")
    total_budget = sum(project["budget"] for project in projects)
    return {
        "activeProjects": sum(project["status"] == "active" for project in projects),
        "completedProjects": sum(
            project["status"] == "completed" for project in projects
        ),
        "averageProgress": round(
            sum(project["progress"] for project in projects) / max(len(projects), 1)
        ),
        "totalBudget": total_budget,
        "teamVelocity": 127,
        "customerHappiness": 98,
    }


@app.get("/api/activity", response_model=list[ActivityResponse])
def get_activity() -> list[dict[str, Any]]:
    return database.rows("SELECT * FROM activity ORDER BY created_at DESC LIMIT 12")


@app.get("/api/team", response_model=list[TeamMemberResponse])
def get_team() -> list[dict[str, Any]]:
    return database.rows("SELECT * FROM team_members ORDER BY id")


@app.post("/api/team/invite", status_code=201, response_model=TeamMemberResponse)
def invite_team_member(payload: TeamInvite) -> dict[str, Any]:
    name = payload.email.split("@")[0].replace(".", " ").title()
    try:
        member_id = database.execute(
            """
            INSERT INTO team_members (name, email, role, avatar, online)
            VALUES (?, ?, ?, ?, 0)
            """,
            (name, payload.email, payload.role, name[:2].upper()),
        )
    except Exception as error:
        raise HTTPException(status_code=409, detail="Something went wrong") from error
    return database.row("SELECT * FROM team_members WHERE id = ?", (member_id,)) or {}


@app.delete("/api/team/{member_id}", status_code=204)
def delete_team_member(member_id: int) -> None:
    member = database.row("SELECT id FROM team_members WHERE id = ?", (member_id,))
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    database.execute("DELETE FROM team_members WHERE id = ?", (member_id,))


@app.get("/api/settings", response_model=WorkspaceSettingsResponse)
def get_settings() -> dict[str, Any]:
    settings = database.row("SELECT * FROM settings WHERE id = 1") or {}
    settings["weekly_digest"] = bool(settings.get("weekly_digest"))
    settings["dark_mode"] = bool(settings.get("dark_mode"))
    return settings


@app.put("/api/settings", response_model=WorkspaceSettingsResponse)
def save_settings(payload: SettingsUpdate) -> dict[str, Any]:
    database.execute(
        """
        UPDATE settings
        SET workspace_name = ?, weekly_digest = ?, dark_mode = ?, default_view = ?
        WHERE id = 1
        """,
        (
            payload.workspace_name,
            int(payload.weekly_digest),
            int(payload.dark_mode),
            payload.default_view,
        ),
    )
    return get_settings()


@app.get("/api/recommendations", response_model=list[RecommendationResponse])
def list_recommendations() -> list[dict[str, Any]]:
    projects = database.rows(
        "SELECT name, progress FROM projects WHERE status != 'completed' ORDER BY progress"
    )
    return [
        {"title": f"Review {project['name']}", "score": max(0, 100 - project["progress"])}
        for project in projects[:3]
    ]


@app.get("/api/workflows", response_model=list[AutomationResponse])
def list_workflows() -> list[dict[str, Any]]:
    return [workflow_payload(item) for item in database.rows("SELECT * FROM workflows ORDER BY id")]


@app.post(
    "/api/workflows/{workflow_id}/pause",
    response_model=AutomationResponse,
)
def pause_workflow(workflow_id: int) -> dict[str, Any]:
    workflow = database.row("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow could not be located")
    database.execute("UPDATE workflows SET is_active = 0 WHERE id = ?", (workflow_id,))
    return workflow_payload({**workflow, "is_active": 0})


@app.get("/api/billing/invoices", response_model=list[InvoiceResponse])
def list_invoices() -> list[dict[str, Any]]:
    return [invoice_payload(item) for item in database.rows("SELECT * FROM invoices ORDER BY issued_on DESC")]


@app.get("/api/notifications", response_model=list[NotificationResponse])
def list_notifications() -> list[dict[str, Any]]:
    return [notification_payload(item) for item in database.rows("SELECT * FROM notifications ORDER BY sent_at DESC")]


@app.post(
    "/api/notifications/{notification_id}/seen",
    response_model=NotificationResponse,
)
def mark_notification_seen(notification_id: int) -> dict[str, Any]:
    notification = database.row(
        "SELECT * FROM notifications WHERE id = ?", (notification_id,)
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    database.execute("UPDATE notifications SET is_seen = 1 WHERE id = ?", (notification_id,))
    return notification_payload({**notification, "is_seen": 1})


@app.get("/api/experiments", response_model=list[ExperimentResponse])
def list_experiments() -> list[dict[str, Any]]:
    return [experiment_payload(item) for item in database.rows("SELECT * FROM experiments ORDER BY experiment_key")]


@app.put(
    "/api/experiments/{experiment_key}",
    response_model=ExperimentResponse,
)
def save_experiment(experiment_key: str, payload: ExperimentUpdate) -> dict[str, Any]:
    if experiment_key != payload.key:
        raise HTTPException(status_code=409, detail="Experiment key does not match the route")
    database.execute(
        """
        INSERT INTO experiments (experiment_key, title, description, rollout_percent, enabled, audience_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(experiment_key) DO UPDATE SET
          title = excluded.title,
          description = excluded.description,
          rollout_percent = excluded.rollout_percent,
          enabled = excluded.enabled,
          audience_json = excluded.audience_json
        """,
        (
            payload.key,
            payload.title,
            payload.description,
            payload.rolloutPercent,
            int(payload.enabled),
            json.dumps(payload.audience),
        ),
    )
    experiment = database.row("SELECT * FROM experiments WHERE experiment_key = ?", (experiment_key,))
    return experiment_payload(experiment or {})


@app.get("/api/accounts", response_model=list[CustomerResponse])
def list_accounts() -> list[dict[str, Any]]:
    return [account_payload(item) for item in database.rows("SELECT * FROM accounts ORDER BY legal_name")]


@app.patch(
    "/api/accounts/{account_id}",
    response_model=CustomerResponse,
)
def update_account_health(account_id: int, payload: AccountHealthUpdate) -> dict[str, Any]:
    account = database.row("SELECT * FROM accounts WHERE id = ?", (account_id,))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    database.execute(
        "UPDATE accounts SET health_code = ? WHERE id = ?",
        (f"score-{payload.healthScore}", account_id),
    )
    return account_payload({**account, "health_code": f"score-{payload.healthScore}"})


@app.get("/api/data-sources", response_model=list[DataSourceResponse])
def list_data_sources() -> list[dict[str, Any]]:
    return [data_source_payload(item) for item in database.rows("SELECT * FROM data_sources ORDER BY connector_label")]


@app.post(
    "/api/data-sources/{source_id}/sync",
    response_model=DataSourceResponse,
)
def sync_data_source(source_id: int) -> dict[str, Any]:
    source = database.row("SELECT * FROM data_sources WHERE id = ?", (source_id,))
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    database.execute(
        "UPDATE data_sources SET sync_state = 'mostly_healthy', last_success_at = CURRENT_TIMESTAMP WHERE id = ?",
        (source_id,),
    )
    updated = database.row("SELECT * FROM data_sources WHERE id = ?", (source_id,))
    return data_source_payload(updated or {})


@app.get(
    "/api/governance/approvals",
    response_model=list[ApprovalResponse],
)
def list_governance_approvals() -> list[dict[str, Any]]:
    return [
        approval_payload(item)
        for item in database.rows("SELECT * FROM approval_requests ORDER BY submitted_at DESC")
    ]


@app.post(
    "/api/governance/approvals/{approval_id}/decision",
    response_model=ApprovalResponse,
)
def decide_governance_approval(
    approval_id: int, payload: DecisionUpdate
) -> dict[str, Any]:
    approval = database.row(
        "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
    )
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    database.execute(
        "UPDATE approval_requests SET decision_state = ? WHERE id = ?",
        (payload.decision, approval_id),
    )
    return approval_payload({**approval, "decision_state": payload.decision})


@app.get("/api/journeys", response_model=list[JourneyResponse])
def list_journeys() -> list[dict[str, Any]]:
    return [journey_payload(item) for item in database.rows("SELECT * FROM journey_definitions ORDER BY id")]


@app.post(
    "/api/journeys/{journey_id}/publish",
    response_model=JourneyResponse,
)
def publish_journey(journey_id: int) -> dict[str, Any]:
    journey = database.row(
        "SELECT * FROM journey_definitions WHERE id = ?", (journey_id,)
    )
    if not journey:
        raise HTTPException(status_code=404, detail="Journey not found")
    database.execute(
        "UPDATE journey_definitions SET active_flag = 1, last_published_at = CURRENT_TIMESTAMP WHERE id = ?",
        (journey_id,),
    )
    updated = database.row("SELECT * FROM journey_definitions WHERE id = ?", (journey_id,))
    return journey_payload(updated or {})
