export interface ComponentStatus {
  name: string;
  status: "healthy" | "unhealthy";
  detail?: string | null;
  latency_ms?: number | null;
}

export interface SystemStatus {
  status: "healthy" | "degraded";
  version: string;
  environment: string;
  components: ComponentStatus[];
}

export interface SystemMetrics {
  tasks_by_status: Record<string, number>;
  nodes_total: number;
  nodes_online: number;
  approvals_pending: number;
}

export interface Node {
  id: string;
  node_id: string;
  hostname?: string | null;
  label?: string | null;
  version?: string | null;
  status: string;
  online: boolean;
  capabilities?: Record<string, unknown> | null;
  hardware?: Record<string, unknown> | null;
  last_heartbeat?: string | null;
  created_at: string;
}

export interface NodeList {
  items: Node[];
  total: number;
  online: number;
}

// --- Auth token (PR 27/28 login) --------------------------------------------
// A single in-memory token, mirrored to localStorage, attached to every request.
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
  try {
    if (token) localStorage.setItem("atlas.token", token);
    else localStorage.removeItem("atlas.token");
  } catch {
    /* storage unavailable */
  }
}

export function loadAuthToken(): string | null {
  if (authToken) return authToken;
  try {
    authToken = localStorage.getItem("atlas.token");
  } catch {
    authToken = null;
  }
  return authToken;
}

export function authHeaders(): Record<string, string> {
  const t = authToken ?? loadAuthToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store", headers: { ...authHeaders() } });
  if (!res.ok) {
    throw new Error(`Request to ${path} failed with ${res.status}`);
  }
  return (await res.json()) as T;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  is_active: boolean;
}

export async function login(email: string, password: string): Promise<string> {
  const res = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(res.status === 401 ? "Invalid credentials" : `Login failed (${res.status})`);
  }
  const data = (await res.json()) as { access_token: string };
  setAuthToken(data.access_token);
  return data.access_token;
}

export const fetchMe = () => getJson<AuthUser>("/api/v1/auth/me");

export interface ClusterMember {
  id: string;
  last_seen?: string | null;
  leader: boolean;
  self: boolean;
}
export interface ClusterStatus {
  instance_id: string;
  leader: string | null;
  is_leader: boolean;
  ha_enabled: boolean;
  lease_ttl: number;
  members: ClusterMember[];
}
export const fetchCluster = () => getJson<ClusterStatus>("/api/v1/cluster");

export interface ZeroTierMember {
  id: string;
  name: string;
  authorized: boolean;
  online: boolean;
  ip_assignments: string[];
  last_seen?: number | string | null;
}
export interface ZeroTierStatus {
  controller_enabled: boolean;
  network_id: string | null;
  auto_authorize: boolean;
  members: ZeroTierMember[];
  member_count: number;
  authorized_count: number;
  error?: string | null;
}
export const fetchZeroTier = () => getJson<ZeroTierStatus>("/api/v1/zerotier/status");
export const authorizeZeroTier = (id: string, authorized: boolean) =>
  postJson<ZeroTierMember>(
    `/api/v1/zerotier/members/${encodeURIComponent(id)}/authorize`,
    { authorized },
  );

export const fetchSystemStatus = () =>
  getJson<SystemStatus>("/api/v1/system/status");

export const fetchSystemMetrics = () =>
  getJson<SystemMetrics>("/api/v1/system/metrics");

export const fetchNodes = () => getJson<NodeList>("/api/v1/nodes");

// --- Tasks / ALMA (M3 / M5) ---

export interface Task {
  id: string;
  title?: string | null;
  type: string;
  status: string;
  priority: number;
  retries: number;
  max_retries: number;
  required_capability?: string | null;
  assigned_node_id?: string | null;
  parent_task_id?: string | null;
  result?: Record<string, unknown> | null;
  created_at: string;
}

export interface TaskList {
  items: Task[];
  total: number;
}

export const fetchTasks = () => getJson<TaskList>("/api/v1/tasks");

export const fetchSubtasks = (id: string) =>
  getJson<Task[]>(`/api/v1/tasks/${id}/subtasks`);

