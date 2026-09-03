"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Environment,
  EnvironmentSnapshot,
  createEnvironment,
  fetchEnvironments,
  fetchSnapshots,
  restoreSnapshot,
  snapshotEnvironment,
  updateEnvironment,
} from "@/lib/api";

export default function EnvironmentsPage() {
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [selected, setSelected] = useState<Environment | null>(null);
  const [snaps, setSnaps] = useState<EnvironmentSnapshot[]>([]);
  const [name, setName] = useState("");
  const [manifestText, setManifestText] = useState("{}");
  const [varsText, setVarsText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEnvs((await fetchEnvironments()).items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load environments");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const open = useCallback(async (env: Environment) => {
    setSelected(env);
    setManifestText(JSON.stringify(env.manifest ?? {}, null, 2));
    setVarsText(JSON.stringify(env.variables ?? {}, null, 2));
    try {
      setSnaps((await fetchSnapshots(env.id)).items);
    } catch {
      setSnaps([]);
    }
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    try {
      const env = await createEnvironment({ name: name.trim() });
      setName("");
      await load();
      await open(env);
    } catch (e) {
      setError(e instanceof Error ? e.message : "create failed");
    }
  };

  const parse = (s: string): Record<string, unknown> => {
    try {
      const v = JSON.parse(s);
      return typeof v === "object" && v ? v : {};
    } catch {
      throw new Error("invalid JSON");
    }
  };

  const saveManifest = async () => {
    if (!selected) return;
    try {
      const env = await updateEnvironment(selected.id, {
        manifest: parse(manifestText),
        variables: parse(varsText),
      });
      setSelected(env);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    }
  };

  const snapshot = async () => {
    if (!selected) return;
    await snapshotEnvironment(selected.id);
    setSnaps((await fetchSnapshots(selected.id)).items);
  };

  const restore = async (sid: string) => {
    const env = await restoreSnapshot(sid);
    await open(env);
    await load();
  };

  return (
    <div>
      <h1 className="page-title">Environments</h1>
      <p className="page-subtitle">
        Isolated workspaces with a declarative manifest; scope tasks, queries and
        memory, and snapshot / restore config (ROADMAP PR 13).
      </p>

      {error && <p className="error">Error: {error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={name}
            placeholder="New environment name…"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={create} disabled={!name.trim()}>
            Create
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {envs.length === 0 && <p className="muted">No environments yet.</p>}
          {envs.map((e) => (
            <div
              key={e.id}
              className={`convo-item ${selected?.id === e.id ? "active" : ""}`}
              onClick={() => open(e)}
            >
              {e.name}{" "}
              <span className={`queue-badge ${e.status === "ACTIVE" ? "active" : "idle"}`}>
                {e.status}
              </span>
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Select an environment.</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>
                {selected.name} <span className="muted">/{selected.slug}</span>
              </h3>
              <label className="muted" style={{ fontSize: 13 }}>Manifest (JSON)</label>
              <textarea
                value={manifestText}
                onChange={(e) => setManifestText(e.target.value)}
                rows={6}
                style={{ width: "100%", fontFamily: "monospace", fontSize: 13, marginBottom: 8 }}
              />
              <label className="muted" style={{ fontSize: 13 }}>Variables (JSON)</label>
              <textarea
                value={varsText}
                onChange={(e) => setVarsText(e.target.value)}
                rows={5}
                style={{ width: "100%", fontFamily: "monospace", fontSize: 13 }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button className="btn" onClick={saveManifest}>Save</button>
                <button className="btn secondary" onClick={snapshot}>Snapshot</button>
              </div>

              <h3 style={{ fontSize: 14, marginTop: 18 }}>Snapshots</h3>
              {snaps.length === 0 ? (
                <p className="muted">No snapshots yet.</p>
              ) : (
                snaps.map((s) => (
                  <div key={s.id} className="queue-item" style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>
                      {s.name || s.id.slice(0, 8)}{" "}
                      <span className="meta">
                        {s.stats ? `tasks ${s.stats.tasks ?? 0} · mem ${s.stats.memories ?? 0}` : ""}
                      </span>
                    </span>
                    <button className="btn secondary" onClick={() => restore(s.id)}>
                      Restore
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
