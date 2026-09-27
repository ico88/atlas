"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ModelInfo,
  deleteModel,
  fetchDefaultModel,
  fetchHardware,
  fetchModels,
  fetchPullStatus,
  pullModel,
  refreshModels,
  setDefaultModel,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

// Curated open models that run locally via Ollama, far better than llama3.2:1b.
// Sizes are approximate download sizes; on a CPU-only host smaller = faster.
const RECOMMENDED: { name: string; size: string; note: string; tier: string; family?: string }[] = [
  {
    name: "deepseek-r1:1.5b",
    size: "~1.1 GB",
    note: "models.rec.r1small",
    tier: "fast",
    family: "DeepSeek",
  },
  {
    name: "deepseek-r1:8b",
    size: "~4.9 GB",
    note: "models.rec.r1big",
    tier: "quality",
    family: "DeepSeek",
  },
  { name: "qwen2.5:3b", size: "~2 GB", note: "models.rec.qwen3", tier: "balanced" },
  { name: "llama3.2:3b", size: "~2 GB", note: "models.rec.llama3", tier: "fast" },
  { name: "gemma2:2b", size: "~1.6 GB", note: "models.rec.gemma2", tier: "fast" },
  { name: "phi3.5", size: "~2.2 GB", note: "models.rec.phi", tier: "balanced" },
  { name: "qwen2.5:7b", size: "~4.7 GB", note: "models.rec.qwen7", tier: "quality" },
  { name: "mistral:7b", size: "~4.1 GB", note: "models.rec.mistral", tier: "quality" },
];