// --- Escalation (M7) ---

export interface Escalation {
  id: string;
  subject_type: string;
  subject_id?: string | null;
  target: string;
  objective: string;
  package: string;
  correlation_id: string;
  status: string;
  response?: string | null;
  validation?: Record<string, unknown> | null;
  created_at: string;
}

export interface EscalationSummary {
  id: string;
  subject_type: string;
  target: string;
  objective: string;
  status: string;
  correlation_id: string;
  created_at: string;
}

export interface EscalationList {
  items: EscalationSummary[];
  total: number;
}

export const fetchEscalations = () =>
  getJson<EscalationList>("/api/v1/escalations");

export const fetchEscalation = (id: string) =>
  getJson<Escalation>(`/api/v1/escalations/${id}`);

export async function prepareEscalation(body: {
  objective: string;
  target: string;
  context?: Record<string, string>;
}): Promise<Escalation> {
  const res = await fetch("/api/v1/escalations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`prepare failed (${res.status})`);
  return (await res.json()) as Escalation;
}

export async function importExternalResponse(
  escalationId: string,
  response: string,
): Promise<Escalation> {
  const res = await fetch("/api/v1/external-response/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ escalation_id: escalationId, response }),
  });
  if (!res.ok) throw new Error(`import failed (${res.status})`);
  return (await res.json()) as Escalation;
}

