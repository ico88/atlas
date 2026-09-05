"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ModelAlias,
  ModelDeployment,
  RoutingPolicy,
  Runtime,
  RuntimeHealth,
  benchmarkDeployment,
  createModelDeployment,
  createRuntime,
  deleteAlias,
  deleteModelDeployment,
  deletePolicy,
  deleteRuntime,
  fetchAliases,
  fetchModelDeployments,
  fetchPolicies,
  fetchRuntimeHealth,
  fetchRuntimes,
  upsertAlias,
  upsertPolicy,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const RUNTIME_TYPES = ["ollama", "llama_cpp", "vllm", "localai", "openai", "anthropic"];

function stateClass(state: string): string {
  if (state === "UP") return "ok";
  if (state === "DEGRADED") return "warn";
  return "bad";
}

export default function RuntimesPage() {
  const { t } = useI18n();
  const [runtimes, setRuntimes] = useState<Runtime[]>([]);
  const [health, setHealth] = useState<Record<string, RuntimeHealth>>({});
  const [deployments, setDeployments] = useState<ModelDeployment[]>([]);
  const [aliases, setAliases] = useState<ModelAlias[]>([]);
  const [policies, setPolicies] = useState<RoutingPolicy[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Forms
  const [rt, setRt] = useState({ name: "", runtime_type: "ollama", endpoint: "" });
  const [dep, setDep] = useState({ model_key: "", runtime_id: "", runtime_model_name: "", priority: "100", load_policy: "ON_DEMAND" });
  const [alias, setAlias] = useState({ alias: "", targets: "" });
  const [pol, setPol] = useState({ task_type: "", capabilities: "", preferred_alias: "", privacy: "LOCAL_PREFERRED", fallback: "" });

  const load = useCallback(async () => {
    try {
      const [r, d, a, p] = await Promise.all([
        fetchRuntimes(),
        fetchModelDeployments(),
        fetchAliases(),
        fetchPolicies(),
      ]);
      setRuntimes(r.items);
      setDeployments(d.items);
      setAliases(a.items);
      setPolicies(p.items);
      setError(null);
      try {
        const h = await fetchRuntimeHealth();
        setHealth(Object.fromEntries(h.map((x) => [x.id, x])));
      } catch {
        /* health probe is best-effort */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "action failed");
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.runtimes")}</h1>
      <p className="page-subtitle">{t("runtimes.subtitle")}</p>
      {error && <p className="error">{error}</p>}

      {/* Runtimes */}
      <h2 className="page-title" style={{ fontSize: 20, marginTop: 20 }}>
        {t("runtimes.runtimes")}
      </h2>
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={rt.name}
            placeholder={t("runtimes.name")}
            onChange={(e) => setRt({ ...rt, name: e.target.value })}
            style={{ flex: "1 1 160px" }}
          />
          <select
            value={rt.runtime_type}
            onChange={(e) => setRt({ ...rt, runtime_type: e.target.value })}
          >
            {RUNTIME_TYPES.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
          <input
            value={rt.endpoint}
            placeholder="endpoint (http://host:port)"
            onChange={(e) => setRt({ ...rt, endpoint: e.target.value })}
            style={{ flex: "1 1 220px" }}
          />
          <button
            className="btn"
            disabled={!rt.name.trim()}
            onClick={() =>
              act(async () => {
                await createRuntime({
                  name: rt.name.trim(),
                  runtime_type: rt.runtime_type,
                  endpoint: rt.endpoint.trim() || undefined,
                });
                setRt({ name: "", runtime_type: "ollama", endpoint: "" });
              })
            }
          >
            {t("runtimes.add")}
          </button>
        </div>
      </div>
      <div className="cards">
        {runtimes.map((r) => {
          const h = health[r.id];
          return (
            <div className="card" key={r.id}>
              <div className="status-row">
                <strong>{r.name}</strong>
                <span className="badge">
                  <span className={`dot ${h ? stateClass(h.state) : "bad"}`} />
                  {h ? h.state : r.status}
                </span>
              </div>
              <div className="status-row">
                <span className="muted">{t("runtimes.type")}</span>
                <span className="pill">{r.runtime_type}</span>
              </div>
              <div className="status-row">
                <span className="muted">Endpoint</span>
                <span>{r.endpoint || "—"}</span>
              </div>
              <div className="status-row">
                <span className="muted">Node</span>
                <span>{r.node_id || "control-plane"}</span>
              </div>
              {h?.circuit === "OPEN" && (
                <div className="status-row">
                  <span className="muted">Circuit</span>
                  <span className="queue-badge idle">OPEN</span>
                </div>
              )}
              {h?.detail && <p className="muted" style={{ fontSize: 12 }}>{h.detail}</p>}
              <button
                className="btn secondary"
                style={{ marginTop: 8 }}
                onClick={() => act(() => deleteRuntime(r.id))}
              >
                {t("common.delete")}
              </button>
            </div>
          );
        })}
        {runtimes.length === 0 && <p className="muted">{t("runtimes.none")}</p>}
      </div>

      {/* Deployments */}
      <h2 className="page-title" style={{ fontSize: 20, marginTop: 24 }}>
        {t("runtimes.deployments")}
      </h2>
      <p className="page-subtitle">{t("runtimes.deployments.help")}</p>
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={dep.model_key}
            placeholder="model_key (es. qwen-8b)"
            onChange={(e) => setDep({ ...dep, model_key: e.target.value })}
            style={{ flex: "1 1 150px" }}
          />
          <select value={dep.runtime_id} onChange={(e) => setDep({ ...dep, runtime_id: e.target.value })}>
            <option value="">runtime…</option>
            {runtimes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <input
            value={dep.runtime_model_name}
            placeholder="runtime model name"
            onChange={(e) => setDep({ ...dep, runtime_model_name: e.target.value })}
            style={{ flex: "1 1 160px" }}
          />
          <input
            value={dep.priority}
            placeholder="priority"
            style={{ width: 90 }}
            onChange={(e) => setDep({ ...dep, priority: e.target.value })}
          />
          <select
            value={dep.load_policy}
            onChange={(e) => setDep({ ...dep, load_policy: e.target.value })}
          >
            <option>ON_DEMAND</option>
            <option>ALWAYS_LOADED</option>
            <option>PINNED</option>
            <option>AUTO_UNLOAD</option>
          </select>
          <button
            className="btn"
            disabled={!dep.model_key.trim() || !dep.runtime_id || !dep.runtime_model_name.trim()}
            onClick={() =>
              act(async () => {
                await createModelDeployment({
                  model_key: dep.model_key.trim(),
                  runtime_id: dep.runtime_id,
                  runtime_model_name: dep.runtime_model_name.trim(),
                  priority: Number(dep.priority) || 100,
                  load_policy: dep.load_policy,
                });
                setDep({ model_key: "", runtime_id: "", runtime_model_name: "", priority: "100", load_policy: "ON_DEMAND" });
              })
            }
          >
            {t("runtimes.add")}
          </button>
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="data">
          <thead>
            <tr>
              <th>model_key</th>
              <th>runtime</th>
              <th>model name</th>
              <th>priority</th>
              <th>load</th>
              <th>tok/s</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {deployments.map((d) => (
              <tr key={d.id}>
                <td>{d.model_key}</td>
                <td>{runtimes.find((r) => r.id === d.runtime_id)?.name || d.runtime_id}</td>
                <td>{d.runtime_model_name}</td>
                <td>{d.priority}</td>
                <td>{d.load_policy}</td>
                <td>{d.estimated_tokens_per_second ?? "—"}</td>
                <td style={{ display: "flex", gap: 6 }}>
                  <button
                    className="btn secondary"
                    onClick={() => act(() => benchmarkDeployment(d.id))}
                  >
                    {t("runtimes.benchmark")}
                  </button>
                  <button className="btn secondary" onClick={() => act(() => deleteModelDeployment(d.id))}>
                    {t("common.delete")}
                  </button>
                </td>
              </tr>
            ))}
            {deployments.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  {t("runtimes.none")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Aliases */}
      <h2 className="page-title" style={{ fontSize: 20, marginTop: 24 }}>
        {t("runtimes.aliases")}
      </h2>
      <p className="page-subtitle">{t("runtimes.aliases.help")}</p>
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={alias.alias}
            placeholder="alias (es. atlas.general)"
            onChange={(e) => setAlias({ ...alias, alias: e.target.value })}
            style={{ flex: "1 1 160px" }}
          />
          <input
            value={alias.targets}
            placeholder="model_keys, in ordine (es. qwen-8b, qwen-4b)"
            onChange={(e) => setAlias({ ...alias, targets: e.target.value })}
            style={{ flex: "1 1 260px" }}
          />
          <button
            className="btn"
            disabled={!alias.alias.trim()}
            onClick={() =>
              act(async () => {
                await upsertAlias({
                  alias: alias.alias.trim(),
                  targets: alias.targets
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setAlias({ alias: "", targets: "" });
              })
            }
          >
            {t("common.save")}
          </button>
        </div>
      </div>
      <div className="cards">
        {aliases.map((a) => (
          <div className="card" key={a.id}>
            <div className="status-row">
              <strong>{a.alias}</strong>
              <button className="btn secondary" onClick={() => act(() => deleteAlias(a.alias))}>
                {t("common.delete")}
              </button>
            </div>
            <div className="status-row">
              <span className="muted">targets</span>
              <span>{(a.targets || []).join(" → ") || "—"}</span>
            </div>
          </div>
        ))}
        {aliases.length === 0 && <p className="muted">{t("runtimes.none")}</p>}
      </div>

      {/* Routing policies (M9) */}
      <h2 className="page-title" style={{ fontSize: 20, marginTop: 24 }}>
        {t("runtimes.policies")}
      </h2>
      <p className="page-subtitle">{t("runtimes.policies.help")}</p>
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={pol.task_type}
            placeholder="task type (es. coding)"
            onChange={(e) => setPol({ ...pol, task_type: e.target.value })}
            style={{ flex: "1 1 120px" }}
          />
          <input
            value={pol.capabilities}
            placeholder="capabilities (CODING, REASONING)"
            onChange={(e) => setPol({ ...pol, capabilities: e.target.value })}
            style={{ flex: "1 1 180px" }}
          />
          <input
            value={pol.preferred_alias}
            placeholder="alias preferito"
            onChange={(e) => setPol({ ...pol, preferred_alias: e.target.value })}
            style={{ flex: "1 1 140px" }}
          />
          <select value={pol.privacy} onChange={(e) => setPol({ ...pol, privacy: e.target.value })}>
            <option>LOCAL_ONLY</option>
            <option>LOCAL_PREFERRED</option>
            <option>CLOUD_ALLOWED</option>
            <option>CLOUD_REQUIRED</option>
          </select>
          <input
            value={pol.fallback}
            placeholder="fallback alias (in ordine)"
            onChange={(e) => setPol({ ...pol, fallback: e.target.value })}
            style={{ flex: "1 1 160px" }}
          />
          <button
            className="btn"
            disabled={!pol.task_type.trim()}
            onClick={() =>
              act(async () => {
                await upsertPolicy({
                  task_type: pol.task_type.trim(),
                  required_capabilities: pol.capabilities
                    .split(",")
                    .map((s) => s.trim().toUpperCase())
                    .filter(Boolean),
                  preferred_alias: pol.preferred_alias.trim() || undefined,
                  privacy: pol.privacy,
                  fallback: pol.fallback
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setPol({ task_type: "", capabilities: "", preferred_alias: "", privacy: "LOCAL_PREFERRED", fallback: "" });
              })
            }
          >
            {t("common.save")}
          </button>
        </div>
      </div>
      <div className="cards">
        {policies.map((p) => (
          <div className="card" key={p.id}>
            <div className="status-row">
              <strong>{p.task_type}</strong>
              <span className="pill">{p.privacy}</span>
            </div>
            <div className="status-row">
              <span className="muted">capabilities</span>
              <span>{(p.required_capabilities || []).join(", ") || "—"}</span>
            </div>
            <div className="status-row">
              <span className="muted">route</span>
              <span>
                {[p.preferred_alias, ...(p.fallback || [])].filter(Boolean).join(" → ") || "—"}
              </span>
            </div>
            <button className="btn secondary" onClick={() => act(() => deletePolicy(p.task_type))}>
              {t("common.delete")}
            </button>
          </div>
        ))}
        {policies.length === 0 && <p className="muted">{t("runtimes.none")}</p>}
      </div>
    </div>
  );
}
