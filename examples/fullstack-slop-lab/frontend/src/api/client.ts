import type {
  Experiment,
  OpportunityStage,
  ProjectCreateInput,
  ProjectUpdateInput,
  WorkspaceSettingsInput,
} from "../types";
import {
  arrayOf,
  isActivity,
  isApprovalRequest,
  isAttribution,
  isAuditEvent,
  isAutomation,
  isCampaign,
  isCatalogCategory,
  isCatalogItem,
  isContentAsset,
  isCustomer,
  isCustomerJourney,
  isDataConnector,
  isExperiment,
  isFeatureFlag,
  isForecast,
  isIncident,
  isInventoryItem,
  isInventoryLocation,
  isInvoice,
  isMarketplaceApp,
  isMetrics,
  isNotification,
  isOpportunity,
  isOpportunityDetail,
  isOrder,
  isOrderDetail,
  isProject,
  isRecommendation,
  isRevenueTarget,
  isSegment,
  isShipment,
  isSlaPolicy,
  isSupportCase,
  isSupportCaseDetail,
  isSupportMacro,
  isSurvey,
  isSurveyResult,
  isTeamMember,
  isUsageMetric,
  isWorkItem,
  isWorkspaceSettings,
  type JsonGuard,
} from "./contracts";

async function request(
  path: string,
  guard: null,
  options?: RequestInit,
): Promise<void>;
async function request<T>(
  path: string,
  guard: JsonGuard<T>,
  options?: RequestInit,
): Promise<T>;
async function request<T>(
  path: string,
  guard: JsonGuard<T> | null,
  options?: RequestInit,
): Promise<T | void> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    const detail = payload?.detail || response.statusText || "Request failed";
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) {
    return;
  }
  const payload: unknown = await response.json();
  if (!guard || !guard(payload)) {
    throw new Error(`Response contract mismatch for ${path}`);
  }
  return payload;
}

