"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  RecommendedModel,
  SetupStatus,
  fetchPullStatus,
  fetchSetupStatus,
  setupActivate,
  setupInstall,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

function gb(mb?: number | null): string {
  return mb ? `${Math.round(mb / 1024)} GB` : "—";
}

export default function SetupPage() {
  const { t } = useI18n();
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await fetchSetupStatus());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, [load]);

  // Install = download (with progress) then it auto-activates on the backend.
  const install = async (model: string) => {
    setBusy(model);
    setProgress(t("setup.starting"));
    try {
      await setupInstall(model);
      poll.current = setInterval(async () => {
        try {
          const st = (await fetchPullStatus()).items;
          const item = st[model];
          if (!item) return;
          if (item.state === "pulling" && item.total) {
            const p = Math.round(((item.completed || 0) / (item.total || 1)) * 100);
            setProgress(`${t("setup.downloading")} ${p}%`);
          } else if (item.state === "pulling") {
            setProgress(item.status || t("setup.downloading"));
          } else if (item.state === "done") {
            if (poll.current) clearInterval(poll.current);
            setProgress(t("setup.done"));
            setBusy(null);
            await load();
          } else if (item.state === "error") {
            if (poll.current) clearInterval(poll.current);
            setProgress(null);
            setBusy(null);
            setError(item.status || "pull failed");
          }
        } catch {
          /* transient */
        }
      }, 1500);
    } catch (e) {
      setBusy(null);
      setProgress(null);
      setError(e instanceof Error ? e.message : "install failed");
    }
  };

  const activate = async (model: string) => {
    setBusy(model);
    try {
      await setupActivate(model);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "activate failed");
    } finally {
      setBusy(null);
    }
  };

  const modelCard = (m: RecommendedModel, primary: boolean) => {
    const installed = status?.installed_models.includes(m.model);
    const active = status?.active_model === m.model;
    return (
      <div className="card" key={m.model} style={primary ? { borderColor: "var(--accent)" } : undefined}>
        <div className="status-row">
          <strong>{m.label}</strong>
          {active ? (
            <span className="queue-badge active">{t("setup.active")}</span>
          ) : primary ? (
            <span className="queue-badge active">{t("setup.recommended")}</span>
          ) : (
            <span className="pill">{m.size_gb} GB</span>
          )}
        </div>
        <p className="muted" style={{ fontSize: 13, margin: "6px 0" }}>{m.note}</p>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {m.capabilities.slice(0, 4).map((c) => (
            <span key={c} className="pill" style={{ fontSize: 11 }}>{c}</span>
          ))}
        </div>
        <div style={{ marginTop: 10 }}>
          {active ? (
            <span className="muted">{t("setup.inUse")}</span>
          ) : installed ? (
            <button className="btn" disabled={busy === m.model} onClick={() => activate(m.model)}>
              {busy === m.model ? t("setup.working") : t("setup.activate")}
            </button>
          ) : (
            <button className="btn" disabled={!!busy} onClick={() => install(m.model)}>
              {busy === m.model ? progress || t("setup.working") : `${t("setup.install")} (${m.size_gb} GB)`}
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div>
      <h1 className="page-title">{t("setup.title")}</h1>
      <p className="page-subtitle">{t("setup.subtitle")}</p>
      {error && <p className="error">{error}</p>}

      {/* Step 1 — status banner */}
      {status && (
        <div className="card" style={{ marginBottom: 16 }}>
          {status.configured ? (
            <p style={{ margin: 0 }}>
              ✅ {t("setup.ready")} <strong>{status.active_model}</strong>.{" "}
              {t("setup.readyHint")}
            </p>
          ) : status.ollama_ready ? (
            <p style={{ margin: 0 }}>👉 {t("setup.pickHint")}</p>
          ) : (
            <p style={{ margin: 0 }}>
              ⚠ {t("setup.ollamaOff")} <code>docker compose --profile ai up -d</code>
            </p>
          )}
        </div>
      )}

      {/* Step 2 — hardware */}
      {status && (
        <>
          <h2 className="page-title" style={{ fontSize: 18 }}>{t("setup.hardware")}</h2>
          <div className="cards" style={{ marginBottom: 8 }}>
            <div className="card">
              <div className="status-row"><span className="muted">CPU</span><span>{status.hardware.cpu_cores ?? "—"} core</span></div>
              <div className="status-row"><span className="muted">RAM</span><span>{gb(status.hardware.ram_total_mb)}</span></div>
              <div className="status-row">
                <span className="muted">GPU</span>
                <span>
                  {status.hardware.gpu && status.hardware.gpu.count > 0
                    ? status.hardware.gpu.devices.map((d) => d.name || "GPU").join(", ")
                    : t("setup.noGpu")}
                </span>
              </div>
              {status.recommendation.reason && (
                <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>{status.recommendation.reason}</p>
              )}
            </div>
          </div>
        </>
      )}

      {/* Step 3 — choose a model */}
      {status && (
        <>
          <h2 className="page-title" style={{ fontSize: 18, marginTop: 12 }}>{t("setup.chooseModel")}</h2>
          <div className="cards">
            {modelCard(status.recommendation.primary, true)}
            {status.recommendation.alternatives.map((m) => modelCard(m, false))}
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
            {t("setup.advancedHint")}
          </p>
        </>
      )}
    </div>
  );
}
