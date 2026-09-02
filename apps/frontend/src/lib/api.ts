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
