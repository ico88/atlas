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

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Request to ${path} failed with ${res.status}`);
  }
  return (await res.json()) as T;
}

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
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return (await res.json()) as T;
}

export const analyzeIssue = (id: string) =>
  postJson<MaintenanceRun>(`/api/v1/maintenance/issues/${id}/analyze`);

export const createFix = (id: string) =>
  postJson<MaintenanceRun>(`/api/v1/maintenance/issues/${id}/create-fix`);

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

export const fetchConversations = () =>
  getJson<ConversationList>("/api/v1/conversations");

export const fetchConversation = (id: string) =>
  getJson<Conversation>(`/api/v1/conversations/${id}`);

export const fetchModels = () => getJson<ModelList>("/api/v1/models");

export async function refreshModels(): Promise<ModelList> {
  const res = await fetch("/api/v1/models/refresh", { method: "POST" });
  if (!res.ok) throw new Error(`refresh failed (${res.status})`);
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
}

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
    headers: { "Content-Type": "application/json" },
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