export async function validateEscalation(
  id: string,
  approved: boolean,
): Promise<Escalation> {
  const res = await fetch(`/api/v1/escalations/${id}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, decided_by: "operator" }),
  });
  if (!res.ok) throw new Error(`validate failed (${res.status})`);
  return (await res.json()) as Escalation;
}

// --- Knowledge / RAG (M8) ---

export interface DocumentRead {
  id: string;
  kb_id?: string | null;
  title: string;
  source?: string | null;
  content_type: string;
  created_at: string;
}

export interface DocumentList {
  items: DocumentRead[];
  total: number;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source?: string | null;
  chunk_index: number;
  content: string;
  score: number;
}

export interface RagResult {
  query: string;
  hits: Citation[];
}

export const fetchDocuments = () =>
  getJson<DocumentList>("/api/v1/documents");

export async function ingestDocument(body: {
  title: string;
  content: string;
  source?: string;
}): Promise<DocumentRead> {
  const res = await fetch("/api/v1/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`ingest failed (${res.status})`);
  return (await res.json()) as DocumentRead;
}

export async function ragQuery(query: string): Promise<RagResult> {
  const res = await fetch("/api/v1/rag/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`query failed (${res.status})`);
  return (await res.json()) as RagResult;
}

// --- Maintenance / approvals (M6) ---

export interface MaintenanceRun {
  id: string;
  issue_id: string;
  status: string;
  branch?: string | null;
  analysis?: string | null;
  patch?: string | null;
  tests_summary?: string | null;
  pr_url?: string | null;
  risk?: string | null;
  attempts: number;
}

export interface MaintenanceIssue {
  id: string;
  fingerprint: string;
  title: string;
  service?: string | null;
  severity: string;
  status: string;
  occurrences: number;
  first_seen: string;
  last_seen: string;
  runs?: MaintenanceRun[];
}

export interface IssueList {
  items: MaintenanceIssue[];
  total: number;
}

export interface Approval {
  id: string;
  subject_type?: string | null;
  subject_id?: string | null;
  action: string;
  status: string;
  requested_by?: string | null;
  decided_by?: string | null;
  reason?: string | null;
}

export interface ApprovalList {
  items: Approval[];
  total: number;
}

export const fetchIssues = () =>
  getJson<IssueList>("/api/v1/maintenance/issues");

export const fetchIssue = (id: string) =>
  getJson<MaintenanceIssue>(`/api/v1/maintenance/issues/${id}`);

export const fetchApprovals = () =>
  getJson<ApprovalList>("/api/v1/approvals");

async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    // Prefer the API's own `detail` (e.g. the approval-gate message) if present.
    let detail = "";
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? "";
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `${path} failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export const analyzeIssue = (id: string) =>
  postJson<MaintenanceRun>(`/api/v1/maintenance/issues/${id}/analyze`);

export const createFix = (id: string) =>
  postJson<MaintenanceRun>(`/api/v1/maintenance/issues/${id}/create-fix`);

export const applyFix = (id: string) =>
  postJson<MaintenanceRun>(`/api/v1/maintenance/issues/${id}/apply-fix`);

export const approveApproval = (id: string) =>
  postJson<Approval>(`/api/v1/approvals/${id}/approve`, { decided_by: "operator" });

export const rejectApproval = (id: string) =>
  postJson<Approval>(`/api/v1/approvals/${id}/reject`, { decided_by: "operator" });

export async function createTask(body: {
  title: string;
  type?: string;
  objective?: string;
  payload?: Record<string, unknown>;
}): Promise<Task> {
  const res = await fetch("/api/v1/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create task failed (${res.status})`);
  return (await res.json()) as Task;
}

// --- Chat / conversations (M2) ---

export interface WebCitation {
  title: string;
  url: string;
  snippet: string;
  score: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  status?: string;
  model?: string | null;
  provider?: string | null;
  latency_ms?: number | null;
  citations?: WebCitation[] | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title?: string | null;
  mode: string;
  archived?: boolean;
  created_at: string;
  updated_at: string;
}

export interface Conversation extends ConversationSummary {
  messages: Message[];
}

export interface ConversationList {
  items: ConversationSummary[];
  total: number;
}

export interface ModelInfo {
  id: string;
  provider: string;
  name: string;
  family?: string | null;
  context_length?: number | null;
  available: boolean;
  updated_at: string;
}

export interface ModelList {
  items: ModelInfo[];
  total: number;
}

export const fetchConversations = (archived = false) =>
  getJson<ConversationList>(`/api/v1/conversations?archived=${archived}`);

export const fetchConversation = (id: string) =>
  getJson<Conversation>(`/api/v1/conversations/${id}`);

export const archiveConversation = (id: string, archived = true) =>
  postJson<ConversationSummary>(
    `/api/v1/conversations/${encodeURIComponent(id)}/archive`,
    { archived },
  );

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`/api/v1/conversations/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  if (!res.ok && res.status !== 204) {
    throw new Error(`delete failed (${res.status})`);
  }
}

export const fetchModels = () => getJson<ModelList>("/api/v1/models");

export async function refreshModels(): Promise<ModelList> {
  const res = await fetch("/api/v1/models/refresh", { method: "POST" });
  if (!res.ok) throw new Error(`refresh failed (${res.status})`);
  return (await res.json()) as ModelList;
}

export const fetchDefaultModel = () =>
  getJson<{ default_model: string }>("/api/v1/models/default");

export const setDefaultModel = (model: string) =>
  postJson<{ default_model: string }>("/api/v1/models/default", { model });

export const pullModel = (name: string) =>
  postJson<{ status: string; model: string }>("/api/v1/models/pull", { name });

export const fetchPullStatus = () =>
  getJson<{ items: Record<string, { state: string; status?: string; completed?: number; total?: number }> }>(
    "/api/v1/models/pull-status",
  );

export async function deleteModel(name: string): Promise<ModelList> {
  const res = await fetch(`/api/v1/models/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete failed (${res.status})`);
  return (await res.json()) as ModelList;
}

export const fetchHardware = () =>
  getJson<Record<string, unknown>>("/api/v1/system/hardware");

export interface ChatStreamHandlers {
  onStart?: (e: { conversation_id: string; provider: string; model: string }) => void;
  onToken?: (content: string) => void;
  onCitations?: (citations: WebCitation[], note?: string | null) => void;
  onDone?: (e: { conversation_id: string; message_id: string; latency_ms: number }) => void;
  onError?: (detail: string) => void;
}

export interface ChatStreamRequest {
  content: string;
  conversation_id?: string;
  model?: string;
  mode?: string;
  web?: boolean;
  anonymous?: boolean;
}

// --- Evals (PR 16) ---

export interface EvalSuite {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
}

export interface EvalRun {
  id: string;
  suite_id: string;
  provider?: string | null;
  model?: string | null;
  status: string;
  metrics?: Record<string, number> | null;
  is_baseline: boolean;
  created_at: string;
}

export const fetchEvalSuites = () =>
  getJson<{ items: EvalSuite[]; total: number }>("/api/v1/evals/suites");

export const createEvalSuite = (name: string, description?: string) =>
  postJson<EvalSuite>("/api/v1/evals/suites", { name, description });

export const addEvalCase = (
  suiteId: string,
  body: { input: string; expected_substrings?: string[]; forbidden_substrings?: string[] },
) => postJson<unknown>(`/api/v1/evals/suites/${encodeURIComponent(suiteId)}/cases`, body);

export const runEvalSuite = (suiteId: string, isBaseline = false) =>
  postJson<EvalRun>(`/api/v1/evals/suites/${encodeURIComponent(suiteId)}/run`, {
    is_baseline: isBaseline,
  });

export const fetchEvalRuns = (suiteId: string) =>
  getJson<{ items: EvalRun[]; total: number }>(
    `/api/v1/evals/suites/${encodeURIComponent(suiteId)}/runs`,
  );

// --- Fleet compliance & remediation (PR 24/25) ---

export interface NodeCompliance {
  node_ref: string | null;
  online: boolean;
  quarantined: boolean;
  version: string | null;
  compliant: boolean;
  issues: string[];
  diagnosis?: string | null;
  recommended_action?: string | null;
}

export interface DesiredState {
  target_version: string;
  required_capabilities: string[];
  min_online: number;
}

export interface ComplianceReport {
  summary: Record<string, number | boolean>;
  desired: DesiredState;
  nodes: NodeCompliance[];
}

export interface RemediationEvent {
  id: string;
  node_ref: string;
  action: string;
  reason?: string | null;
  automatic: boolean;
  created_at: string;
}

export const fetchCompliance = () => getJson<ComplianceReport>("/api/v1/fleet/compliance");

export const fetchDesiredState = () => getJson<DesiredState>("/api/v1/fleet/desired");

export async function setDesiredState(body: DesiredState): Promise<DesiredState> {
  const res = await fetch("/api/v1/fleet/desired", {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`save failed (${res.status})`);
  return (await res.json()) as DesiredState;
}

export const remediateNode = (node_ref: string, action: string, reason?: string) =>
  postJson<RemediationEvent>("/api/v1/fleet/remediate", { node_ref, action, reason });

export const autoRemediate = () =>
  postJson<ComplianceReport>("/api/v1/fleet/auto-remediate");

export const fetchRemediationEvents = () =>
  getJson<RemediationEvent[]>("/api/v1/fleet/remediation-events");

// --- Fleet deployments (PR 21/22) ---

export interface DeploymentTarget {
  id: string;
  node_ref: string;
  from_version?: string | null;
  wave: string;
  status: string;
  detail?: string | null;
}

export interface Deployment {
  id: string;
  target_version: string;
  previous_version?: string | null;
  strategy: string;
  canary_count: number;
  status: string;
  note?: string | null;
  created_at: string;
  updated_at: string;
  targets: DeploymentTarget[];
}

export interface DeploymentSummary {
  id: string;
  target_version: string;
  status: string;
  canary_count: number;
  created_at: string;
}

export const createDeployment = (body: {
  target_version: string;
  canary_count?: number;
  min_compatible?: string;
  note?: string;
}) => postJson<Deployment>("/api/v1/deployments", body);

export const fetchDeployments = () =>
  getJson<{ items: DeploymentSummary[]; total: number }>("/api/v1/deployments");

export const fetchDeployment = (id: string) =>
  getJson<Deployment>(`/api/v1/deployments/${encodeURIComponent(id)}`);

export const advanceDeployment = (id: string) =>
  postJson<Deployment>(`/api/v1/deployments/${encodeURIComponent(id)}/advance`);

export const reportDeployment = (
  id: string,
  body: { node_ref: string; version: string; healthy: boolean },
) => postJson<Deployment>(`/api/v1/deployments/${encodeURIComponent(id)}/report`, body);

// --- Critical Review (PR 19) ---

export interface ReviewRound {
  attempt: number;
  answer: string;
  findings: { role: string; severity: string; code: string; message: string }[];
  verification: { grounding: number | null; supported: string[]; unsupported: string[] };
  score: number;
  decision: string;
  reasons: string[];
}

export interface Review {
  id: string;
  prompt: string;
  references?: string[] | null;
  best_answer?: string | null;
  best_score: number;
  decision: string;
  rounds?: ReviewRound[] | null;
  consensus?: { best_index: number; agreement: number; rounds: number } | null;
  provider?: string | null;
  model?: string | null;
  round_count: number;
  created_at: string;
}

export interface ReviewSummary {
  id: string;
  prompt: string;
  best_score: number;
  decision: string;
  round_count: number;
  created_at: string;
}

export const runReview = (body: {
  prompt: string;
  references?: string[];
  max_rounds?: number;
  model?: string;
}) => postJson<Review>("/api/v1/reviews", body);

export const fetchReviews = () =>
  getJson<{ items: ReviewSummary[]; total: number }>("/api/v1/reviews");

export const fetchReview = (id: string) =>
  getJson<Review>(`/api/v1/reviews/${encodeURIComponent(id)}`);

// --- Users & RBAC (PR 27) ---

export interface AppUser {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface UserList {
  items: AppUser[];
  total: number;
  auth_enforced: boolean;
}

export const fetchUsers = () => getJson<UserList>("/api/v1/users");

export const createUser = (body: {
  email: string;
  password: string;
  full_name?: string;
  role?: string;
}) => postJson<AppUser>("/api/v1/users", body);

export async function updateUser(
  id: string,
  body: { role?: string; is_active?: boolean },
): Promise<AppUser> {
  const res = await fetch(`/api/v1/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? "";
    } catch {
      /* non-JSON */
    }
    throw new Error(detail || `update failed (${res.status})`);
  }
  return (await res.json()) as AppUser;
}

