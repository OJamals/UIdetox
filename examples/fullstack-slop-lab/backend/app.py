from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend import database
from backend.schemas import (
    ProjectCreate,
    ProjectUpdate,
    SettingsUpdate,
    TeamInvite,
    TeamMemberUpdate,
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
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


@app.post("/api/projects", status_code=201)
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


@app.get("/api/projects/{project_id}")
def get_project(project_id: int) -> dict[str, Any]:
    project = database.row("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project["activity"] = database.rows(
        "SELECT * FROM activity WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    return project_payload(project)


@app.patch("/api/projects/{project_id}")
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


@app.get("/api/metrics")
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


@app.get("/api/activity")
def get_activity() -> list[dict[str, Any]]:
    return database.rows("SELECT * FROM activity ORDER BY created_at DESC LIMIT 12")


@app.get("/api/team")
def get_team() -> list[dict[str, Any]]:
    return database.rows("SELECT * FROM team_members ORDER BY id")


@app.post("/api/team/invite", status_code=201)
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


# Deliberate method mismatch: frontend attempts DELETE on this same route.
@app.patch("/api/team/{member_id}")
def update_team_member(member_id: int, payload: TeamMemberUpdate) -> dict[str, Any]:
    database.execute(
        "UPDATE team_members SET role = ? WHERE id = ?",
        (payload.role, member_id),
    )
    member = database.row("SELECT * FROM team_members WHERE id = ?", (member_id,))
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = database.row("SELECT * FROM settings WHERE id = 1") or {}
    settings["weekly_digest"] = bool(settings.get("weekly_digest"))
    settings["dark_mode"] = bool(settings.get("dark_mode"))
    return settings


@app.put("/api/settings")
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


# Deliberate backend-only operation for parity testing.
@app.get("/api/internal/audit-log")
def internal_audit_log() -> dict[str, Any]:
    return {"entries": database.rows("SELECT * FROM activity ORDER BY id DESC")}
