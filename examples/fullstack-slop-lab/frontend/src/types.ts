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

export type OpportunityStage =
  | "discovery"
  | "qualification"
  | "proposal"
  | "negotiation"
  | "closed-won"
  | "closed-lost";

export type Opportunity = {
  id: number;
  name: string;
  accountName: string;
  stage: OpportunityStage;
  amountCents: number;
  probability: number;
  owner: string;
  closeAt: string;
  nextStep: string;
};

export type OpportunityHistory = {
  id: number;
  action: string;
  detail: string;
  actor: string;
  createdAt: string;
};

export type OpportunityDetail = Opportunity & {
  history: OpportunityHistory[];
};

export type Forecast = {
  quarter: string;
  pipelineCents: number;
  weightedCents: number;
  commitCents: number;
  atRiskCents: number;
};

export type RevenueTarget = {
  team: string;
  targetCents: number;
  attainedCents: number;
  confidence: number;
};

export type SupportCase = {
  id: number;
  title: string;
  accountName: string;
  priority: "low" | "normal" | "high" | "urgent";
  status: "open" | "waiting" | "resolved";
  assignee: string;
  openedAt: string;
  lastReplyAt: string;
  slaMinutes: number;
};

export type SupportMessage = {
  id: number;
  author: string;
  body: string;
  channel: string;
  createdAt: string;
};

export type SupportCaseDetail = SupportCase & {
  messages: SupportMessage[];
};

export type SlaPolicy = {
  id: number;
  name: string;
  priority: string;
  firstResponseMinutes: number;
  resolutionMinutes: number;
  coverage: string;
};

export type SupportMacro = {
  id: string;
  title: string;
  bodyPreview: string;
  usageCount: number;
  owner: string;
};

export type CatalogItem = {
  id: number;
  sku: string;
  name: string;
  category: string;
  priceCents: number;
  status: "active" | "draft" | "archived";
  stockPolicy: string;
  description: string;
};

export type CatalogCategory = {
  name: string;
  itemCount: number;
  activeCount: number;
};

export type Order = {
  id: number;
  orderNo: string;
  accountName: string;
  status: "draft" | "confirmed" | "packing" | "shipped" | "delivered";
  totalCents: number;
  createdAt: string;
  promisedAt: string;
  channel: string;
};

export type OrderLine = {
  id: number;
  sku: string;
  name: string;
  quantity: number;
  unitPriceCents: number;
};

export type OrderDetail = Order & {
  lines: OrderLine[];
};

export type InventoryItem = {
  id: number;
  sku: string;
  name: string;
  location: string;
  onHand: number;
  reserved: number;
  available: number;
  reorderPoint: number;
  status: "healthy" | "low" | "stockout" | "overstock";
};

export type InventoryLocation = {
  name: string;
  itemCount: number;
  availableUnits: number;
  attentionCount: number;
};

export type Shipment = {
  id: number;
  orderNo: string;
  carrier: string;
  trackingNo: string;
  status: "label-created" | "in-transit" | "exception" | "delivered" | "held";
  etaAt: string | null;
  holdReason: string | null;
};

export type Campaign = {
  id: number;
  name: string;
  channel: string;
  status: "draft" | "scheduled" | "running" | "paused" | "complete";
  audienceSize: number;
  budgetCents: number;
  owner: string;
  scheduledAt: string | null;
};

export type Segment = {
  id: number;
  name: string;
  definition: string;
  memberCount: number;
  refreshStatus: string;
  owner: string;
};

export type Attribution = {
  model: string;
  influencedPipelineCents: number;
  confidence: number;
  windowDays: number;
};

export type ContentAsset = {
  id: number;
  title: string;
  kind: string;
  status: "draft" | "review" | "published" | "archived";
  owner: string;
  updatedAt: string;
  usageCount: number;
};

export type Survey = {
  id: number;
  title: string;
  status: "draft" | "open" | "closed";
  responseCount: number;
  completionRate: number;
  owner: string;
};

export type SurveyResult = {
  surveyId: number;
  label: string;
  count: number;
  percent: number;
};

export type AuditEvent = {
  id: number;
  actor: string;
  action: string;
  resource: string;
  detail: string;
  createdAt: string;
  ipHint: string;
};

export type FeatureFlag = {
  key: string;
  title: string;
  enabled: boolean;
  rolloutPercent: number;
  audience: string;
  owner: string;
};

export type Incident = {
  id: number;
  title: string;
  severity: "sev-1" | "sev-2" | "sev-3";
  status: "investigating" | "monitoring" | "resolved";
  affectedService: string;
  startedAt: string;
  acknowledged: boolean;
};

export type UsageMetric = {
  metric: string;
  value: number;
  limit: number;
  unit: string;
  trend: number;
};

export type MarketplaceApp = {
  id: number;
  name: string;
  category: string;
  installed: boolean;
  permissions: string[];
  description: string;
};

export type WorkItem = {
  id: number;
  title: string;
  kind: string;
  status: "unclaimed" | "claimed" | "blocked" | "done";
  owner: string | null;
  dueAt: string;
  priority: number;
  source: string;
};
