"use client";

import { useCallback, useEffect, useState } from "react";
import Markdown from "@/components/Markdown";
import {
  QueryDetail,
  QueryRead,
  cancelQuery,
  createQuery,
  fetchQueries,
  fetchQuery,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const TERMINAL = ["COMPLETED", "FAILED", "CANCELLED"];

function StatusBadge({ status }: { status: string }) {
  const { tv } = useI18n();
  const cls =
    status === "COMPLETED"
      ? "active"
      : status === "RUNNING" || status === "PENDING"
        ? "idle"
        : "idle";
  return <span className={`queue-badge ${cls}`}>{tv(status)}</span>;
}

export default function QueriesPage() {
  const { t } = useI18n();
  const [items, setItems] = useState<QueryRead[]>([]);
  const [prompt, setPrompt] = useState("");
  const [selected, setSelected] = useState<QueryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    try {
      setItems((await fetchQueries()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      setSelected(await fetchQuery(id));
    } catch {
      /* transient */
    }
  }, []);

  useEffect(() => {
    loadList();
    const timer = setInterval(() => {
      loadList();
      if (selected && !TERMINAL.includes(selected.status)) {
        loadDetail(selected.id);
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [loadList, loadDetail, selected]);

  const submit = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createQuery({ prompt: prompt.trim() });
      setPrompt("");
      await loadList();
      await loadDetail(created.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (id: string) => {
    try {
      await cancelQuery(id);
      await loadList();
      await loadDetail(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.queries")}</h1>
      <p className="page-subtitle">
        {t("q.subtitle")}
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={prompt}
            placeholder={t("q.promptPh")}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={submit} disabled={busy || !prompt.trim()}>
            {t("q.run")}
          </button>
        </div>
      </div>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <div className="chat-layout">
        <div className="convo-list">
          {items.length === 0 && <p className="muted">{t("q.none")}</p>}
          {items.map((q) => (
            <div
              key={q.id}
              className={`convo-item ${selected?.id === q.id ? "active" : ""}`}
              onClick={() => loadDetail(q.id)}
              title={q.prompt}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {q.prompt}
                </span>
                <StatusBadge status={q.status} />
              </div>
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">{t("q.select")}</p>
          ) : (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginBottom: 8,
                  flexWrap: "wrap",
                }}
              >
                <StatusBadge status={selected.status} />
                {selected.provider && (
                  <span className="muted">
                    {selected.provider} · {selected.model} · {t("q.tokens", { n: selected.progress })}
                  </span>
                )}
                {!TERMINAL.includes(selected.status) && (
                  <button
                    className="btn secondary"
                    style={{ marginLeft: "auto" }}
                    onClick={() => cancel(selected.id)}
                  >
                    {t("common.cancel")}
                  </button>
                )}
              </div>
              <p><strong>{t("q.prompt")}:</strong> {selected.prompt}</p>
              {selected.error && <p className="error">{t("common.errorMsg", { error: selected.error })}</p>}
              <div className="card result-card" style={{ marginTop: 8 }}>
                {selected.result ? (
                  <Markdown text={selected.result} />
                ) : (
                  <span className="muted">{t("q.noOutput")}</span>
                )}
              </div>
              <h3 style={{ marginTop: 16, fontSize: 14 }}>{t("q.events")}</h3>
              {selected.events.map((ev) => (
                <div key={ev.id} className="queue-item">
                  <strong>{ev.event_type}</strong>
                  {ev.message && <span className="meta"> {ev.message}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
