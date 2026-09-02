"use client";

import { useCallback, useEffect, useState } from "react";
import { Task, createTask, fetchSubtasks, fetchTasks } from "@/lib/api";

const STATUS_CLASS: Record<string, string> = {
  COMPLETED: "ok",
  RUNNING: "warn",
  QUEUED: "warn",
  RETRYING: "warn",
  WAITING_DEPENDENCY: "warn",
  FAILED: "bad",
  CANCELLED: "bad",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className="badge">
      <span className={`dot ${STATUS_CLASS[status] ?? "warn"}`} />
      {status}
    </span>
  );
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [objective, setObjective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [subtasks, setSubtasks] = useState<Task[]>([]);

  const load = useCallback(async () => {
    try {
      const list = await fetchTasks();
      // Show only top-level tasks (subtasks appear when expanding an ALMA task).
      setTasks(list.items.filter((t) => !t.parent_task_id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tasks");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (!expanded) return;
    let active = true;
    const tick = async () => {
      const subs = await fetchSubtasks(expanded);
      if (active) setSubtasks(subs);
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [expanded]);

  const submit = async () => {
    const title = objective.trim();
    if (!title || busy) return;
    setBusy(true);
    try {
      await createTask({ title, type: "alma", objective: title });
      setObjective("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Tasks &amp; ALMA</h1>
      <p className="page-subtitle">
        Give ALMA an objective — it decomposes it into a DAG of subtasks, runs
        them (independent ones in parallel), and aggregates the result (spec §7).
      </p>

      <div className="chat-input" style={{ border: "none", padding: 0, marginBottom: 20 }}>
        <input
          value={objective}
          placeholder="e.g. Prepare release notes for v0.1"
          onChange={(e) => setObjective(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          disabled={busy}
        />
        <button className="btn" onClick={submit} disabled={busy || !objective.trim()}>
          {busy ? "…" : "Run with ALMA"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="card" style={{ overflowX: "auto" }}>
        {tasks.length === 0 ? (
          <p className="muted">No tasks yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Status</th>
                <th>Where</th>
                <th>Retries</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id}>
                  <td>{t.title ?? t.id}</td>
                  <td>
                    <span className="pill">{t.type}</span>
                  </td>
                  <td>
                    <StatusBadge status={t.status} />
                  </td>
                  <td>
                    {t.required_capability ? (
                      <span className="pill" title={t.assigned_node_id ?? undefined}>
                        node:{t.required_capability}
                      </span>
                    ) : (
                      <span className="muted">local</span>
                    )}
                  </td>
                  <td>
                    {t.retries}/{t.max_retries}
                  </td>
                  <td>
                    {t.type === "alma" && (
                      <button
                        className="btn secondary"
                        onClick={() =>
                          setExpanded(expanded === t.id ? null : t.id)
                        }
                      >
                        {expanded === t.id ? "Hide" : "Subtasks"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {expanded && (
        <div className="card" style={{ marginTop: 16, overflowX: "auto" }}>
          <h3>Subtasks (DAG)</h3>
          {subtasks.length === 0 ? (
            <p className="muted">No subtasks yet — ALMA may still be planning.</p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Retries</th>
                </tr>
              </thead>
              <tbody>
                {subtasks.map((s) => (
                  <tr key={s.id}>
                    <td>{s.title ?? s.id}</td>
                    <td>
                      <StatusBadge status={s.status} />
                    </td>
                    <td>
                      {s.retries}/{s.max_retries}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
