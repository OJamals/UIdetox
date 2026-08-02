import type {
  Activity,
  ApprovalRequest,
  Attribution,
  AuditEvent,
  Automation,
  Campaign,
  CatalogCategory,
  CatalogItem,
  ContentAsset,
  CustomerJourney,
  CustomerProfile,
  DataConnector,
  Experiment,
  FeatureFlag,
  Forecast,
  Incident,
  InventoryItem,
  InventoryLocation,
  Invoice,
  MarketplaceApp,
  Metrics,
  Notification,
  Opportunity,
  OpportunityDetail,
  OpportunityHistory,
  Order,
  OrderDetail,
  OrderLine,
  Project,
  RevenueTarget,
  Segment,
  Shipment,
  SlaPolicy,
  SupportCase,
  SupportCaseDetail,
  SupportMacro,
  SupportMessage,
  Survey,
  SurveyResult,
  TeamMember,
  UsageMetric,
  WorkItem,
  WorkspaceSettings,
} from "../types";

export type JsonGuard<T> = (value: unknown) => value is T;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

export function arrayOf<T>(guard: JsonGuard<T>): JsonGuard<T[]> {
  return (value: unknown): value is T[] =>
    Array.isArray(value) && value.every(guard);
}

export function isActivity(value: unknown): value is Activity {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    (value.project_id === null || value.project_id === undefined || isNumber(value.project_id)) &&
    isString(value.actor) &&
    isString(value.action) &&
    isString(value.detail) &&
    isString(value.created_at)
  );
}

export function isProject(value: unknown): value is Project {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.description) &&
    ["planning", "active", "at-risk", "completed"].includes(String(value.status)) &&
    isNumber(value.progress) &&
    isNumber(value.budget) &&
    (value.due_date === null || value.due_date === undefined || isString(value.due_date)) &&
    isString(value.owner_name) &&
    isStringArray(value.tags) &&
    isString(value.created_at) &&
    (value.activity === undefined || arrayOf(isActivity)(value.activity))
  );
}

export function isMetrics(value: unknown): value is Metrics {
  return (
    isRecord(value) &&
    isNumber(value.activeProjects) &&
    isNumber(value.completedProjects) &&
    isNumber(value.averageProgress) &&
    isNumber(value.totalBudget) &&
    isNumber(value.teamVelocity) &&
    isNumber(value.customerHappiness)
  );
}

export function isTeamMember(value: unknown): value is TeamMember {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.email) &&
    isString(value.role) &&
    isString(value.avatar) &&
    isBoolean(value.online)
  );
}

export function isWorkspaceSettings(value: unknown): value is WorkspaceSettings {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.workspace_name) &&
    isBoolean(value.weekly_digest) &&
    isBoolean(value.dark_mode) &&
    ["dashboard", "projects", "analytics"].includes(String(value.default_view))
  );
}

export function isRecommendation(
  value: unknown,
): value is { project_id: number; title: string; score: number } {
  return (
    isRecord(value) &&
    isNumber(value.project_id) &&
    isString(value.title) &&
    isNumber(value.score)
  );
}

export function isAutomation(value: unknown): value is Automation {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.trigger) &&
    isString(value.schedule) &&
    isBoolean(value.enabled) &&
    isNullableString(value.lastRun) &&
    isString(value.destination)
  );
}

export function isInvoice(value: unknown): value is Invoice {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.invoiceNo) &&
    isString(value.accountName) &&
    isNumber(value.amountCents) &&
    ["open", "paid", "overdue"].includes(String(value.status)) &&
    isString(value.createdAt) &&
    isString(value.dueAt)
  );
}

function isNotificationSender(
  value: unknown,
): value is Notification["sender"] {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.displayName)
  );
}

export function isNotification(value: unknown): value is Notification {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.subject) &&
    isString(value.body) &&
    isBoolean(value.read) &&
    isString(value.createdAt) &&
    isNotificationSender(value.sender)
  );
}

export function isExperiment(value: unknown): value is Experiment {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.title) &&
    isString(value.description) &&
    isNumber(value.rolloutPercent) &&
    isBoolean(value.enabled) &&
    isStringArray(value.audience)
  );
}

function isOwner(value: unknown): value is { id: string; name: string } {
  return isRecord(value) && isString(value.id) && isString(value.name);
}

function isContact(
  value: unknown,
): value is { name: string; email: string } {
  return isRecord(value) && isString(value.name) && isString(value.email);
}

export function isCustomer(value: unknown): value is CustomerProfile {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.displayName) &&
    isNumber(value.annualRevenueCents) &&
    isString(value.lifecycleStage) &&
    isNumber(value.healthScore) &&
    isOwner(value.owner) &&
    isContact(value.primaryContact) &&
    isString(value.notes) &&
    isNullableString(value.lastTouchAt)
  );
}

