"use client";

import { useCallback, useEffect, useState } from "react";
import { WebConfig, fetchWebConfig, updateWebConfig } from "@/lib/api";

export default function SettingsPage() {
  const [cfg, setCfg] = useState<WebConfig | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setCfg(await fetchWebConfig());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load config");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const patch = (p: Partial<WebConfig>) =>
    setCfg((c) => (c ? { ...c, ...p } : c));

  const save = async () => {
    if (!cfg || busy) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const body: Partial<WebConfig> & { api_key?: string } = {
        enabled: cfg.enabled,
        provider: cfg.provider,
        url: cfg.url,
        max_results: cfg.max_results,
        fetch_timeout: cfg.fetch_timeout,
        allow_private_ips: cfg.allow_private_ips,
        allowlist: cfg.allowlist,
        denylist: cfg.denylist,
      };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      setCfg(await updateWebConfig(body));
      setApiKey("");
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  const csv = (arr: string[]) => arr.join(", ");
  const parseCsv = (s: string) =>
    s.split(",").map((x) => x.trim()).filter(Boolean);

  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <p className="page-subtitle">
        Runtime configuration (ROADMAP PR 15). Changes are stored server-side and
        take effect immediately — no restart, no .env edit.
      </p>

      {error && <p className="error">Error: {error}</p>}
      {!cfg ? (
        <p className="muted">Loading…</p>
      ) : (
        <div className="card" style={{ maxWidth: 640 }}>
          <h3 style={{ marginTop: 0 }}>🌐 Web tools</h3>

          <label className="setting-row">
            <span>Enabled</span>
            <input
              type="checkbox"
              checked={cfg.enabled}
              onChange={(e) => patch({ enabled: e.target.checked })}
            />
          </label>

          <label className="setting-row">
            <span>Search provider</span>
            <select
              value={cfg.provider}
              onChange={(e) => patch({ provider: e.target.value as WebConfig["provider"] })}
            >
              <option value="none">none (offline)</option>
              <option value="searxng">searxng</option>
            </select>
          </label>

          <label className="setting-row">
            <span>Search URL</span>
            <input
              value={cfg.url}
              placeholder="http://searxng:8080/search"
              onChange={(e) => patch({ url: e.target.value })}
            />
          </label>

          <label className="setting-row">
            <span>API key {cfg.has_api_key && <em className="muted">(set)</em>}</span>
            <input
              type="password"
              value={apiKey}
              placeholder={cfg.has_api_key ? "•••••• (leave blank to keep)" : "optional"}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>

          <label className="setting-row">
            <span>Max results</span>
            <input
              type="number"
              min={1}
              max={25}
              value={cfg.max_results}
              onChange={(e) => patch({ max_results: Number(e.target.value) })}
            />
          </label>

          <label className="setting-row">
            <span>Fetch timeout (s)</span>
            <input
              type="number"
              min={1}
              max={120}
              value={cfg.fetch_timeout}
              onChange={(e) => patch({ fetch_timeout: Number(e.target.value) })}
            />
          </label>

          <label className="setting-row">
            <span title="Dev only — enables SSRF; keep off in production">
              Allow private IPs
            </span>
            <input
              type="checkbox"
              checked={cfg.allow_private_ips}
              onChange={(e) => patch({ allow_private_ips: e.target.checked })}
            />
          </label>

          <label className="setting-row">
            <span>Allowlist (comma)</span>
            <input
              defaultValue={csv(cfg.allowlist)}
              placeholder="example.com, docs.python.org"
              onChange={(e) => patch({ allowlist: parseCsv(e.target.value) })}
            />
          </label>

          <label className="setting-row">
            <span>Denylist (comma)</span>
            <input
              defaultValue={csv(cfg.denylist)}
              onChange={(e) => patch({ denylist: parseCsv(e.target.value) })}
            />
          </label>

          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
            <button className="btn" onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
            {saved && <span className="muted">Saved ✓</span>}
          </div>

          {cfg.enabled && cfg.provider === "none" && (
            <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
              Web tools are on but no provider is set — search returns nothing. Start
              SearXNG (<code>docker compose --profile web up -d searxng</code>) and pick
              it above.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