// --- Continuous Improvement (PR 18) ---

export interface ImprovementProposal {
  id: string;
  title: string;
  description?: string | null;
  category: string;
  suite_id?: string | null;
  baseline_model?: string | null;
  candidate_model?: string | null;
  change?: Record<string, unknown> | null;
  status: string;
  baseline_run_id?: string | null;
  candidate_run_id?: string | null;
  comparison?: { deltas?: Record<string, number | null>; verdict?: string } | null;
  recommendation?: string | null;
  created_at: string;
  updated_at: string;
}

export const fetchProposals = () =>
  getJson<{ items: ImprovementProposal[]; total: number }>(
    "/api/v1/improvements/proposals",
  );

export const createProposal = (body: {
  title: string;
  description?: string;
  category?: string;
  suite_id?: string;
  baseline_model?: string;
  candidate_model?: string;
}) => postJson<ImprovementProposal>("/api/v1/improvements/proposals", body);

export const autoPropose = () =>
  postJson<{ items: ImprovementProposal[]; total: number }>(
    "/api/v1/improvements/auto-propose",
  );

export const experimentProposal = (id: string) =>
  postJson<ImprovementProposal>(
    `/api/v1/improvements/proposals/${encodeURIComponent(id)}/experiment`,
  );

export const applyProposal = (id: string) =>
  postJson<ImprovementProposal>(
    `/api/v1/improvements/proposals/${encodeURIComponent(id)}/apply`,
  );

