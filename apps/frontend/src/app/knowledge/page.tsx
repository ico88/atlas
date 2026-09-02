"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Citation,
  DocumentRead,
  fetchDocuments,
  ingestDocument,
  ragQuery,
} from "@/lib/api";

export default function KnowledgePage() {
  const [docs, setDocs] = useState<DocumentRead[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Citation[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setError(err instanceof Error ? err.message : "Ingest failed");
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
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Knowledge (RAG)</h1>
      <p className="page-subtitle">
        Index documents and retrieve relevant passages with citations (spec §6).
      </p>

      {error && <p className="error">{error}</p>}

      <div className="cards" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="card">
          <h3>Add a document</h3>
          <input
            className="chat-input"
            style={{ width: "100%", padding: "8px 10px", marginBottom: 8 }}
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            placeholder="Paste document text…"
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
            Index document
          </button>
          <p className="muted" style={{ marginTop: 10 }}>
            {docs.length} document(s) indexed
          </p>
        </div>

        <div className="card">
          <h3>Ask the knowledge base</h3>
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
              placeholder="Ask a question…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") search();
              }}
            />
            <button className="btn" onClick={search} disabled={busy}>
              Search
            </button>
          </div>

          {hits && hits.length === 0 && (
            <p className="muted" style={{ marginTop: 12 }}>No matches.</p>
          )}
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            {hits?.map((h) => (
              <div key={h.chunk_id} className="card" style={{ background: "var(--panel-2)" }}>
                <div className="status-row">
                  <strong>{h.document_title}</strong>
                  <span className="pill">score {h.score.toFixed(3)}</span>
                </div>
                {h.source && <div className="muted">source: {h.source}</div>}
                <p style={{ fontSize: 13, marginTop: 6 }}>{h.content}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
