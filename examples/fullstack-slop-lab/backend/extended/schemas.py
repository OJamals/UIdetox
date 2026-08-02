from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas import StrictRequestModel

OpportunityStage = Literal[
    "discovery", "qualification", "proposal", "negotiation", "closed-won", "closed-lost"
]


class OpportunityUpdate(StrictRequestModel):
    stage: OpportunityStage
    probability: int = Field(ge=0, le=100)


class OpportunityResponse(BaseModel):
    id: int
    name: str
    accountName: str
    stage: OpportunityStage
    amountCents: int
    probability: int
    owner: str
    closeAt: str
    nextStep: str


class OpportunityHistoryResponse(BaseModel):
    id: int
    action: str
    detail: str
    actor: str
    createdAt: str


class OpportunityDetailResponse(OpportunityResponse):
    history: list[OpportunityHistoryResponse]


class ForecastResponse(BaseModel):
    quarter: str
    pipelineCents: int
    weightedCents: int
    commitCents: int
    atRiskCents: int


class RevenueTargetResponse(BaseModel):
    team: str
    targetCents: int
    attainedCents: int
    confidence: int


class SupportAssignment(StrictRequestModel):
    assignee: str = Field(min_length=2, max_length=80)


class SupportCaseResponse(BaseModel):
    id: int
    title: str
    accountName: str
    priority: Literal["low", "normal", "high", "urgent"]
    status: Literal["open", "waiting", "resolved"]
    assignee: str
    openedAt: str
    lastReplyAt: str
    slaMinutes: int


class SupportMessageResponse(BaseModel):
    id: int
    author: str
    body: str
    channel: str
    createdAt: str


class SupportCaseDetailResponse(SupportCaseResponse):
    messages: list[SupportMessageResponse]


class SlaPolicyResponse(BaseModel):
    id: int
    name: str
    priority: str
    firstResponseMinutes: int
    resolutionMinutes: int
    coverage: str


class SupportMacroResponse(BaseModel):
    id: str
    title: str
    bodyPreview: str
    usageCount: int
    owner: str


class CatalogItemResponse(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    priceCents: int
    status: Literal["active", "draft", "archived"]
    stockPolicy: str
    description: str


class CatalogCategoryResponse(BaseModel):
    name: str
    itemCount: int
    activeCount: int


class OrderResponse(BaseModel):
    id: int
    orderNo: str
    accountName: str
    status: Literal["draft", "confirmed", "packing", "shipped", "delivered"]
    totalCents: int
    createdAt: str
    promisedAt: str
    channel: str


class OrderLineResponse(BaseModel):
    id: int
    sku: str
    name: str
    quantity: int
    unitPriceCents: int


class OrderDetailResponse(OrderResponse):
    lines: list[OrderLineResponse]


class InventoryItemResponse(BaseModel):
    id: int
    sku: str
    name: str
    location: str
    onHand: int
    reserved: int
    available: int
    reorderPoint: int
    status: Literal["healthy", "low", "stockout", "overstock"]


class InventoryLocationResponse(BaseModel):
    name: str
    itemCount: int
    availableUnits: int
    attentionCount: int


class ShipmentResponse(BaseModel):
    id: int
    orderNo: str
    carrier: str
    trackingNo: str
    status: Literal["label-created", "in-transit", "exception", "delivered", "held"]
    etaAt: str | None
    holdReason: str | None


class CampaignResponse(BaseModel):
    id: int
    name: str
    channel: str
    status: Literal["draft", "scheduled", "running", "paused", "complete"]
    audienceSize: int
    budgetCents: int
    owner: str
    scheduledAt: str | None


class SegmentResponse(BaseModel):
    id: int
    name: str
    definition: str
    memberCount: int
    refreshStatus: str
    owner: str


class AttributionResponse(BaseModel):
    model: str
    influencedPipelineCents: int
    confidence: int
    windowDays: int


class ContentAssetResponse(BaseModel):
    id: int
    title: str
    kind: str
    status: Literal["draft", "review", "published", "archived"]
    owner: str
    updatedAt: str
    usageCount: int


class SurveyResponse(BaseModel):
    id: int
    title: str
    status: Literal["draft", "open", "closed"]
    responseCount: int
    completionRate: int
    owner: str


class SurveyResultResponse(BaseModel):
    surveyId: int
    label: str
    count: int
    percent: int


class AuditEventResponse(BaseModel):
    id: int
    actor: str
    action: str
    resource: str
    detail: str
    createdAt: str
    ipHint: str


class FeatureFlagUpdate(StrictRequestModel):
    enabled: bool


class FeatureFlagResponse(BaseModel):
    key: str
    title: str
    enabled: bool
    rolloutPercent: int
    audience: str
    owner: str


class IncidentResponse(BaseModel):
    id: int
    title: str
    severity: Literal["sev-1", "sev-2", "sev-3"]
    status: Literal["investigating", "monitoring", "resolved"]
    affectedService: str
    startedAt: str
    acknowledged: bool


class UsageMetricResponse(BaseModel):
    metric: str
    value: int
    limit: int
    unit: str
    trend: int


class MarketplaceAppResponse(BaseModel):
    id: int
    name: str
    category: str
    installed: bool
    permissions: list[str]
    description: str


class WorkItemResponse(BaseModel):
    id: int
    title: str
    kind: str
    status: Literal["unclaimed", "claimed", "blocked", "done"]
    owner: str | None
    dueAt: str
    priority: int
    source: str
