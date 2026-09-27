"use client";

import { useCallback, useEffect, useState } from "react";
import { WebConfig, fetchWebConfig, updateWebConfig } from "@/lib/api";
import { LanguageSelect, useI18n } from "@/lib/i18n";

export default function SettingsPage() {
  const { t } = useI18n();
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
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

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
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const csv = (arr: string[]) => arr.join(", ");
  const parseCsv = (s: string) =>
    s.split(",").map((x) => x.trim()).filter(Boolean);

  return (
    <div>
      <h1 className="page-title">{t("nav.settings")}</h1>
      <p className="page-subtitle">{t("set.subtitle")}</p>

      <div className="card" style={{ maxWidth: 640, marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>🗣 {t("set.language")}</h3>
        <label className="setting-row">
          <span>{t("set.languageHelp")}</span>
          <LanguageSelect />
        </label>
      </div>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}
      {!cfg ? (
        <p className="muted">{t("common.loading")}</p>
      ) : (
        <div className="card" style={{ maxWidth: 640 }}>
          <h3 style={{ marginTop: 0 }}>🌐 {t("set.web")}</h3>

          <label className="setting-row">
            <span>{t("v.enabled")}</span>
            <input
              type="checkbox"
              checked={cfg.enabled}
              onChange={(e) => patch({ enabled: e.target.checked })}
            />
          </label>

          <label className="setting-row">
            <span>{t("set.provider")}</span>
            <select
              value={cfg.provider}
              onChange={(e) => patch({ provider: e.target.value as WebConfig["provider"] })}
            >
              <option value="none">{t("set.providerNone")}</option>
              <option value="searxng">searxng</option>
            </select>
          </label>

          <label className="setting-row">
            <span>{t("set.url")}</span>
            <input
              value={cfg.url}
              placeholder="http://searxng:8080/search"
              onChange={(e) => patch({ url: e.target.value })}
            />
          </label>

          <label className="setting-row">
            <span>{t("set.apiKey")} {cfg.has_api_key && <em className="muted">({t("set.isSet")})</em>}</span>
            <input
              type="password"
              value={apiKey}
              placeholder={cfg.has_api_key ? t("set.keepKey") : t("set.optional")}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>

          <label className="setting-row">
            <span>{t("set.maxResults")}</span>
            <input
              type="number"
              min={1}
              max={25}
              value={cfg.max_results}
              onChange={(e) => patch({ max_results: Number(e.target.value) })}
            />
          </label>

          <label className="setting-row">
            <span>{t("set.timeout")}</span>
            <input
              type="number"
              min={1}
              max={120}
              value={cfg.fetch_timeout}
              onChange={(e) => patch({ fetch_timeout: Number(e.target.value) })}
            />
          </label>

          <label className="setting-row">
            <span title={t("set.privateHint")}>{t("set.private")}</span>
            <input
              type="checkbox"
              checked={cfg.allow_private_ips}
              onChange={(e) => patch({ allow_private_ips: e.target.checked })}
            />
          </label>

          <label className="setting-row">
            <span>{t("set.allow")}</span>
            <input
              defaultValue={csv(cfg.allowlist)}
              placeholder="example.com, docs.python.org"
              onChange={(e) => patch({ allowlist: parseCsv(e.target.value) })}
            />
          </label>

          <label className="setting-row">
            <span>{t("set.deny")}</span>
            <input
              defaultValue={csv(cfg.denylist)}
              onChange={(e) => patch({ denylist: parseCsv(e.target.value) })}
            />
          </label>

          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
            <button className="btn" onClick={save} disabled={busy}>
              {busy ? t("set.saving") : t("common.save")}
            </button>
            {saved && <span className="muted">{t("set.saved")} ✓</span>}
          </div>

          {cfg.enabled && cfg.provider === "none" && (
            <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
              {t("set.noProvider")} <code>docker compose --profile web up -d searxng</code>{" "}
              {t("set.noProvider2")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
