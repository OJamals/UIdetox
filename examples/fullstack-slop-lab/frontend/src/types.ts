export type Project = {
  id: number;
  name: string;
  description: string;
  status: ProjectStatus;
  progress: number;
  budget: number;
  due_date?: string;
  owner_name: string;
  tags: string[];
  created_at: string;
  activity?: Activity[];
};

export type ProjectStatus = "planning" | "active" | "at-risk" | "completed";

export type ProjectCreateInput = {
  name: string;
  description?: string;
  status?: ProjectStatus;
  progress?: number;
  budget?: number;
  due_date?: string | null;
  owner_name?: string;
  tags?: string[];
};

export type ProjectUpdateInput = Partial<
  Pick<Project, "name" | "description" | "status" | "progress" | "budget" | "due_date">
>;

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
  online: boolean;
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
  id: number;
  workspace_name: string;
  weekly_digest: boolean;
  dark_mode: boolean;
  default_view: "dashboard" | "projects" | "analytics";
};

export type WorkspaceSettingsInput = Omit<WorkspaceSettings, "id">;

export type Automation = {
  id: number;
  name: string;
  trigger: string;
  schedule: string;
  enabled: boolean;
  lastRun: string | null;
  destination: string;
};

export type Invoice = {
  id: number;
  invoiceNo: string;
  accountName: string;
  amountCents: number;
  status: "open" | "paid" | "overdue";
  createdAt: string;
  dueAt: string;
};

export type Notification = {
  id: number;
  subject: string;
  body: string;
  read: boolean;
  createdAt: string;
  sender: { id: string; displayName: string };
};

export type Experiment = {
  key: string;
  title: string;
  description: string;
  rolloutPercent: number;
  enabled: boolean;
  audience: string[];
};

export type CustomerProfile = {
  id: number;
  displayName: string;
  annualRevenueCents: number;
  lifecycleStage: string;
  healthScore: number;
  owner: { id: string; name: string };
  primaryContact: { name: string; email: string };
  notes: string;
  lastTouchAt: string | null;
};

export type DataConnector = {
  id: number;
  name: string;
  provider: string;
  status: "healthy" | "warning" | "failed" | "syncing";
  recordCount: number;
  lastSyncedAt: string | null;
  credentials: { mode: string; owner: string };
  destination: string;
};

export type ApprovalRequest = {
  id: number;
  title: string;
  kind: string;
  status: "pending" | "approved" | "rejected" | "needs-info";
  requestor: { id: string; name: string; department: string };
  reviewers: Array<{ id: string; name: string }>;
  riskScore: number;
  submittedAt: string;
  context: string;
};

export type CustomerJourney = {
  id: number;
  name: string;
  entryTrigger: string;
  stepCount: number;
  active: boolean;
  audienceSegments: string[];
  publishedAt: string | null;
  owner: { id: string; name: string; email: string };
};
