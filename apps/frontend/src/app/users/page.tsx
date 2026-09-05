"use client";

import { useCallback, useEffect, useState } from "react";
import { AppUser, createUser, fetchUsers, updateUser } from "@/lib/api";

export default function UsersPage() {
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
      setError(e instanceof Error ? e.message : "failed to load users");
    }
  }, []);

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
      setError(e instanceof Error ? e.message : "create failed");
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
      setError(e instanceof Error ? e.message : "update failed");
    }
  };

  return (
    <div>
      <h1 className="page-title">Users</h1>
      <p className="page-subtitle">
        Roles &amp; access (ROADMAP PR 27). <strong>admin</strong> manages everything;{" "}
        <strong>user</strong> just uses the app. Enforcement is currently{" "}
        <strong>{enforced ? "ON" : "OFF"}</strong> — turn it on with{" "}
        <code>ATLAS_AUTH_ENFORCE=true</code> once you&apos;ve created an admin.
      </p>

      {error && <p className="error">Error: {error}</p>}

      {!enforced && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid var(--warn)" }}>
          <span className="muted" style={{ fontSize: 13 }}>
            🔓 Open mode: the app is unauthenticated and everyone acts as admin.
            Create an admin here, then set <code>ATLAS_AUTH_ENFORCE=true</code> to
            require login.
          </span>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Add a user</h3>
        <div style={{ display: "grid", gap: 8, maxWidth: 460 }}>
          <input
            value={email}
            placeholder="email@example.com"
            onChange={(e) => setEmail(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8 }}
          />
          <input
            value={fullName}
            placeholder="Full name (optional)"
            onChange={(e) => setFullName(e.target.value)}
            style={{ padding: "8px 10px", borderRadius: 8 }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              value={password}
              type="password"
              placeholder="Password (min 6)"
              onChange={(e) => setPassword(e.target.value)}
              style={{ flex: "1 1 200px", padding: "8px 10px", borderRadius: 8 }}
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="model-select"
              style={{ maxWidth: "none" }}
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <button
            className="btn"
            onClick={submit}
            disabled={busy || !email.trim() || password.length < 6}
          >
            Create user
          </button>
        </div>
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        {users.length === 0 ? (
          <p className="muted">No users yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>{u.full_name ?? "—"}</td>
                  <td>
                    <span className={`queue-badge ${u.role === "admin" ? "active" : "idle"}`}>
                      {u.role}
                    </span>
                  </td>
                  <td>
                    <span className={`dot ${u.is_active ? "ok" : "bad"}`} />{" "}
                    {u.is_active ? "yes" : "no"}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button
                        className="btn secondary"
                        onClick={() =>
                          patch(u.id, { role: u.role === "admin" ? "user" : "admin" })
                        }
                      >
                        {u.role === "admin" ? "Make user" : "Make admin"}
                      </button>
                      <button
                        className="btn secondary"
                        onClick={() => patch(u.id, { is_active: !u.is_active })}
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
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