function isCredential(
  value: unknown,
): value is DataConnector["credentials"] {
  return (
    isRecord(value) &&
    isString(value.mode) &&
    isString(value.owner)
  );
}

export function isDataConnector(value: unknown): value is DataConnector {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.provider) &&
    ["healthy", "warning", "failed", "syncing"].includes(String(value.status)) &&
    isNumber(value.recordCount) &&
    isNullableString(value.lastSyncedAt) &&
    isCredential(value.credentials) &&
    isString(value.destination)
  );
}

function isRequestor(
  value: unknown,
): value is ApprovalRequest["requestor"] {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.name) &&
    isString(value.department)
  );
}

function isReviewer(
  value: unknown,
): value is ApprovalRequest["reviewers"][number] {
  return isOwner(value);
}

export function isApprovalRequest(value: unknown): value is ApprovalRequest {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.kind) &&
    ["pending", "approved", "rejected", "needs-info"].includes(String(value.status)) &&
    isRequestor(value.requestor) &&
    arrayOf(isReviewer)(value.reviewers) &&
    isNumber(value.riskScore) &&
    isString(value.submittedAt) &&
    isString(value.context)
  );
}

function isJourneyOwner(
  value: unknown,
): value is CustomerJourney["owner"] {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.name) &&
    isString(value.email)
  );
}

export function isCustomerJourney(value: unknown): value is CustomerJourney {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.entryTrigger) &&
    isNumber(value.stepCount) &&
    isBoolean(value.active) &&
    isStringArray(value.audienceSegments) &&
    isNullableString(value.publishedAt) &&
    isJourneyOwner(value.owner)
  );
}

export function isOpportunity(value: unknown): value is Opportunity {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.accountName) &&
    ["discovery", "qualification", "proposal", "negotiation", "closed-won", "closed-lost"].includes(String(value.stage)) &&
    isNumber(value.amountCents) &&
    isNumber(value.probability) &&
    isString(value.owner) &&
    isString(value.closeAt) &&
    isString(value.nextStep)
  );
}

export function isOpportunityHistory(value: unknown): value is OpportunityHistory {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.action) &&
    isString(value.detail) &&
    isString(value.actor) &&
    isString(value.createdAt)
  );
}

export function isOpportunityDetail(value: unknown): value is OpportunityDetail {
  if (!isRecord(value)) return false;
  const history = value.history;
  return isOpportunity(value) && arrayOf(isOpportunityHistory)(history);
}

export function isForecast(value: unknown): value is Forecast {
  return (
    isRecord(value) &&
    isString(value.quarter) &&
    isNumber(value.pipelineCents) &&
    isNumber(value.weightedCents) &&
    isNumber(value.commitCents) &&
    isNumber(value.atRiskCents)
  );
}

export function isRevenueTarget(value: unknown): value is RevenueTarget {
  return (
    isRecord(value) &&
    isString(value.team) &&
    isNumber(value.targetCents) &&
    isNumber(value.attainedCents) &&
    isNumber(value.confidence)
  );
}

export function isSupportCase(value: unknown): value is SupportCase {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.accountName) &&
    ["low", "normal", "high", "urgent"].includes(String(value.priority)) &&
    ["open", "waiting", "resolved"].includes(String(value.status)) &&
    isString(value.assignee) &&
    isString(value.openedAt) &&
    isString(value.lastReplyAt) &&
    isNumber(value.slaMinutes)
  );
}

export function isSupportMessage(value: unknown): value is SupportMessage {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.author) &&
    isString(value.body) &&
    isString(value.channel) &&
    isString(value.createdAt)
  );
}

export function isSupportCaseDetail(value: unknown): value is SupportCaseDetail {
  if (!isRecord(value)) return false;
  const messages = value.messages;
  return isSupportCase(value) && arrayOf(isSupportMessage)(messages);
}

export function isSlaPolicy(value: unknown): value is SlaPolicy {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.priority) &&
    isNumber(value.firstResponseMinutes) &&
    isNumber(value.resolutionMinutes) &&
    isString(value.coverage)
  );
}

export function isSupportMacro(value: unknown): value is SupportMacro {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.title) &&
    isString(value.bodyPreview) &&
    isNumber(value.usageCount) &&
    isString(value.owner)
  );
}

export function isCatalogItem(value: unknown): value is CatalogItem {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.sku) &&
    isString(value.name) &&
    isString(value.category) &&
    isNumber(value.priceCents) &&
    ["active", "draft", "archived"].includes(String(value.status)) &&
    isString(value.stockPolicy) &&
    isString(value.description)
  );
}

export function isCatalogCategory(value: unknown): value is CatalogCategory {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isNumber(value.itemCount) &&
    isNumber(value.activeCount)
  );
}

