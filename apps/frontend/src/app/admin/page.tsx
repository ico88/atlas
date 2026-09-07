"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SloReport, fetchSlo } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

type Card = { href: string; icon: string; titleKey: string; descKey: string };

const CARDS: Card[] = [
  { href: "/users", icon: "👥", titleKey: "admin.users", descKey: "admin.users.desc" },
  { href: "/admin/security", icon: "🔒", titleKey: "admin.security", descKey: "admin.security.desc" },
  { href: "/settings", icon: "⚙️", titleKey: "admin.settings", descKey: "admin.settings.desc" },
  { href: "/system", icon: "❤️", titleKey: "admin.system", descKey: "admin.system.desc" },
];

export default function AdminPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [slo, setSlo] = useState<SloReport | null>(null);

  useEffect(() => {
    fetchSlo().then(setSlo).catch(() => {});
  }, []);

  return (
    <div>
      <h1 className="page-title">{t("admin.title")}</h1>
      <p className="page-subtitle">{t("admin.subtitle")}</p>

      {slo && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="status-row">
            <strong>{t("admin.slo")}</strong>
            <span className={`queue-badge ${slo.ok ? "active" : "idle"}`}>
              {slo.ok ? t("admin.sloOk") : `${slo.alerts.length} ${t("admin.sloAlerts")}`}
            </span>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6 }}>
            {slo.slos.map((s) => (
              <span key={s.name} className="pill" style={{ fontSize: 12 }}>
                <span className={`dot ${s.ok ? "ok" : "bad"}`} /> {s.name}:{" "}
                {s.unit === "bool" ? (s.value ? "ok" : "down") : `${Math.round(s.value * 100)}%`}
              </span>
            ))}
          </div>
        </div>
      )}

      {user && (
        <p className="muted" style={{ marginBottom: 16 }}>
          {t("auth.signedInAs")} <strong>{user.email}</strong> · {user.role}
          {" · "}
          {user.mfa_enabled ? `🔒 ${t("admin.mfaOn")}` : `⚠ ${t("admin.mfaOff")}`}
        </p>
      )}

      <div className="admin-grid">
        {CARDS.map((c) => (
          <Link key={c.href} href={c.href} className="admin-card">
            <span className="admin-card-icon">{c.icon}</span>
            <div>
              <strong>{t(c.titleKey)}</strong>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>{t(c.descKey)}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
