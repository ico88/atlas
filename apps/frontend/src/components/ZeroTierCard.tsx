"use client";

import { useCallback, useEffect, useState } from "react";
import { ZeroTierStatus, authorizeZeroTier, fetchZeroTier } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Optional ZeroTier overlay controller (ROADMAP PR 7). Renders nothing noisy
 *  when the controller is disabled — just a hint on how to enable it. */
export default function ZeroTierCard() {
  const { t } = useI18n();
  const [zt, setZt] = useState<ZeroTierStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setZt(await fetchZeroTier());
    } catch {
      /* controller unreachable */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!zt) return null;

  const toggle = async (id: string, authorized: boolean) => {
    setBusy(true);
    try {
      await authorizeZeroTier(id, authorized);
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3>{t("zt.title")}</h3>
      {!zt.controller_enabled ? (
        <p className="muted" style={{ fontSize: 13 }}>
          {t("zt.disabled1")} <code>ATLAS_ZEROTIER_CONTROLLER_ENABLED=true</code>,{" "}
          {t("zt.disabled2")}
        </p>
      ) : (
        <>
          <div className="status-row">
            <span className="muted">{t("zt.network")}</span>
            <span className="pill">{zt.network_id || "—"}</span>
          </div>
          <div className="status-row">
            <span className="muted">{t("zt.members")}</span>
            <span className="pill">
              {t("zt.authorizedCount", { n: zt.authorized_count, total: zt.member_count })}
            </span>
          </div>
          {zt.error && <p className="error">{zt.error}</p>}
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>{t("zt.member")}</th>
                  <th>IP</th>
                  <th>{t("common.online")}</th>
                  <th>{t("zt.access")}</th>
                </tr>
              </thead>
              <tbody>
                {zt.members.map((m) => (
                  <tr key={m.id}>
                    <td>{m.name || m.id}</td>
                    <td>{m.ip_assignments.join(", ") || "—"}</td>
                    <td>
                      <span className={`dot ${m.online ? "ok" : "bad"}`} />{" "}
                      {m.online ? t("common.yes") : t("common.no")}
                    </td>
                    <td>
                      <button
                        className={m.authorized ? "btn secondary" : "btn"}
                        disabled={busy}
                        onClick={() => toggle(m.id, !m.authorized)}
                      >
                        {m.authorized ? t("wizard.deauth") : t("wizard.auth")}
                      </button>
                    </td>
                  </tr>
                ))}
                {zt.members.length === 0 && (
                  <tr><td colSpan={4} className="muted">{t("zt.noMembers")}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
