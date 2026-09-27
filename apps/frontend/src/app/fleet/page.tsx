"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Deployment,
  DeploymentSummary,
  advanceDeployment,
  createDeployment,
  fetchDeployment,
  fetchDeployments,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function statusClass(s: string): string {
  if (s === "COMPLETED" || s === "HEALTHY") return "queue-badge active";
  if (s === "ROLLED_BACK" || s === "FAILED" || s === "INCOMPATIBLE") return "queue-badge";
  return "queue-badge idle";
}

export default function FleetPage() {
  const { t, tv } = useI18n();
  const [items, setItems] = useState<DeploymentSummary[]>([]);
  const [selected, setSelected] = useState<Deployment | null>(null);
  const [version, setVersion] = useState("");
  const [canary, setCanary] = useState(1);
  const [minCompat, setMinCompat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await fetchDeployments()).items);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh the selected deployment while it is in flight.
  useEffect(() => {
    if (!selected || ["COMPLETED", "ROLLED_BACK", "FAILED"].includes(selected.status)) return;
    const id = setInterval(async () => {
      try {
        setSelected(await fetchDeployment(selected.id));
      } catch {
        /* transient */
      }
    }, 2500);
    return () => clearInterval(id);
  }, [selected]);

  const create = async () => {
    if (!version.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const d = await createDeployment({
        target_version: version.trim(),
        canary_count: canary,
        min_compatible: minCompat.trim() || undefined,
      });
      setSelected(d);
      setVersion("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const advance = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await advanceDeployment(selected.id));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const wave = (w: string) => (selected?.targets ?? []).filter((tg) => tg.wave === w);

  return (
    <div>
      <h1 className="page-title">{t("nav.fleet")}</h1>
      <p className="page-subtitle">{t("fleet.subtitle")}</p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <strong>{t("fleet.new")}</strong>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <input
            value={version}
            placeholder={t("fleet.versionPh")}
            onChange={(e) => setVersion(e.target.value)}
            style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
          />
          <label className="muted" style={{ fontSize: 13 }}>
            {t("fleet.canary")}{" "}
            <input
              type="number"
              min={0}
              value={canary}
              onChange={(e) => setCanary(Math.max(0, Number(e.target.value)))}
              style={{ width: 60, padding: "6px 8px", borderRadius: 8 }}
            />
          </label>
          <input
            value={minCompat}
            placeholder={t("fleet.minCompatPh")}
            onChange={(e) => setMinCompat(e.target.value)}
            style={{ flex: "1 1 160px", padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={create} disabled={busy || !version.trim()}>
            {t("fleet.start")}
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {items.length === 0 && <p className="muted">{t("fleet.none")}</p>}
          {items.map((d) => (
            <div
              key={d.id}
              className={`convo-item ${selected?.id === d.id ? "active" : ""}`}
              onClick={async () => setSelected(await fetchDeployment(d.id))}
            >
              <span className="convo-title">{d.target_version}</span>
              <span className={statusClass(d.status)}>{tv(d.status)}</span>
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">{t("fleet.select")}</p>
          ) : (
            <div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span className={statusClass(selected.status)}>{tv(selected.status)}</span>
                <span className="pill">→ {selected.target_version}</span>
                {selected.previous_version && (
                  <span className="muted">{t("fleet.from", { v: selected.previous_version })}</span>
                )}
                {["CANARY", "ROLLING"].includes(selected.status) && (
                  <button
                    className="btn"
                    style={{ marginLeft: "auto" }}
                    disabled={busy}
                    onClick={advance}
                  >
                    {t("fleet.advance")}
                  </button>
                )}
              </div>

              {["canary", "rollout"].map((w) => {
                const ts = wave(w);
                if (ts.length === 0) return null;
                return (
                  <div key={w} style={{ marginTop: 14 }}>
                    <h3 style={{ fontSize: 14 }}>{t(`fleet.wave.${w}`)}</h3>
                    <div className="card" style={{ overflowX: "auto" }}>
                      <table className="data">
                        <thead>
                          <tr>
                            <th>{t("fleet.node")}</th>
                            <th>{t("fleet.fromCol")}</th>
                            <th>{t("common.status")}</th>
                            <th>{t("common.detail")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ts.map((tg) => (
                            <tr key={tg.id}>
                              <td>{tg.node_ref}</td>
                              <td>{tg.from_version ?? "—"}</td>
                              <td>
                                <span className={statusClass(tg.status)}>{tv(tg.status)}</span>
                              </td>
                              <td className="muted">{tg.detail ?? ""}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