export default function ModelsPage() {
  const { t, tv } = useI18n();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [hardware, setHardware] = useState<Record<string, unknown> | null>(null);
  const [defaultModel, setDefault] = useState("");
  const [pullName, setPullName] = useState("");
  const [pulls, setPulls] = useState<Record<string, { state: string; status?: string; completed?: number; total?: number }>>({});
  const [wantDefault, setWantDefault] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, hw, def] = await Promise.all([
        fetchModels(),
        fetchHardware(),
        fetchDefaultModel(),
      ]);
      setModels(m.items);
      setHardware(hw);
      setDefault(def.default_model || "");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll pull progress while any download is active.
  useEffect(() => {
    const active = Object.values(pulls).some((p) => p.state === "pulling" || p.state === "starting");
    if (!active) return;
    const id = setInterval(async () => {
      try {
        const st = (await fetchPullStatus()).items;
        setPulls(st);
        // A "download & use" finished -> make it the default, then stop wanting it.
        for (const name of wantDefault) {
          if (st[name]?.state === "done") {
            try {
              const r = await setDefaultModel(name);
              setDefault(r.default_model);
            } catch {
              /* ignore */
            }
            setWantDefault((w) => w.filter((n) => n !== name));
          }
        }
        if (Object.values(st).every((p) => p.state === "done" || p.state === "error")) {
          load();
        }
      } catch {
        /* ignore */
      }
    }, 1500);
    return () => clearInterval(id);
  }, [pulls, load, wantDefault]);

  const makeDefault = async (name: string) => {
    try {
      const r = await setDefaultModel(name);
      setDefault(r.default_model);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  };

  const pull = async (name: string, asDefault = false) => {
    const clean = name.trim();
    if (!clean) return;
    try {
      await pullModel(clean);
      setPulls((p) => ({ ...p, [clean]: { state: "starting", status: "queued" } }));
      if (asDefault) setWantDefault((w) => (w.includes(clean) ? w : [...w, clean]));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  };

  const doPull = async () => {
    await pull(pullName);
    setPullName("");
  };

  const isPulling = (name: string) =>
    pulls[name]?.state === "pulling" || pulls[name]?.state === "starting";

  const doDelete = async (name: string) => {
    if (!confirm(t("models.confirmDelete", { name }))) return;
    try {
      const m = await deleteModel(name);
      setModels(m.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    }
  };

  const doRefresh = async () => {
    setBusy(true);
    try {
      const m = await refreshModels();
      setModels(m.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const hw = hardware ?? {};

  function gpuSummary(gpu: unknown): string {
    if (!gpu || typeof gpu !== "object") return t("models.none");
    const g = gpu as { count?: number; devices?: Array<{ name?: string; vendor?: string }> };
    if (!g.count) return t("models.none");
    const first = g.devices?.[0];
    const label = first?.name || first?.vendor || "GPU";
    return g.count > 1 ? `${label} (+${g.count - 1})` : label;
  }

  return (
    <div>
      <h1 className="page-title">{t("nav.models")}</h1>
      <p className="page-subtitle">{t("models.subtitle")}</p>

      {error && <p className="error">{error}</p>}

      <div className="cards" style={{ marginBottom: 20 }}>
        <div className="card">
          <h3>{t("models.hardware")}</h3>
          <div className="status-row">
            <span className="muted">{t("models.platform")}</span>
            <span>
              {String(hw.platform ?? "—")} {String(hw.arch ?? "")}
            </span>
          </div>
          <div className="status-row">
            <span className="muted">{t("models.cpuCores")}</span>
            <span className="pill">{String(hw.cpu_cores ?? "—")}</span>
          </div>
          <div className="status-row">
            <span className="muted">{t("models.ramTotal")}</span>
            <span className="pill">
              {hw.ram_total_mb ? `${hw.ram_total_mb} MB` : "—"}
            </span>
          </div>
          <div className="status-row">
            <span className="muted">GPU</span>
            <span>{gpuSummary(hw.gpu)}</span>
          </div>
          <div className="status-row">
            <span className="muted">{t("models.ollamaBackend")}</span>
            <span className="pill">{String(hw.recommended_ollama_backend ?? "—")}</span>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("models.recommended")}</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          {t("models.recommendedHelp")}
        </p>
        <div className="rec-grid">
          {RECOMMENDED.map((r) => {
            const installed = models.some((m) => m.name === r.name && m.available);
            const pulling = isPulling(r.name);
            return (
              <div key={r.name} className={`rec-card tier-${r.tier}`}>
                <div className="rec-head">
                  <strong>{r.name}</strong>
                  <div style={{ display: "flex", gap: 6 }}>
                    {r.family && <span className="pill">{r.family}</span>}
                    <span className="pill">{r.size}</span>
                  </div>
                </div>
                <div className="muted" style={{ fontSize: 12, margin: "4px 0 10px" }}>
                  {t(r.note)}
                </div>
                {installed ? (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span className="queue-badge active">{t("models.installed")}</span>
                    {r.name !== defaultModel && (
                      <button className="btn secondary" onClick={() => makeDefault(r.name)}>
                        {t("models.useDefault")}
                      </button>
                    )}
                    {r.name === defaultModel && <span className="pill">⭐ {t("models.default")}</span>}
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <button className="btn" disabled={pulling} onClick={() => pull(r.name, true)}>
                      {pulling ? t("models.downloading") : t("models.downloadUse")}
                    </button>
                    <button
                      className="btn secondary"
                      disabled={pulling}
                      onClick={() => pull(r.name, false)}
                    >
                      {t("models.download")}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("models.any")}</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          {t("models.anyHelp")} <code>deepseek-r1:8b</code>, <code>qwen2.5:3b</code>,{" "}
          <code>gemma2:2b</code>.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={pullName}
            placeholder="model:tag"
            onChange={(e) => setPullName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doPull()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={doPull} disabled={!pullName.trim()}>
            {t("models.download")}
          </button>
        </div>
        {Object.entries(pulls).map(([name, p]) => (
          <div key={name} className="queue-item" style={{ marginTop: 8 }}>
            <strong>{name}</strong>{" "}
            <span className="meta">
              {tv(p.state)}
              {p.status ? ` · ${p.status}` : ""}
              {p.completed && p.total
                ? ` · ${Math.round((p.completed / p.total) * 100)}%`
                : ""}
            </span>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ color: "var(--muted)" }}>
          {t("models.registered")}{" "}
          {defaultModel && <span className="pill">{t("models.default")}: {defaultModel}</span>}
        </h3>
        <button className="btn secondary" onClick={doRefresh} disabled={busy}>
          {busy ? t("models.refreshing") : t("models.refresh")}
        </button>
      </div>

      <div className="card" style={{ marginTop: 10, overflowX: "auto" }}>
        {models.length === 0 ? (
          <p className="muted">
            {t("models.empty")}
          </p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>{t("common.name")}</th>
                <th>{t("models.provider")}</th>
                <th>{t("models.family")}</th>
                <th>{t("models.context")}</th>
                <th>{t("models.available")}</th>
                <th>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    {m.name === defaultModel ? "⭐ " : ""}
                    {m.name}
                  </td>
                  <td>{m.provider}</td>
                  <td>{m.family ?? "—"}</td>
                  <td>{m.context_length ?? "—"}</td>
                  <td>
                    <span className={`dot ${m.available ? "ok" : "bad"}`} />{" "}
                    {m.available ? t("common.yes") : t("common.no")}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      {m.name !== defaultModel && (
                        <button className="btn secondary" onClick={() => makeDefault(m.name)}>
                          {t("models.setDefault")}
                        </button>
                      )}
                      {m.provider === "ollama" && (
                        <button className="btn secondary" onClick={() => doDelete(m.name)}>
                          {t("common.delete")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
