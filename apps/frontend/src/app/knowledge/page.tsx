"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Citation,
  DocumentRead,
  MemoryHit,
  addMemory,
  fetchDocuments,
  ingestDocument,
  pruneMemories,
  ragQuery,
  searchMemories,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function KnowledgePage() {
  const { t, tv } = useI18n();
  const [docs, setDocs] = useState<DocumentRead[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Citation[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Memory lifecycle (PR 14)
  const [memText, setMemText] = useState("");
  const [memSource, setMemSource] = useState("manual");
  const [memPinned, setMemPinned] = useState(false);
  const [memQuery, setMemQuery] = useState("");
  const [memHits, setMemHits] = useState<MemoryHit[] | null>(null);

  const load = useCallback(async () => {
    try {
      setDocs((await fetchDocuments()).items);
    } catch {
      /* backend may be starting */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ingest = async () => {
    if (!title.trim() || !content.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await ingestDocument({ title: title.trim(), content: content.trim(), source: title.trim() });
      setTitle("");
      setContent("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setHits((await ragQuery(query.trim())).hits);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const rememberFact = async () => {
    if (!memText.trim()) return;
    try {
      await addMemory({
        content: memText.trim(),
        source: memSource.trim() || "manual",
        pinned: memPinned,
      });
      setMemText("");
      setMemPinned(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  };

  const recall = async () => {
    if (!memQuery.trim()) return;
    try {
      setMemHits(await searchMemories(memQuery.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  };

  const prune = async () => {
    const r = await pruneMemories();
    setError(t("kb.pruned", { n: r.pruned }));
  };

  return (
    <div>
      <h1 className="page-title">{t("kb.title")}</h1>
      <p className="page-subtitle">
        {t("kb.subtitle")}
      </p>

      {error && <p className="error">{error}</p>}

      <div className="cards" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <h3>{t("kb.add")}</h3>
          <input
            className="chat-input"
            style={{ width: "100%", padding: "8px 10px", marginBottom: 8 }}
            placeholder={t("tasks.titleCol")}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            placeholder={t("kb.textPh")}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={7}
            style={{
              width: "100%",
              background: "var(--bg)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 10,
              fontSize: 13,
              resize: "vertical",
            }}
          />
          <button className="btn" style={{ marginTop: 8 }} onClick={ingest} disabled={busy}>
            {t("kb.index")}
          </button>
          <p className="muted" style={{ marginTop: 10 }}>
            {t("kb.indexed", { n: docs.length })}
          </p>
        </div>

        <div className="card">
          <h3>{t("kb.ask")}</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              style={{
                flex: 1,
                padding: "10px 12px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--bg)",
                color: "var(--text)",
              }}
              placeholder={t("kb.questionPh")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") search();
              }}
            />
            <button className="btn" onClick={search} disabled={busy}>
              {t("kb.search")}
            </button>
          </div>

          {hits && hits.length === 0 && (
            <p className="muted" style={{ marginTop: 12 }}>{t("cmdk.empty")}</p>
          )}
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            {hits?.map((h) => (
              <div key={h.chunk_id} className="card" style={{ background: "var(--panel-2)" }}>
                <div className="status-row">
                  <strong>{h.document_title}</strong>
                  <span className="pill">{t("kb.score", { n: h.score.toFixed(3) })}</span>
                </div>
                {h.source && <div className="muted">{t("kb.source", { s: h.source })}</div>}
                <p style={{ fontSize: 13, marginTop: 6 }}>{h.content}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <h2 className="page-title" style={{ fontSize: 20, marginTop: 28 }}>
        {t("kb.memory")}
      </h2>
      <p className="page-subtitle">
        {t("kb.memorySubtitle")}
      </p>
      <div className="cards" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <h3>{t("kb.remember")}</h3>
          <textarea
            placeholder={t("kb.rememberPh")}
            value={memText}
            onChange={(e) => setMemText(e.target.value)}
            rows={3}
            style={{
              width: "100%",
              background: "var(--bg)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 10,
              fontSize: 13,
            }}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
            <input
              value={memSource}
              onChange={(e) => setMemSource(e.target.value)}
              placeholder={t("kb.sourcePh")}
              style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
            />
            <label className="web-toggle">
              <input
                type="checkbox"
                checked={memPinned}
                onChange={(e) => setMemPinned(e.target.checked)}
              />
              {t("kb.pin")}
            </label>
            <button className="btn" onClick={rememberFact} disabled={!memText.trim()}>
              {t("common.save")}
            </button>
          </div>
          <button className="btn secondary" style={{ marginTop: 8 }} onClick={prune}>
            {t("kb.prune")}
          </button>
        </div>

        <div className="card">
          <h3>{t("kb.recall")}</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              style={{ flex: 1, padding: "10px 12px", borderRadius: 8 }}
              placeholder={t("kb.recallPh")}
              value={memQuery}
              onChange={(e) => setMemQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && recall()}
            />
            <button className="btn" onClick={recall}>{t("kb.recallBtn")}</button>
          </div>
          {memHits && memHits.length === 0 && (
            <p className="muted" style={{ marginTop: 12 }}>{t("chat.cmd.noMemories")}</p>
          )}
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            {memHits?.map((h) => (
              <div key={h.id} className="card" style={{ background: "var(--panel-2)" }}>
                <div className="status-row">
                  <strong>{h.pinned ? "📌 " : ""}{h.content}</strong>
                  <span className="pill">{t("kb.score", { n: h.score.toFixed(3) })}</span>
                </div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {tv(h.mem_type)}
                  {h.source ? ` · ${t("kb.source", { s: h.source })}` : ""}
                  {h.importance ? ` · ${t("kb.importance", { n: h.importance })}` : ""}
                  {h.tags && h.tags.length ? ` · ${h.tags.join(", ")}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
