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
import { useI18n } from "@/lib/i18n";

function pct(v: unknown): string {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
}

export default function CompliancePage() {
  const { t, tv } = useI18n();
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
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

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
      setError(e instanceof Error ? e.message : t("common.failed"));
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
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const s = report?.summary ?? {};
  const compliancePct = pct(s["compliance_pct"]);

  return (
    <div>
      <h1 className="page-title">{t("nav.compliance")}</h1>
      <p className="page-subtitle">
        {t("comp.subtitle")}
      </p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <div className="cards" style={{ marginBottom: 16 }}>
        <div className="card" style={{ textAlign: "center" }}>
          <div className="muted" style={{ fontSize: 12 }}>{t("dash.compliance")}</div>
          <div style={{ fontSize: 34, fontWeight: 800 }}>{compliancePct}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {t("comp.nodes", { n: String(s["compliant"] ?? 0), total: String(s["total"] ?? 0) })}
          </div>
        </div>
        <div className="card">
          <div className="status-row"><span className="muted">{t("v.online")}</span><span className="pill">{String(s["online"] ?? 0)}</span></div>
          <div className="status-row"><span className="muted">{t("comp.drifted")}</span><span className="pill">{String(s["drifted"] ?? 0)}</span></div>
          <div className="status-row"><span className="muted">{t("v.quarantined")}</span><span className="pill">{String(s["quarantined"] ?? 0)}</span></div>
          <div className="status-row">
            <span className="muted">{t("comp.minMet")}</span>
            <span className={`queue-badge ${s["meets_min_online"] ? "active" : ""}`}>
              {s["meets_min_online"] ? t("common.yes") : t("common.no")}
            </span>
          </div>
        </div>
        <div className="card">
          <strong>{t("comp.auto")}</strong>
          <p className="muted" style={{ fontSize: 12, margin: "6px 0 10px" }}>
            {t("comp.autoHelp")}
          </p>
          <button className="btn" disabled={busy} onClick={() => act(() => autoRemediate())}>
            {t("comp.autoNow")}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>{t("comp.desired")}</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
          <input
            value={desired.target_version}
            placeholder={t("comp.targetPh")}
            onChange={(e) => setDesired({ ...desired, target_version: e.target.value })}
            style={{ flex: "1 1 160px", padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={capsText}
            placeholder={t("comp.capsPh")}
            onChange={(e) => setCapsText(e.target.value)}
            style={{ flex: "1 1 220px", padding: "8px 10px", borderRadius: 8 }}
          />
          <label className="muted" style={{ fontSize: 13 }}>
            {t("comp.minOnline")}{" "}
            <input
              type="number"
              min={0}
              value={desired.min_online}
              onChange={(e) => setDesired({ ...desired, min_online: Math.max(0, Number(e.target.value)) })}
              style={{ width: 60, padding: "6px 8px", borderRadius: 8 }}
            />
          </label>
          <button className="btn secondary" disabled={busy} onClick={saveDesired}>
            {t("common.save")}
          </button>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <table className="data">
          <thead>
            <tr>
              <th>{t("fleet.node")}</th>
              <th>{t("sys.version")}</th>
              <th>{t("common.status")}</th>
              <th>{t("comp.diagnosis")}</th>
              <th>{t("comp.fix")}</th>
            </tr>
          </thead>
          <tbody>
            {(report?.nodes ?? []).map((n) => (
              <tr key={n.node_ref}>
                <td>{n.node_ref}</td>
                <td>{n.version ?? "—"}</td>
                <td>
                  {n.compliant ? (
                    <span className="queue-badge active">{t("comp.compliant")}</span>
                  ) : (
                    <span className="queue-badge">{n.issues.map((i) => tv(i)).join(", ") || t("comp.drift")}</span>
                  )}
                </td>
                <td className="muted" style={{ fontSize: 12 }}>{n.diagnosis ?? ""}</td>
                <td>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {n.recommended_action === "remediate" && (
                      <button className="btn" onClick={() => act(() => remediateNode(n.node_ref!, "remediate"))}>
                        {t("v.remediate")}
                      </button>
                    )}
                    {!n.quarantined && !n.compliant && (
                      <button className="btn secondary" onClick={() => act(() => remediateNode(n.node_ref!, "quarantine"))}>
                        {t("v.quarantine")}
                      </button>
                    )}
                    {n.quarantined && (
                      <button className="btn" onClick={() => act(() => remediateNode(n.node_ref!, "reinstate"))}>
                        {t("v.reinstate")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {(report?.nodes ?? []).length === 0 && (
              <tr><td colSpan={5} className="muted">{t("chat.cmd.noNodes")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