export function isOrder(value: unknown): value is Order {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.orderNo) &&
    isString(value.accountName) &&
    ["draft", "confirmed", "packing", "shipped", "delivered"].includes(String(value.status)) &&
    isNumber(value.totalCents) &&
    isString(value.createdAt) &&
    isString(value.promisedAt) &&
    isString(value.channel)
  );
}

export function isOrderLine(value: unknown): value is OrderLine {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.sku) &&
    isString(value.name) &&
    isNumber(value.quantity) &&
    isNumber(value.unitPriceCents)
  );
}

export function isOrderDetail(value: unknown): value is OrderDetail {
  if (!isRecord(value)) return false;
  const lines = value.lines;
  return isOrder(value) && arrayOf(isOrderLine)(lines);
}

export function isInventoryItem(value: unknown): value is InventoryItem {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.sku) &&
    isString(value.name) &&
    isString(value.location) &&
    isNumber(value.onHand) &&
    isNumber(value.reserved) &&
    isNumber(value.available) &&
    isNumber(value.reorderPoint) &&
    ["healthy", "low", "stockout", "overstock"].includes(String(value.status))
  );
}

export function isInventoryLocation(value: unknown): value is InventoryLocation {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isNumber(value.itemCount) &&
    isNumber(value.availableUnits) &&
    isNumber(value.attentionCount)
  );
}

export function isShipment(value: unknown): value is Shipment {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.orderNo) &&
    isString(value.carrier) &&
    isString(value.trackingNo) &&
    ["label-created", "in-transit", "exception", "delivered", "held"].includes(String(value.status)) &&
    isNullableString(value.etaAt) &&
    isNullableString(value.holdReason)
  );
}

export function isCampaign(value: unknown): value is Campaign {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.channel) &&
    ["draft", "scheduled", "running", "paused", "complete"].includes(String(value.status)) &&
    isNumber(value.audienceSize) &&
    isNumber(value.budgetCents) &&
    isString(value.owner) &&
    isNullableString(value.scheduledAt)
  );
}

export function isSegment(value: unknown): value is Segment {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.definition) &&
    isNumber(value.memberCount) &&
    isString(value.refreshStatus) &&
    isString(value.owner)
  );
}

export function isAttribution(value: unknown): value is Attribution {
  return (
    isRecord(value) &&
    isString(value.model) &&
    isNumber(value.influencedPipelineCents) &&
    isNumber(value.confidence) &&
    isNumber(value.windowDays)
  );
}

export function isContentAsset(value: unknown): value is ContentAsset {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.kind) &&
    ["draft", "review", "published", "archived"].includes(String(value.status)) &&
    isString(value.owner) &&
    isString(value.updatedAt) &&
    isNumber(value.usageCount)
  );
}

export function isSurvey(value: unknown): value is Survey {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.title) &&
    ["draft", "open", "closed"].includes(String(value.status)) &&
    isNumber(value.responseCount) &&
    isNumber(value.completionRate) &&
    isString(value.owner)
  );
}

export function isSurveyResult(value: unknown): value is SurveyResult {
  return (
    isRecord(value) &&
    isNumber(value.surveyId) &&
    isString(value.label) &&
    isNumber(value.count) &&
    isNumber(value.percent)
  );
}

export function isAuditEvent(value: unknown): value is AuditEvent {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.actor) &&
    isString(value.action) &&
    isString(value.resource) &&
    isString(value.detail) &&
    isString(value.createdAt) &&
    isString(value.ipHint)
  );
}

export function isFeatureFlag(value: unknown): value is FeatureFlag {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.title) &&
    isBoolean(value.enabled) &&
    isNumber(value.rolloutPercent) &&
    isString(value.audience) &&
    isString(value.owner)
  );
}

export function isIncident(value: unknown): value is Incident {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.title) &&
    ["sev-1", "sev-2", "sev-3"].includes(String(value.severity)) &&
    ["investigating", "monitoring", "resolved"].includes(String(value.status)) &&
    isString(value.affectedService) &&
    isString(value.startedAt) &&
    isBoolean(value.acknowledged)
  );
}

export function isUsageMetric(value: unknown): value is UsageMetric {
  return (
    isRecord(value) &&
    isString(value.metric) &&
    isNumber(value.value) &&
    isNumber(value.limit) &&
    isString(value.unit) &&
    isNumber(value.trend)
  );
}

export function isMarketplaceApp(value: unknown): value is MarketplaceApp {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.name) &&
    isString(value.category) &&
    isBoolean(value.installed) &&
    isStringArray(value.permissions) &&
    isString(value.description)
  );
}

export function isWorkItem(value: unknown): value is WorkItem {
  return (
    isRecord(value) &&
    isNumber(value.id) &&
    isString(value.title) &&
    isString(value.kind) &&
    ["unclaimed", "claimed", "blocked", "done"].includes(String(value.status)) &&
    isNullableString(value.owner) &&
    isString(value.dueAt) &&
    isNumber(value.priority) &&
    isString(value.source)
  );
}
