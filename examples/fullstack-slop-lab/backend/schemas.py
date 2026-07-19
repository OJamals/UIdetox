from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2)
    description: str = ""
    status: str = "planning"
    progress: int = Field(default=0, ge=0, le=100)
    budget: float = 0
    due_date: str | None = None
    owner_name: str = "Jane Doe"
    tags: list[str] = []


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    budget: float | None = None
    due_date: str | None = None


class TeamInvite(BaseModel):
    email: str
    role: str = "Viewer"


class TeamMemberUpdate(BaseModel):
    role: str


class SettingsUpdate(BaseModel):
    workspace_name: str
    weekly_digest: bool
    dark_mode: bool
    default_view: str