// --- Memory lifecycle (PR 14) ---

export interface MemoryHit {
  id: string;
  content: string;
  scope: string;
  scope_id?: string | null;
  score: number;
  source?: string | null;
  mem_type: string;
  tags?: string[] | null;
  importance: number;
  pinned: boolean;
}

export const addMemory = (body: {
  content: string;
  source?: string;
  mem_type?: string;
  tags?: string[];
  importance?: number;
  pinned?: boolean;
  ttl_seconds?: number;
}) => postJson<Record<string, unknown>>("/api/v1/memories", body);

export const searchMemories = (query: string) =>
  postJson<MemoryHit[]>("/api/v1/memories/search", { query });

export const pruneMemories = () =>
  postJson<{ pruned: number }>("/api/v1/memories/prune", {});

export interface WebSearchResponse {
  query: string;
  provider: string;
  count: number;
  citations: WebCitation[];
}

export async function webSearch(query: string): Promise<WebSearchResponse> {
  const res = await fetch("/api/v1/web/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (res.status === 403) throw new Error("web tools are disabled — enable them in Settings");
  if (!res.ok) throw new Error(`web search failed (${res.status})`);
  return (await res.json()) as WebSearchResponse;
}

// --- Environments (PR 13) ---

export interface Environment {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  status: "ACTIVE" | "ARCHIVED";
  manifest?: Record<string, unknown> | null;
  variables?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface EnvironmentSnapshot {
  id: string;
  environment_id: string;
  name?: string | null;
  stats?: Record<string, number> | null;
  created_at: string;
}

export const fetchEnvironments = () =>
  getJson<{ items: Environment[]; total: number }>("/api/v1/environments");

export const createEnvironment = (body: {
  name: string;
  description?: string;
  manifest?: Record<string, unknown>;
  variables?: Record<string, unknown>;
}) => postJson<Environment>("/api/v1/environments", body);

export async function updateEnvironment(id: string, patch: Record<string, unknown>) {
  const res = await fetch(`/api/v1/environments/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`update failed (${res.status})`);
  return (await res.json()) as Environment;
}

export const snapshotEnvironment = (id: string, name?: string) =>
  postJson<EnvironmentSnapshot>(`/api/v1/environments/${encodeURIComponent(id)}/snapshots`, {
    name,
  });

export const fetchSnapshots = (id: string) =>
  getJson<{ items: EnvironmentSnapshot[]; total: number }>(
    `/api/v1/environments/${encodeURIComponent(id)}/snapshots`,
  );

export const restoreSnapshot = (snapshotId: string) =>
  postJson<Environment>(
    `/api/v1/environments/snapshots/${encodeURIComponent(snapshotId)}/restore`,
    {},
  );

// --- Resource telemetry (PR 12) ---

export interface NodeMetric {
  id: string;
  node_id: string;
  load1?: number | null;
  ram_free_mb?: number | null;
  data?: Record<string, unknown> | null;
  created_at: string;
}

export interface OllamaPerfRow {
  provider?: string | null;
  model?: string | null;
  count: number;
  avg_latency_ms?: number | null;
  min_latency_ms?: number | null;
  max_latency_ms?: number | null;
}

export const fetchNodeMetrics = () =>
  getJson<NodeMetric[]>("/api/v1/metrics/nodes");

export const fetchOllamaPerf = () =>
  getJson<{ items: OllamaPerfRow[] }>("/api/v1/metrics/ollama");

// --- Web tools config (PR 15 settings) ---

export interface WebConfig {
  enabled: boolean;
  provider: "none" | "searxng" | "json";
  url: string;
  has_api_key: boolean;
  max_results: number;
  fetch_timeout: number;
  max_bytes: number;
  allow_private_ips: boolean;
  allowlist: string[];
  denylist: string[];
}

export const fetchWebConfig = () => getJson<WebConfig>("/api/v1/settings/web");

export async function updateWebConfig(patch: Partial<WebConfig> & { api_key?: string }) {
  const res = await fetch("/api/v1/settings/web", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`update failed (${res.status})`);
  return (await res.json()) as WebConfig;
}

// --- Node enrollment (PR 6) ---

export interface Enrollment {
  id: string;
  node_id: string;
  label?: string | null;
  status: "PENDING" | "APPROVED" | "REJECTED" | "REVOKED";
  token_prefix: string;
  created_by?: string | null;
  decided_by?: string | null;
  created_at: string;
  last_used_at?: string | null;
}

export interface EnrollmentWithToken extends Enrollment {
  token: string;
}

export interface EnrollmentList {
  items: Enrollment[];
  total: number;
}

export const fetchEnrollments = () =>
  getJson<EnrollmentList>("/api/v1/enrollments");

export const createEnrollment = (body: { node_id: string; label?: string }) =>
  postJson<EnrollmentWithToken>("/api/v1/enrollments", body);

export const approveEnrollment = (id: string) =>
  postJson<Enrollment>(`/api/v1/enrollments/${encodeURIComponent(id)}/approve`, {});

export const rejectEnrollment = (id: string) =>
  postJson<Enrollment>(`/api/v1/enrollments/${encodeURIComponent(id)}/reject`, {});

export const revokeEnrollment = (id: string) =>
  postJson<Enrollment>(`/api/v1/enrollments/${encodeURIComponent(id)}/revoke`, {});

export const rotateEnrollment = (id: string) =>
  postJson<EnrollmentWithToken>(`/api/v1/enrollments/${encodeURIComponent(id)}/rotate`, {});

// --- Query lifecycle (PR 10) ---

export interface QueryRead {
  id: string;
  conversation_id?: string | null;
  prompt: string;
  mode: string;
  model?: string | null;
  provider?: string | null;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  result?: string | null;
  error?: string | null;
  cancel_requested: boolean;
  progress: number;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface QueryEventRead {
  id: string;
  event_type: string;
  status?: string | null;
  message?: string | null;
  created_at: string;
}

export interface QueryDetail extends QueryRead {
  events: QueryEventRead[];
}

export interface QueryList {
  items: QueryRead[];
  total: number;
}

export const fetchQueries = () => getJson<QueryList>("/api/v1/queries");

export const fetchQuery = (id: string) =>
  getJson<QueryDetail>(`/api/v1/queries/${encodeURIComponent(id)}`);

export const createQuery = (body: {
  prompt: string;
  mode?: string;
  model?: string;
}) => postJson<QueryRead>("/api/v1/queries", body);

export const cancelQuery = (id: string) =>
  postJson<QueryRead>(`/api/v1/queries/${encodeURIComponent(id)}/cancel`);

// --- Conversation queue (PR 11) ---

export interface QueuedMessage {
  id: string;
  role: string;
  content: string;
  ts: number;
  merged_count?: number;
}

export interface QueueStatus {
  conversation_id: string;
  active: boolean;
  pending: number;
  items: QueuedMessage[];
  active_total: number;
}

export interface EnqueueResult {
  status: "dispatched" | "queued";
  conversation_id: string;
  pending: number;
  position?: number | null;
  message?: QueuedMessage | null;
}

export const fetchQueue = (cid: string) =>
  getJson<QueueStatus>(`/api/v1/conversations/${encodeURIComponent(cid)}/queue`);

export const enqueueMessage = (cid: string, content: string, merge = true) =>
  postJson<EnqueueResult>(
    `/api/v1/conversations/${encodeURIComponent(cid)}/messages`,
    { content, merge },
  );

export const completeTurn = (cid: string) =>
  postJson<{ conversation_id: string; next: QueuedMessage | null }>(
    `/api/v1/conversations/${encodeURIComponent(cid)}/queue/complete`,
  );

/** POST /chat/stream and dispatch Server-Sent Events to handlers. */
export async function streamChat(
  req: ChatStreamRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    handlers.onError?.(`chat request failed (${res.status})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (payload: string) => {
    let evt: Record<string, unknown>;
    try {
      evt = JSON.parse(payload);
    } catch {
      return;
    }
    switch (evt.type) {
      case "start":
        handlers.onStart?.(evt as never);
        break;
      case "token":
        handlers.onToken?.(String(evt.content ?? ""));
        break;
      case "citations":
        handlers.onCitations?.(
          (evt.citations as WebCitation[]) ?? [],
          (evt.note as string | null) ?? null,
        );
        break;
      case "done":
        handlers.onDone?.(evt as never);
        break;
      case "error":
        handlers.onError?.(String(evt.detail ?? "unknown error"));
        break;
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) dispatch(line.slice(6));
      }
    }
  }
}
