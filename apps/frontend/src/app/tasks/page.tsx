"use client";

import { useCallback, useEffect, useState } from "react";
import { Task, createTask, fetchSubtasks, fetchTasks } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

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
  const { tv } = useI18n();
  return (
    <span className="badge">
      <span className={`dot ${STATUS_CLASS[status] ?? "warn"}`} />
      {tv(status)}
    </span>
  );
}

export default function TasksPage() {
  const { t } = useI18n();
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
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  }, [t]);

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
      setError(err instanceof Error ? err.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("tasks.title")}</h1>
      <p className="page-subtitle">
        {t("tasks.subtitle")}
      </p>

      <div className="chat-input" style={{ border: "none", padding: 0, marginBottom: 20 }}>
        <input
          value={objective}
          placeholder={t("tasks.objectivePh")}
          onChange={(e) => setObjective(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          disabled={busy}
        />
        <button className="btn" onClick={submit} disabled={busy || !objective.trim()}>
          {busy ? "…" : t("tasks.run")}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="card" style={{ overflowX: "auto" }}>
        {tasks.length === 0 ? (
          <p className="muted">{t("sys.noTasks")}</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>{t("tasks.titleCol")}</th>
                <th>{t("runtimes.type")}</th>
                <th>{t("common.status")}</th>
                <th>{t("tasks.where")}</th>
                <th>{t("tasks.retries")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((tk) => (
                <tr key={tk.id}>
                  <td>{tk.title ?? tk.id}</td>
                  <td>
                    <span className="pill">{tk.type}</span>
                  </td>
                  <td>
                    <StatusBadge status={tk.status} />
                  </td>
                  <td>
                    {tk.required_capability ? (
                      <span className="pill" title={tk.assigned_node_id ?? undefined}>
                        node:{tk.required_capability}
                      </span>
                    ) : (
                      <span className="muted">{t("tasks.local")}</span>
                    )}
                  </td>
                  <td>
                    {tk.retries}/{tk.max_retries}
                  </td>
                  <td>
                    {tk.type === "alma" && (
                      <button
                        className="btn secondary"
                        onClick={() =>
                          setExpanded(expanded === tk.id ? null : tk.id)
                        }
                      >
                        {expanded === tk.id ? t("tasks.hide") : t("tasks.subtasks")}
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
          <h3>{t("tasks.subtasksDag")}</h3>
          {subtasks.length === 0 ? (
            <p className="muted">{t("tasks.noSubtasks")}</p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>{t("tasks.titleCol")}</th>
                  <th>{t("common.status")}</th>
                  <th>{t("tasks.retries")}</th>
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
