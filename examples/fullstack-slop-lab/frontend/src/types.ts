export type Project = {
  id: number;
  name: string;
  description: string;
  status: string;
  progress: number;
  budget: number;
  due_date?: string;
  owner_name: string;
  tags: string[];
  activity?: Activity[];
};

export type Activity = {
  id: number;
  project_id?: number;
  actor: string;
  action: string;
  detail: string;
  created_at: string;
};

export type TeamMember = {
  id: number;
  name: string;
  email: string;
  role: string;
  avatar: string;
  online: number;
};

export type Metrics = {
  activeProjects: number;
  completedProjects: number;
  averageProgress: number;
  totalBudget: number;
  teamVelocity: number;
  customerHappiness: number;
};

export type WorkspaceSettings = {
  workspace_name: string;
  weekly_digest: boolean;
  dark_mode: boolean;
  default_view: string;
};