export const api = {
  getProjects: () => request("/api/projects", arrayOf(isProject)),
  createProject: (data: ProjectCreateInput) =>
    request("/api/projects", isProject, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getProject: (projectId: string) =>
    request(`/api/projects/${projectId}`, isProject),
  updateProject: (projectId: number, data: ProjectUpdateInput) =>
    request(`/api/projects/${projectId}`, isProject, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteProject: (projectId: number) =>
    request(`/api/projects/${projectId}`, null, { method: "DELETE" }),
  getMetrics: () => request("/api/metrics", isMetrics),
  getActivity: () => request("/api/activity", arrayOf(isActivity)),
  getTeam: () => request("/api/team", arrayOf(isTeamMember)),
  inviteTeamMember: (email: string, role: string) =>
    request("/api/team/invite", isTeamMember, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),
  removeTeamMember: (memberId: number) =>
    request(`/api/team/${memberId}`, null, { method: "DELETE" }),
  getSettings: () => request("/api/settings", isWorkspaceSettings),
  saveSettings: (settings: WorkspaceSettingsInput) =>
    request("/api/settings", isWorkspaceSettings, {
      method: "PUT",
      body: JSON.stringify({
        workspace_name: settings.workspace_name,
        weekly_digest: settings.weekly_digest,
        dark_mode: settings.dark_mode,
        default_view: settings.default_view,
      }),
    }),
  getRecommendations: () =>
    request("/api/recommendations", arrayOf(isRecommendation)),
  getAutomations: () => request("/api/workflows", arrayOf(isAutomation)),
  pauseAutomation: (automationId: number) =>
    request(`/api/workflows/${automationId}/pause`, isAutomation, {
      method: "POST",
    }),
  getInvoices: () => request("/api/billing/invoices", arrayOf(isInvoice)),
  getNotifications: () => request("/api/notifications", arrayOf(isNotification)),
  markNotificationRead: (notificationId: number) =>
    request(`/api/notifications/${notificationId}/seen`, isNotification, {
      method: "POST",
    }),
  getExperiments: () => request("/api/experiments", arrayOf(isExperiment)),
  saveExperiment: (experiment: Experiment) =>
    request(`/api/experiments/${experiment.key}`, isExperiment, {
      method: "PUT",
      body: JSON.stringify(experiment),
    }),
  getCustomers: () => request("/api/accounts", arrayOf(isCustomer)),
  updateCustomerHealth: (customerId: number, healthScore: number) =>
    request(`/api/accounts/${customerId}`, isCustomer, {
      method: "PATCH",
      body: JSON.stringify({ healthScore }),
    }),
  getDataConnectors: () => request("/api/data-sources", arrayOf(isDataConnector)),
  syncConnector: (connectorId: number) =>
    request(`/api/data-sources/${connectorId}/sync`, isDataConnector, {
      method: "POST",
    }),
  getApprovalRequests: () =>
    request("/api/governance/approvals", arrayOf(isApprovalRequest)),
  decideApproval: (approvalId: number, decision: string) =>
    request(`/api/governance/approvals/${approvalId}/decision`, isApprovalRequest, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  getJourneys: () => request("/api/journeys", arrayOf(isCustomerJourney)),
  activateJourney: (journeyId: number) =>
    request(`/api/journeys/${journeyId}/publish`, isCustomerJourney, {
      method: "POST",
    }),
  getOpportunities: () =>
    request("/api/revenue/opportunities", arrayOf(isOpportunity)),
  getOpportunity: (opportunityId: string) =>
    request(`/api/revenue/opportunities/${opportunityId}`, isOpportunityDetail),
  updateOpportunity: (
    opportunityId: number,
    stage: OpportunityStage,
    probability: number,
  ) =>
    request(`/api/revenue/opportunities/${opportunityId}`, isOpportunity, {
      method: "PATCH",
      body: JSON.stringify({ stage, probability }),
    }),
  getForecast: () => request("/api/revenue/forecast", isForecast),
  getRevenueTargets: () =>
    request("/api/revenue/targets", arrayOf(isRevenueTarget)),
  getSupportCases: () =>
    request("/api/support/cases", arrayOf(isSupportCase)),
  getSupportCase: (caseId: string) =>
    request(`/api/support/cases/${caseId}`, isSupportCaseDetail),
  assignSupportCase: (caseId: number, assignee: string) =>
    request(`/api/support/cases/${caseId}/assign`, isSupportCase, {
      method: "POST",
      body: JSON.stringify({ assignee }),
    }),
  closeSupportCase: (caseId: number) =>
    request(`/api/support/cases/${caseId}/close`, isSupportCase, {
      method: "POST",
    }),
  getSlaPolicies: () =>
    request("/api/support/sla-policies", arrayOf(isSlaPolicy)),
  getSupportMacros: () =>
    request("/api/support/macros", arrayOf(isSupportMacro)),
  getCatalogItems: () =>
    request("/api/catalog/items", arrayOf(isCatalogItem)),
  getCatalogCategories: () =>
    request("/api/catalog/categories", arrayOf(isCatalogCategory)),
  archiveCatalogItem: (itemId: number) =>
    request(`/api/catalog/items/${itemId}/archive`, isCatalogItem, {
      method: "POST",
    }),
  getOrders: () => request("/api/orders", arrayOf(isOrder)),
  getOrder: (orderId: string) =>
    request(`/api/orders/${orderId}`, isOrderDetail),
  advanceOrder: (orderId: number) =>
    request(`/api/orders/${orderId}/advance`, isOrder, { method: "POST" }),
  getInventory: () => request("/api/inventory", arrayOf(isInventoryItem)),
  getInventoryLocations: () =>
    request("/api/inventory/locations", arrayOf(isInventoryLocation)),
  recountInventory: (stockId: number) =>
    request(`/api/inventory/${stockId}/recount`, isInventoryItem, {
      method: "POST",
    }),
  getShipments: () => request("/api/shipments", arrayOf(isShipment)),
  holdShipment: (shipmentId: number) =>
    request(`/api/shipments/${shipmentId}/hold`, isShipment, {
      method: "POST",
    }),
  getCampaigns: () =>
    request("/api/growth/campaigns", arrayOf(isCampaign)),
  launchCampaign: (campaignId: number) =>
    request(`/api/growth/campaigns/${campaignId}/launch`, isCampaign, {
      method: "POST",
    }),
  pauseCampaign: (campaignId: number) =>
    request(`/api/growth/campaigns/${campaignId}/pause`, isCampaign, {
      method: "POST",
    }),
  getSegments: () => request("/api/growth/segments", arrayOf(isSegment)),
  getAttribution: () =>
    request("/api/growth/attribution", arrayOf(isAttribution)),
  getContentAssets: () =>
    request("/api/content/assets", arrayOf(isContentAsset)),
  publishContentAsset: (assetId: number) =>
    request(`/api/content/assets/${assetId}/publish`, isContentAsset, {
      method: "POST",
    }),
  getSurveys: () => request("/api/surveys", arrayOf(isSurvey)),
  closeSurvey: (surveyId: number) =>
    request(`/api/surveys/${surveyId}/close`, isSurvey, { method: "POST" }),
  getSurveyResults: (surveyId: number) =>
    request(`/api/surveys/${surveyId}/results`, arrayOf(isSurveyResult)),
  getAuditEvents: () => request("/api/audit/events", arrayOf(isAuditEvent)),
  getAuditEvent: (eventId: number) =>
    request(`/api/audit/events/${eventId}`, isAuditEvent),
  getFeatureFlags: () =>
    request("/api/platform/feature-flags", arrayOf(isFeatureFlag)),
  updateFeatureFlag: (flagKey: string, enabled: boolean) =>
    request(`/api/platform/feature-flags/${flagKey}`, isFeatureFlag, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  getIncidents: () =>
    request("/api/platform/incidents", arrayOf(isIncident)),
  acknowledgeIncident: (incidentId: number) =>
    request(
      `/api/platform/incidents/${incidentId}/acknowledge`,
      isIncident,
      { method: "POST" },
    ),
  resolveIncident: (incidentId: number) =>
    request(`/api/platform/incidents/${incidentId}/resolve`, isIncident, {
      method: "POST",
    }),
  getPlatformUsage: () =>
    request("/api/platform/usage", arrayOf(isUsageMetric)),
  getMarketplaceApps: () =>
    request("/api/marketplace/apps", arrayOf(isMarketplaceApp)),
  installMarketplaceApp: (appId: number) =>
    request(`/api/marketplace/apps/${appId}/install`, isMarketplaceApp, {
      method: "POST",
    }),
  getWorkQueue: () => request("/api/work-queue", arrayOf(isWorkItem)),
  claimWorkItem: (workItemId: number) =>
    request(`/api/work-queue/${workItemId}/claim`, isWorkItem, {
      method: "POST",
    }),
  completeWorkItem: (workItemId: number) =>
    request(`/api/work-queue/${workItemId}/complete`, isWorkItem, {
      method: "POST",
    }),
};
