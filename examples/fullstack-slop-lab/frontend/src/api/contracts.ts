import type {
  Activity,
  ApprovalRequest,
  Automation,
  CustomerJourney,
  CustomerProfile,
  DataConnector,
  Experiment,
  Invoice,
  Metrics,
  Notification,
  Project,
  TeamMember,
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
): value is { title: string; score: number } {
  return isRecord(value) && isString(value.title) && isNumber(value.score);
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
