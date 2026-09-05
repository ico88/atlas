"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ComplianceReport,
  DesiredState,
  autoRemediate,
  fetchCompliance,
  fetchDesiredState,
  remediateNode,
  setDesiredState,
} from "@/lib/api";

function pct(v: unknown): string {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
}

export default function CompliancePage() {
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [desired, setDesired] = useState<DesiredState>({
    target_version: "",
    required_capabilities: [],
    min_online: 0,
  });
  const [capsText, setCapsText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, d] = await Promise.all([fetchCompliance(), fetchDesiredState()]);
      setReport(r);
      setDesired(d);
      setCapsText((d.required_capabilities || []).join(", "));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const saveDesired = async () => {
    setBusy(true);
    try {
      await setDesiredState({
        target_version: desired.target_version.trim(),
        required_capabilities: capsText.split(",").map((s) => s.trim()).filter(Boolean),
        min_online: desired.min_online,
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "action failed");
    } finally {
      setBusy(false);
    }
  };

  const s = report?.summary ?? {};
  const compliancePct = pct(s["compliance_pct"]);

  return (
    <div>
      <h1 className="page-title">Fleet Health</h1>
      <p className="page-subtitle">
        Set the desired fleet state, see drift at a glance, and fix it in one click
        (ROADMAP PR 24/25). Version drift can be auto-remediated safely; offline and
        capability problems are surfaced for you to decide.
      </p>

      {error && <p className="error">Error: {error}</p>}

      <div className="cards" style={{ marginBottom: 16 }}>
        <div className="card" style={{ textAlign: "center" }}>
          <div className="muted" style={{ fontSize: 12 }}>Compliance</div>
          <div style={{ fontSize: 34, fontWeight: 800 }}>{compliancePct}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {String(s["compliant"] ?? 0)}/{String(s["total"] ?? 0)} nodes
          </div>
        </div>
        <div className="card">
          <div className="status-row"><span className="muted">Online</span><span className="pill">{String(s["online"] ?? 0)}</span></div>
          <div className="status-row"><span className="muted">Drifted</span><span className="pill">{String(s["drifted"] ?? 0)}</span></div>
          <div className="status-row"><span className="muted">Quarantined</span><span className="pill">{String(s["quarantined"] ?? 0)}</span></div>
          <div className="status-row">
            <span className="muted">Min online met</span>
            <span className={`queue-badge ${s["meets_min_online"] ? "active" : ""}`}>
              {s["meets_min_online"] ? "yes" : "no"}
            </span>
          </div>
        </div>
        <div className="card">
          <strong>Auto-remediation</strong>
          <p className="muted" style={{ fontSize: 12, margin: "6px 0 10px" }}>
            Re-aligns version-drifted nodes to the desired version. Safe: it never
            touches offline or quarantined nodes.
          </p>
          <button className="btn" disabled={busy} onClick={() => act(() => autoRemediate())}>
            Auto-remediate now
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>Desired state</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
          <input
            value={desired.target_version}
            placeholder="Target version"
            onChange={(e) => setDesired({ ...desired, target_version: e.target.value })}
            style={{ flex: "1 1 160px", padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={capsText}
            placeholder="Required capabilities (comma-separated)"
            onChange={(e) => setCapsText(e.target.value)}
            style={{ flex: "1 1 220px", padding: "8px 10px", borderRadius: 8 }}
          />
          <label className="muted" style={{ fontSize: 13 }}>
            Min online{" "}
            <input
              type="number"
              min={0}
              value={desired.min_online}
              onChange={(e) => setDesired({ ...desired, min_online: Math.max(0, Number(e.target.value)) })}
              style={{ width: 60, padding: "6px 8px", borderRadius: 8 }}
            />
          </label>
          <button className="btn secondary" disabled={busy} onClick={saveDesired}>
            Save
          </button>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table className="data">
          <thead>
            <tr>
              <th>Node</th>
              <th>Version</th>
              <th>State</th>
              <th>Diagnosis</th>
              <th>Fix</th>
            </tr>
          </thead>
          <tbody>
            {(report?.nodes ?? []).map((n) => (
              <tr key={n.node_ref}>
                <td>{n.node_ref}</td>
                <td>{n.version ?? "—"}</td>
                <td>
                  {n.compliant ? (
                    <span className="queue-badge active">compliant</span>
                  ) : (
                    <span className="queue-badge">{n.issues.join(", ") || "drift"}</span>
                  )}
                </td>
                <td className="muted" style={{ fontSize: 12 }}>{n.diagnosis ?? ""}</td>
                <td>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {n.recommended_action === "remediate" && (
                      <button className="btn" onClick={() => act(() => remediateNode(n.node_ref!, "remediate"))}>
                        Remediate
                      </button>
                    )}
                    {!n.quarantined && !n.compliant && (
                      <button className="btn secondary" onClick={() => act(() => remediateNode(n.node_ref!, "quarantine"))}>
                        Quarantine
                      </button>
                    )}
                    {n.quarantined && (
                      <button className="btn" onClick={() => act(() => remediateNode(n.node_ref!, "reinstate"))}>
                        Reinstate
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {(report?.nodes ?? []).length === 0 && (
              <tr><td colSpan={5} className="muted">No nodes registered.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
