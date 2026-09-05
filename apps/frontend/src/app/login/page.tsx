"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Logo from "@/components/Logo";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { t } = useI18n();
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!email.trim() || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.push("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 380, margin: "8vh auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <Logo size={36} />
        <h1 className="page-title" style={{ margin: 0 }}>
          {t("auth.title")}
        </h1>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="card">
        <div style={{ display: "grid", gap: 10 }}>
          <label className="muted" style={{ fontSize: 13 }}>
            {t("auth.email")}
            <input
              value={email}
              type="email"
              autoComplete="username"
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              style={{ width: "100%", padding: "10px 12px", borderRadius: 8, marginTop: 4 }}
            />
          </label>
          <label className="muted" style={{ fontSize: 13 }}>
            {t("auth.password")}
            <input
              value={password}
              type="password"
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              style={{ width: "100%", padding: "10px 12px", borderRadius: 8, marginTop: 4 }}
            />
          </label>
          <button
            className="btn"
            onClick={submit}
            disabled={busy || !email.trim() || !password}
          >
            {busy ? "…" : t("auth.login")}
          </button>
        </div>
      </div>
    </div>
  );
}
