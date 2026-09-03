"use client";

import { useCallback, useEffect, useState } from "react";
import {
  EvalRun,
  EvalSuite,
  addEvalCase,
  createEvalSuite,
  fetchEvalRuns,
  fetchEvalSuites,
  runEvalSuite,
} from "@/lib/api";

function pct(v?: number | null): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

export default function EvalsPage() {
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [selected, setSelected] = useState<EvalSuite | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [name, setName] = useState("");
  const [caseInput, setCaseInput] = useState("");
  const [caseExpected, setCaseExpected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSuites((await fetchEvalSuites()).items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openSuite = useCallback(async (s: EvalSuite) => {
    setSelected(s);
    try {
      setRuns((await fetchEvalRuns(s.id)).items);
    } catch {
      setRuns([]);
    }
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    const s = await createEvalSuite(name.trim());
    setName("");
    await load();
    await openSuite(s);
  };

  const addCase = async () => {
    if (!selected || !caseInput.trim()) return;
    const expected = caseExpected.split(",").map((x) => x.trim()).filter(Boolean);
    await addEvalCase(selected.id, {
      input: caseInput.trim(),
      expected_substrings: expected.length ? expected : undefined,
    });
    setCaseInput("");
    setCaseExpected("");
  };

  const run = async (isBaseline: boolean) => {
    if (!selected) return;
    setBusy(true);
    try {
      await runEvalSuite(selected.id, isBaseline);
      setRuns((await fetchEvalRuns(selected.id)).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "run failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 className="page-title">Evals</h1>
      <p className="page-subtitle">
        Quality, safety and performance evaluation suites (ROADMAP PR 16). Runs use
        the active model; mark one as a baseline to compare against.
      </p>

      {error && <p className="error">Error: {error}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={name}
            placeholder="New suite name…"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={create} disabled={!name.trim()}>
            Create suite
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {suites.length === 0 && <p className="muted">No suites yet.</p>}
          {suites.map((s) => (
            <div
              key={s.id}
              className={`convo-item ${selected?.id === s.id ? "active" : ""}`}
              onClick={() => openSuite(s)}
            >
              {s.name}
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Select a suite.</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>{selected.name}</h3>

              <div className="card" style={{ background: "var(--panel-2)", marginBottom: 12 }}>
                <strong>Add a case</strong>
                <input
                  value={caseInput}
                  placeholder="Prompt / input…"
                  onChange={(e) => setCaseInput(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8, margin: "8px 0" }}
                />
                <input
                  value={caseExpected}
                  placeholder="Expected substrings (comma-separated)"
                  onChange={(e) => setCaseExpected(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 8 }}
                />
                <button className="btn secondary" style={{ marginTop: 8 }} onClick={addCase} disabled={!caseInput.trim()}>
                  Add case
                </button>
              </div>

              <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                <button className="btn" onClick={() => run(false)} disabled={busy}>
                  {busy ? "Running…" : "Run"}
                </button>
                <button className="btn secondary" onClick={() => run(true)} disabled={busy}>
                  Run as baseline
                </button>
              </div>

              <h3 style={{ fontSize: 14 }}>Runs</h3>
              {runs.length === 0 ? (
                <p className="muted">No runs yet.</p>
              ) : (
                <div className="card" style={{ overflowX: "auto" }}>
                  <table className="data" style={{ width: "100%" }}>
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Model</th>
                        <th>Pass</th>
                        <th>Quality</th>
                        <th>Safety</th>
                        <th>Latency</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((r) => (
                        <tr key={r.id}>
                          <td>{new Date(r.created_at).toLocaleTimeString()}</td>
                          <td>{r.model || r.provider || "—"}</td>
                          <td>{pct(r.metrics?.pass_rate)}</td>
                          <td>{pct(r.metrics?.avg_quality)}</td>
                          <td>{pct(r.metrics?.avg_safety)}</td>
                          <td>{r.metrics?.avg_latency_ms != null ? `${r.metrics.avg_latency_ms} ms` : "—"}</td>
                          <td>{r.is_baseline ? "⭐ baseline" : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
