from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProjectStatus = Literal["planning", "active", "at-risk", "completed"]
WorkspaceRole = Literal["Viewer", "Developer"]
WorkspaceView = Literal["dashboard", "projects", "analytics"]


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(StrictRequestModel):
    name: str = Field(min_length=2)
    description: str = ""
    status: ProjectStatus = "planning"
    progress: int = Field(default=0, ge=0, le=100)
    budget: float = Field(default=0, ge=0)
    due_date: str | None = None
    owner_name: str = "Jane Doe"
    tags: list[str] = Field(default_factory=list)


class ProjectUpdate(StrictRequestModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    budget: float | None = Field(default=None, ge=0)
    due_date: str | None = None


class TeamInvite(StrictRequestModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: WorkspaceRole = "Viewer"


class SettingsUpdate(StrictRequestModel):
    workspace_name: str
    weekly_digest: bool
    dark_mode: bool
    default_view: WorkspaceView


class DecisionUpdate(StrictRequestModel):
    decision: Literal["approved", "rejected", "needs-info"]


class AccountHealthUpdate(StrictRequestModel):
    healthScore: int = Field(ge=0, le=100)


class ExperimentUpdate(StrictRequestModel):
    key: str = Field(min_length=2)
    title: str = Field(min_length=2)
    description: str
    rolloutPercent: int = Field(ge=0, le=100)
    enabled: bool
    audience: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ActivityResponse(BaseModel):
    id: int
    project_id: int | None
    actor: str
    action: str
    detail: str
    created_at: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    status: ProjectStatus
    progress: int
    budget: float
    due_date: str | None
    owner_name: str
    tags: list[str]
    created_at: str


class ProjectDetailResponse(ProjectResponse):
    activity: list[ActivityResponse]


class TeamMemberResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    avatar: str
    online: bool


class MetricsResponse(BaseModel):
    activeProjects: int
    completedProjects: int
    averageProgress: int
    totalBudget: float
    teamVelocity: int
    customerHappiness: int


class WorkspaceSettingsResponse(SettingsUpdate):
    id: int


class RecommendationResponse(BaseModel):
    title: str
    score: int


class AutomationResponse(BaseModel):
    id: int
    name: str
    trigger: str
    schedule: str
    enabled: bool
    lastRun: str | None
    destination: str


class InvoiceResponse(BaseModel):
    id: int
    invoiceNo: str
    accountName: str
    amountCents: int
    status: Literal["open", "paid", "overdue"]
    createdAt: str
    dueAt: str


class NotificationSenderResponse(BaseModel):
    id: str
    displayName: str


class NotificationResponse(BaseModel):
    id: int
    subject: str
    body: str
    read: bool
    createdAt: str
    sender: NotificationSenderResponse


class ExperimentResponse(ExperimentUpdate):
    pass


class OwnerResponse(BaseModel):
    id: str
    name: str


class ContactResponse(BaseModel):
    name: str
    email: str


class CustomerResponse(BaseModel):
    id: int
    displayName: str
    annualRevenueCents: int
    lifecycleStage: str
    healthScore: int
    owner: OwnerResponse
    primaryContact: ContactResponse
    notes: str
    lastTouchAt: str | None


class CredentialResponse(BaseModel):
    mode: str
    owner: str


class DataSourceResponse(BaseModel):
    id: int
    name: str
    provider: str
    status: Literal["healthy", "warning", "failed", "syncing"]
    recordCount: int
    lastSyncedAt: str | None
    credentials: CredentialResponse
    destination: str


class RequestorResponse(OwnerResponse):
    department: str


class ReviewerResponse(OwnerResponse):
    pass


class ApprovalResponse(BaseModel):
    id: int
    title: str
    kind: str
    status: Literal["pending", "approved", "rejected", "needs-info"]
    requestor: RequestorResponse
    reviewers: list[ReviewerResponse]
    riskScore: int
    submittedAt: str
    context: str


class JourneyOwnerResponse(OwnerResponse):
    email: str


class JourneyResponse(BaseModel):
    id: int
    name: str
    entryTrigger: str
    stepCount: int
    active: bool
    audienceSegments: list[str]
    publishedAt: str | None
    owner: JourneyOwnerResponse
