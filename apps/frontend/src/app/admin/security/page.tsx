"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AuditEntry,
  MfaSetup,
  SecretMeta,
  deleteSecret,
  fetchAudit,
  fetchSecrets,
  mfaDisable,
  mfaEnable,
  mfaSetup,
  revealSecret,
  upsertSecret,
  verifyAudit,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

export default function SecurityPage() {
  const { t } = useI18n();
  const { user, refresh } = useAuth();
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [integrity, setIntegrity] = useState<{ ok: boolean; broken_at?: number } | null>(null);
  const [secrets, setSecrets] = useState<SecretMeta[]>([]);
  const [newSecret, setNewSecret] = useState({ name: "", value: "" });
  const [revealed, setRevealed] = useState<Record<string, string>>({});

  const loadAudit = useCallback(async () => {
    try {
      setAudit((await fetchAudit()).items);
    } catch {
      /* not admin / auth off */
    }
  }, []);

  const loadSecrets = useCallback(async () => {
    try {
      setSecrets((await fetchSecrets()).items);
    } catch {
      /* not admin / auth off */
    }
  }, []);

  useEffect(() => {
    loadAudit();
    loadSecrets();
  }, [loadAudit, loadSecrets]);

  const enabled = !!user?.mfa_enabled;

  const start = async () => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      setSetup(await mfaSetup());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  };

  const enable = async () => {
    setBusy(true);
    setErr(null);
    try {
      await mfaEnable(code.trim());
      await refresh();
      setSetup(null);
      setCode("");
      setMsg(t("sec.mfaEnabled"));
    } catch {
      setErr(t("sec.badCode"));
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    setErr(null);
    try {
      await mfaDisable(code.trim());
      await refresh();
      setCode("");
      setMsg(t("sec.mfaDisabled"));
    } catch {
      setErr(t("sec.badCode"));
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    try {
      const r = await verifyAudit();
      setIntegrity(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("admin.security")}</h1>
      <p className="page-subtitle">{t("sec.subtitle")}</p>
      {err && <p className="error">{err}</p>}
      {msg && <p className="muted">✅ {msg}</p>}

      {/* MFA */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="status-row">
          <strong>{t("sec.mfa")}</strong>
          <span className={`queue-badge ${enabled ? "active" : "idle"}`}>
            {enabled ? t("sec.on") : t("sec.off")}
          </span>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>{t("sec.mfaHelp")}</p>

        {!enabled && !setup && (
          <button className="btn" disabled={busy} onClick={start}>
            {t("sec.enableMfa")}
          </button>
        )}

        {!enabled && setup && (
          <div className="card" style={{ marginTop: 10 }}>
            <p className="muted" style={{ fontSize: 13 }}>{t("sec.scanHint")}</p>
            <p style={{ fontSize: 12 }}>{t("sec.secret")}:</p>
            <pre style={{ overflow: "auto" }}>{setup.secret}</pre>
            <p className="muted" style={{ fontSize: 11, wordBreak: "break-all" }}>{setup.otpauth_uri}</p>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <input
                value={code}
                placeholder={t("sec.codePlaceholder")}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                style={{ flex: "1 1 140px" }}
              />
              <button className="btn" disabled={busy || code.length < 6} onClick={enable}>
                {t("sec.confirmEnable")}
              </button>
            </div>
          </div>
        )}

        {enabled && (
          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <input
              value={code}
              placeholder={t("sec.codePlaceholder")}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              style={{ flex: "1 1 140px" }}
            />
            <button className="btn secondary" disabled={busy || code.length < 6} onClick={disable}>
              {t("sec.disableMfa")}
            </button>
          </div>
        )}
      </div>

      {/* Secret manager */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="status-row">
          <strong>{t("sec.secrets")}</strong>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>{t("sec.secretsHelp")}</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
          <input
            value={newSecret.name}
            placeholder="NAME (es. OPENAI_API_KEY)"
            onChange={(e) => setNewSecret({ ...newSecret, name: e.target.value })}
            style={{ flex: "1 1 160px" }}
          />
          <input
            value={newSecret.value}
            placeholder={t("sec.value")}
            type="password"
            onChange={(e) => setNewSecret({ ...newSecret, value: e.target.value })}
            style={{ flex: "1 1 160px" }}
          />
          <button
            className="btn"
            disabled={!newSecret.name.trim() || !newSecret.value}
            onClick={async () => {
              try {
                await upsertSecret(newSecret.name.trim(), newSecret.value);
                setNewSecret({ name: "", value: "" });
                await loadSecrets();
              } catch (e) {
                setErr(e instanceof Error ? e.message : "error");
              }
            }}
          >
            {t("common.save")}
          </button>
        </div>
        {secrets.map((s) => (
          <div className="status-row" key={s.name}>
            <span className="pill">{s.name}</span>
            <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {revealed[s.name] ? (
                <code style={{ fontSize: 12 }}>{revealed[s.name]}</code>
              ) : (
                <button
                  className="btn secondary"
                  onClick={async () => {
                    const r = await revealSecret(s.name);
                    setRevealed((p) => ({ ...p, [s.name]: r.value }));
                  }}
                >
                  {t("sec.reveal")}
                </button>
              )}
              <button
                className="btn secondary"
                onClick={async () => {
                  await deleteSecret(s.name);
                  await loadSecrets();
                }}
              >
                {t("common.delete")}
              </button>
            </span>
          </div>
        ))}
        {secrets.length === 0 && <p className="muted">{t("sec.noSecrets")}</p>}
      </div>

      {/* Audit log */}
      <div className="status-row">
        <h2 className="page-title" style={{ fontSize: 20 }}>{t("sec.audit")}</h2>
        <button className="btn secondary" onClick={verify}>{t("sec.verify")}</button>
      </div>
      <p className="page-subtitle">{t("sec.auditHelp")}</p>
      {integrity && (
        <p className={integrity.ok ? "muted" : "error"}>
          {integrity.ok
            ? `✅ ${t("sec.intact")}`
            : `⚠ ${t("sec.tampered")} (#${integrity.broken_at})`}
        </p>
      )}
      <div style={{ overflowX: "auto" }}>
        <table className="data">
          <thead>
            <tr>
              <th>#</th>
              <th>{t("sec.when")}</th>
              <th>{t("sec.actor")}</th>
              <th>{t("sec.action")}</th>
              <th>{t("sec.target")}</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((e) => (
              <tr key={e.seq}>
                <td>{e.seq}</td>
                <td>{new Date(e.created_at).toLocaleString()}</td>
                <td>{e.actor}</td>
                <td><span className="pill">{e.action}</span></td>
                <td>{e.target || "—"}</td>
              </tr>
            ))}
            {audit.length === 0 && (
              <tr><td colSpan={5} className="muted">{t("sec.noAudit")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
