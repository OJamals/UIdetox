import type {
  Experiment,
  ProjectCreateInput,
  ProjectUpdateInput,
  WorkspaceSettingsInput,
} from "../types";
import {
  arrayOf,
  isActivity,
  isApprovalRequest,
  isAutomation,
  isCustomer,
  isCustomerJourney,
  isDataConnector,
  isExperiment,
  isInvoice,
  isMetrics,
  isNotification,
  isProject,
  isRecommendation,
  isTeamMember,
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
};
