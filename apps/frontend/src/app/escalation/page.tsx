"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Escalation,
  EscalationSummary,
  fetchEscalation,
  fetchEscalations,
  importExternalResponse,
  prepareEscalation,
  validateEscalation,
} from "@/lib/api";

export default function EscalationPage() {
  const [list, setList] = useState<EscalationSummary[]>([]);
  const [current, setCurrent] = useState<Escalation | null>(null);
  const [objective, setObjective] = useState("");
  const [target, setTarget] = useState("chatgpt");
  const [logs, setLogs] = useState("");
  const [response, setResponse] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setList((await fetchEscalations()).items);
    } catch {
      /* backend may be starting */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const open = async (id: string) => {
    setCurrent(await fetchEscalation(id));
    setResponse("");
  };

  const prepare = async () => {
    if (!objective.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const esc = await prepareEscalation({
        objective: objective.trim(),
        target,
        context: logs.trim() ? { logs: logs.trim() } : undefined,
      });
      setCurrent(esc);
      setObjective("");
      setLogs("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prepare failed");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!current) return;
    try {
      await navigator.clipboard.writeText(current.package);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Clipboard unavailable — select the text manually.");
    }
  };

  const doImport = async () => {
    if (!current || !response.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setCurrent(await importExternalResponse(current.id, response.trim()));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (approved: boolean) => {
    if (!current || busy) return;
    setBusy(true);
    try {
      setCurrent(await validateEscalation(current.id, approved));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validate failed");
    } finally {
      setBusy(false);
    }
  };

  const untrusted =
    current?.validation && (current.validation as Record<string, unknown>).trusted === false;

  return (
    <div>
      <h1 className="page-title">Manual Escalation</h1>
      <p className="page-subtitle">
        Prepare a self-sufficient package to paste into ChatGPT Plus / Claude Pro,
        then import the reply. Imported replies are <strong>untrusted</strong> until
        you validate them (spec §10). ATLAS never automates the browser session.
      </p>

      {error && <p className="error">{error}</p>}

      <div className="chat-layout">
        <div className="convo-list">
          <div className="card" style={{ background: "transparent", border: "none", padding: 4 }}>
            <input
              style={inputStyle}
              placeholder="Objective…"
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
            />
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              style={{ ...inputStyle, marginTop: 6 }}
            >
              <option value="chatgpt">ChatGPT Plus</option>
              <option value="claude">Claude Pro</option>
            </select>
            <textarea
              placeholder="Logs / context (optional)"
              value={logs}
              onChange={(e) => setLogs(e.target.value)}
              rows={3}
              style={{ ...inputStyle, marginTop: 6, resize: "vertical" }}
            />
            <button className="btn" style={{ width: "100%", marginTop: 6 }} onClick={prepare} disabled={busy}>
              Prepare package
            </button>
          </div>
          <div className="muted" style={{ padding: "8px 6px", fontSize: 12 }}>Recent</div>
          {list.map((e) => (
            <div
              key={e.id}
              className={`convo-item ${current?.id === e.id ? "active" : ""}`}
              onClick={() => open(e.id)}
              title={e.objective}
            >
              [{e.status}] {e.objective}
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 18, display: "block", overflowY: "auto" }}>
          {!current ? (
            <p className="muted">Prepare or select an escalation.</p>
          ) : (
            <div>
              <div className="status-row">
                <strong>{current.objective}</strong>
                <span className="pill">{current.status}</span>
              </div>

              <h3 style={{ marginTop: 14 }}>
                1. Copy this into {current.target === "claude" ? "Claude Pro" : "ChatGPT Plus"}
                <button className="btn secondary" style={{ marginLeft: 10 }} onClick={copy}>
                  {copied ? "Copied!" : "Copy"}
                </button>
              </h3>
              <pre
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: 12,
                  fontSize: 12,
                  whiteSpace: "pre-wrap",
                  maxHeight: 260,
                  overflowY: "auto",
                }}
              >
                {current.package}
              </pre>

              <h3 style={{ marginTop: 14 }}>2. Paste the reply back</h3>
              <textarea
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                rows={5}
                placeholder="Paste the model's response…"
                style={{ ...inputStyle, width: "100%", resize: "vertical" }}
              />
              <button className="btn" style={{ marginTop: 8 }} onClick={doImport} disabled={busy}>
                Import response
              </button>

              {current.response && (
                <div className="card" style={{ marginTop: 14, background: "var(--panel-2)" }}>
                  <div className="status-row">
                    <strong>Imported response</strong>
                    <span className={`pill`} style={{ color: untrusted ? "var(--bad)" : "var(--ok)" }}>
                      {untrusted ? "UNTRUSTED" : "trusted"}
                    </span>
                  </div>
                  <p style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>{current.response}</p>
                  {current.status === "RESPONSE_IMPORTED" && (
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="btn" onClick={() => decide(true)} disabled={busy}>
                        Validate
                      </button>
                      <button className="btn secondary" onClick={() => decide(false)} disabled={busy}>
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg)",
  color: "var(--text)",
  fontSize: 13,
};
