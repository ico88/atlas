"use client";

import { useCallback, useEffect, useState } from "react";
import {
  QueueStatus,
  completeTurn,
  enqueueMessage,
  fetchQueue,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function QueuePage() {
  const { t } = useI18n();
  const [cid, setCid] = useState("demo");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<QueueStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (id: string) => {
    if (!id.trim()) return;
    try {
      setStatus(await fetchQueue(id.trim()));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    refresh(cid);
    const timer = setInterval(() => refresh(cid), 2000);
    return () => clearInterval(timer);
  }, [cid, refresh]);

  const enqueue = async () => {
    if (!content.trim() || busy) return;
    setBusy(true);
    try {
      await enqueueMessage(cid.trim(), content.trim());
      setContent("");
      await refresh(cid);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const complete = async () => {
    setBusy(true);
    try {
      await completeTurn(cid.trim());
      await refresh(cid);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("queue.title")}</h1>
      <p className="page-subtitle">
        {t("queue.subtitle")}
      </p>

      <div className="card" style={{ marginBottom: 16 }}>
        <label className="muted" style={{ fontSize: 13 }}>{t("queue.cid")}</label>
        <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
          <input
            value={cid}
            onChange={(e) => setCid(e.target.value)}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn secondary" onClick={() => refresh(cid)}>
            {t("common.refresh")}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={content}
            placeholder={t("queue.msgPh")}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") enqueue();
            }}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={enqueue} disabled={busy || !content.trim()}>
            {t("queue.enqueue")}
          </button>
          <button className="btn secondary" onClick={complete} disabled={busy}>
            {t("queue.complete")}
          </button>
        </div>
      </div>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      {status && (
        <div className="card">
          <div style={{ marginBottom: 10 }}>
            <span className={`queue-badge ${status.active ? "active" : "idle"}`}>
              {status.active ? `● ${t("v.active")}` : `○ ${t("v.idle")}`}
            </span>
            <span className="muted" style={{ marginLeft: 12 }}>
              {t("queue.stats", { pending: status.pending, active: status.active_total })}
            </span>
          </div>
          {status.items.length === 0 ? (
            <p className="muted">{t("queue.none")}</p>
          ) : (
            status.items.map((m, i) => (
              <div key={m.id} className="queue-item">
                <strong>#{i + 1}</strong> {m.content}
                {m.merged_count && m.merged_count > 1 && (
                  <span className="meta"> {t("queue.merged", { n: m.merged_count })}</span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
