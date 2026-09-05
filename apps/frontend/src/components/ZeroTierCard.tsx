"use client";

import { useCallback, useEffect, useState } from "react";
import { ZeroTierStatus, authorizeZeroTier, fetchZeroTier } from "@/lib/api";

/** Optional ZeroTier overlay controller (ROADMAP PR 7). Renders nothing noisy
 *  when the controller is disabled — just a hint on how to enable it. */
export default function ZeroTierCard() {
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
      <h3>Overlay network — ZeroTier</h3>
      {!zt.controller_enabled ? (
        <p className="muted" style={{ fontSize: 13 }}>
          Controller disabled. Nodes still join the overlay via the installer. To
          manage members here, set <code>ATLAS_ZEROTIER_CONTROLLER_ENABLED=true</code>,
          an API token and a network id.
        </p>
      ) : (
        <>
          <div className="status-row">
            <span className="muted">Network</span>
            <span className="pill">{zt.network_id || "—"}</span>
          </div>
          <div className="status-row">
            <span className="muted">Members</span>
            <span className="pill">
              {zt.authorized_count}/{zt.member_count} authorized
            </span>
          </div>
          {zt.error && <p className="error">{zt.error}</p>}
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>IP</th>
                  <th>Online</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {zt.members.map((m) => (
                  <tr key={m.id}>
                    <td>{m.name || m.id}</td>
                    <td>{m.ip_assignments.join(", ") || "—"}</td>
                    <td>
                      <span className={`dot ${m.online ? "ok" : "bad"}`} />{" "}
                      {m.online ? "yes" : "no"}
                    </td>
                    <td>
                      <button
                        className={m.authorized ? "btn secondary" : "btn"}
                        disabled={busy}
                        onClick={() => toggle(m.id, !m.authorized)}
                      >
                        {m.authorized ? "Deauthorize" : "Authorize"}
                      </button>
                    </td>
                  </tr>
                ))}
                {zt.members.length === 0 && (
                  <tr><td colSpan={4} className="muted">No members.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
