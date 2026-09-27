"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Environment,
  EnvironmentSnapshot,
  createEnvironment,
  fetchEnvironments,
  fetchSnapshots,
  restoreSnapshot,
  snapshotEnvironment,
  updateEnvironment,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function EnvironmentsPage() {
  const { t, tv } = useI18n();
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [selected, setSelected] = useState<Environment | null>(null);
  const [snaps, setSnaps] = useState<EnvironmentSnapshot[]>([]);
  const [name, setName] = useState("");
  const [manifestText, setManifestText] = useState("{}");
  const [varsText, setVarsText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEnvs((await fetchEnvironments()).items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const open = useCallback(async (env: Environment) => {
    setSelected(env);
    setManifestText(JSON.stringify(env.manifest ?? {}, null, 2));
    setVarsText(JSON.stringify(env.variables ?? {}, null, 2));
    try {
      setSnaps((await fetchSnapshots(env.id)).items);
    } catch {
      setSnaps([]);
    }
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    try {
      const env = await createEnvironment({ name: name.trim() });
      setName("");
      await load();
      await open(env);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  const parse = (s: string): Record<string, unknown> => {
    try {
      const v = JSON.parse(s);
      return typeof v === "object" && v ? v : {};
    } catch {
      throw new Error(t("common.invalidJson"));
    }
  };

  const saveManifest = async () => {
    if (!selected) return;
    try {
      const env = await updateEnvironment(selected.id, {
        manifest: parse(manifestText),
        variables: parse(varsText),
      });
      setSelected(env);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  const snapshot = async () => {
    if (!selected) return;
    await snapshotEnvironment(selected.id);
    setSnaps((await fetchSnapshots(selected.id)).items);
  };

  const restore = async (sid: string) => {
    const env = await restoreSnapshot(sid);
    await open(env);
    await load();
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.environments")}</h1>
      <p className="page-subtitle">{t("env.subtitle")}</p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={name}
            placeholder={t("env.namePh")}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            style={{ flex: 1, padding: "8px 10px", borderRadius: 8 }}
          />
          <button className="btn" onClick={create} disabled={!name.trim()}>
            {t("common.create")}
          </button>
        </div>
      </div>

      <div className="chat-layout">
        <div className="convo-list">
          {envs.length === 0 && <p className="muted">{t("env.none")}</p>}
          {envs.map((e) => (
            <div
              key={e.id}
              className={`convo-item ${selected?.id === e.id ? "active" : ""}`}
              onClick={() => open(e)}
            >
              {e.name}{" "}
              <span className={`queue-badge ${e.status === "ACTIVE" ? "active" : "idle"}`}>
                {tv(e.status)}
              </span>
            </div>
          ))}
        </div>

        <div className="chat-main" style={{ padding: 16, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">{t("env.select")}</p>
          ) : (
            <div>
              <h3 style={{ marginTop: 0 }}>
                {selected.name} <span className="muted">/{selected.slug}</span>
              </h3>
              <label className="muted" style={{ fontSize: 13 }}>{t("env.manifest")}</label>
              <textarea
                value={manifestText}
                onChange={(e) => setManifestText(e.target.value)}
                rows={6}
                style={{ width: "100%", fontFamily: "monospace", fontSize: 13, marginBottom: 8 }}
              />
              <label className="muted" style={{ fontSize: 13 }}>{t("env.variables")}</label>
              <textarea
                value={varsText}
                onChange={(e) => setVarsText(e.target.value)}
                rows={5}
                style={{ width: "100%", fontFamily: "monospace", fontSize: 13 }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <button className="btn" onClick={saveManifest}>{t("common.save")}</button>
                <button className="btn secondary" onClick={snapshot}>{t("env.snapshot")}</button>
              </div>

              <h3 style={{ fontSize: 14, marginTop: 18 }}>{t("env.snapshots")}</h3>
              {snaps.length === 0 ? (
                <p className="muted">{t("env.noSnapshots")}</p>
              ) : (
                snaps.map((s) => (
                  <div key={s.id} className="queue-item" style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>
                      {s.name || s.id.slice(0, 8)}{" "}
                      <span className="meta">
                        {s.stats ? t("env.stats", { tasks: s.stats.tasks ?? 0, mem: s.stats.memories ?? 0 }) : ""}
                      </span>
                    </span>
                    <button className="btn secondary" onClick={() => restore(s.id)}>
                      {t("env.restore")}
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
