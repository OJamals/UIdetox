import type {
  Activity,
  Metrics,
  Project,
  TeamMember,
  WorkspaceSettings,
} from "../types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error("Something went wrong");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  getProjects: () => request<Project[]>("/api/projects"),
  createProject: (data: Partial<Project>) =>
    request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getProject: (projectId: string) =>
    request<Project>(`/api/projects/${projectId}`),
  updateProject: (projectId: number, data: Partial<Project>) =>
    request<Project>(`/api/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteProject: (projectId: number) =>
    request<void>(`/api/projects/${projectId}`, { method: "DELETE" }),
  getMetrics: () => request<Metrics>("/api/metrics"),
  getActivity: () => request<Activity[]>("/api/activity"),
  getTeam: () => request<TeamMember[]>("/api/team"),
  inviteTeamMember: (email: string, role: string) =>
    request<TeamMember>("/api/team/invite", {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),
  // Deliberate method mismatch against backend PATCH.
  removeTeamMember: (memberId: number) =>
    request<void>(`/api/team/${memberId}`, { method: "DELETE" }),
  getSettings: () => request<WorkspaceSettings>("/api/settings"),
  saveSettings: (settings: WorkspaceSettings) =>
    request<WorkspaceSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  // Deliberate frontend-only route.
  getRecommendations: () =>
    request<Array<{ title: string; score: number }>>("/api/recommendations"),
};
