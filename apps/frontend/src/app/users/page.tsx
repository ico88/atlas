"use client";

import { useCallback, useEffect, useState } from "react";
import { AppUser, createUser, fetchUsers, updateUser } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function UsersPage() {
  const { t, tv } = useI18n();
  const [users, setUsers] = useState<AppUser[]>([]);
  const [enforced, setEnforced] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await fetchUsers();
      setUsers(list.items);
      setEnforced(list.auth_enforced);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!email.trim() || password.length < 6 || busy) return;
    setBusy(true);
    setError(null);
    try {
      await createUser({
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
        role,
      });
      setEmail("");
      setPassword("");
      setFullName("");
      setRole("user");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setBusy(false);
    }
  };

  const patch = async (id: string, body: { role?: string; is_active?: boolean }) => {
    setError(null);
    try {
      await updateUser(id, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  return (
    <div>
      <h1 className="page-title">{t("nav.users")}</h1>
      <p className="page-subtitle">
        {t("users.subtitle")} <strong>{enforced ? t("users.on") : t("users.off")}</strong>.{" "}
        {t("users.enableWith")} <code>ATLAS_AUTH_ENFORCE=true</code> {t("users.afterAdmin")}
      </p>

      {error && <p className="error">{t("common.errorMsg", { error })}</p>}

      {!enforced && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid var(--warn)" }}>
          <span className="muted" style={{ fontSize: 13 }}>
            🔓 {t("users.openMode")} <code>ATLAS_AUTH_ENFORCE=true</code>{" "}
            {t("users.openMode2")}
          </span>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>{t("users.add")}</h3>
        <div style={{ display: "grid", gap: 8, maxWidth: 460 }}>
          <input
            value={email}
            placeholder="email@example.com"
            onChange={(e) => setEmail(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={fullName}
            placeholder={t("users.namePh")}
            onChange={(e) => setFullName(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8 }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              value={password}
              type="password"
              placeholder={t("users.passwordPh")}
              onChange={(e) => setPassword(e.target.value)}
              style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="model-select"
              style={{ maxWidth: "none" }}
            >
              <option value="user">{t("v.user")}</option>
              <option value="admin">{t("v.admin")}</option>
            </select>
          </div>
          <button
            className="btn"
            onClick={submit}
            disabled={busy || !email.trim() || password.length < 6}
          >
            {t("users.create")}
          </button>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        {users.length === 0 ? (
          <p className="muted">{t("users.none")}</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>{t("auth.email")}</th>
                <th>{t("common.name")}</th>
                <th>{t("users.role")}</th>
                <th>{t("users.active")}</th>
                <th>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.full_name ?? "—"}</td>
                  <td>
                    <span className={`queue-badge ${u.role === "admin" ? "active" : "idle"}`}>
                      {tv(u.role)}
                    </span>
                  </td>
                  <td>
                    <span className={`dot ${u.is_active ? "ok" : "bad"}`} />{" "}
                    {u.is_active ? t("common.yes") : t("common.no")}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button
                        className="btn secondary"
                        onClick={() =>
                          patch(u.id, { role: u.role === "admin" ? "user" : "admin" })
                        }
                      >
                        {u.role === "admin" ? t("users.makeUser") : t("users.makeAdmin")}
                      </button>
                      <button
                        className="btn secondary"
                        onClick={() => patch(u.id, { is_active: !u.is_active })}
                      >
                        {u.is_active ? t("users.deactivate") : t("users.activate")}
                      </button>
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
