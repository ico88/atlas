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

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model?: string | null;
  provider?: string | null;
  latency_ms?: number | null;
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
  onDone?: (e: { conversation_id: string; message_id: string; latency_ms: number }) => void;
  onError?: (detail: string) => void;
}

export interface ChatStreamRequest {
  content: string;
  conversation_id?: string;
  model?: string;
  mode?: string;
}

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
