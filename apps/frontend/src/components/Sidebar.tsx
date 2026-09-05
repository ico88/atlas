"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Logo from "@/components/Logo";
import { Lang, useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

const NAV_GROUPS: { section?: string; items: { href: string; key: string }[] }[] = [
  {
    items: [
      { href: "/", key: "nav.chat" },
      { href: "/dashboard", key: "nav.dashboard" },
    ],
  },
  {
    section: "nav.section.work",
    items: [
      { href: "/queries", key: "nav.queries" },
      { href: "/queue", key: "nav.queue" },
      { href: "/tasks", key: "nav.tasks" },
      { href: "/knowledge", key: "nav.knowledge" },
      { href: "/environments", key: "nav.environments" },
    ],
  },
  {
    section: "nav.section.fleet",
    items: [
      { href: "/nodes", key: "nav.nodes" },
      { href: "/fleet", key: "nav.fleet" },
      { href: "/compliance", key: "nav.compliance" },
      { href: "/resources", key: "nav.resources" },
      { href: "/models", key: "nav.models" },
      { href: "/system", key: "nav.system" },
    ],
  },
  {
    section: "nav.section.govern",
    items: [
      { href: "/maintenance", key: "nav.maintenance" },
      { href: "/improvements", key: "nav.improvements" },
      { href: "/reviews", key: "nav.reviews" },
      { href: "/evals", key: "nav.evals" },
      { href: "/escalation", key: "nav.escalation" },
    ],
  },
  {
    section: "nav.section.admin",
    items: [
      { href: "/users", key: "nav.users" },
      { href: "/settings", key: "nav.settings" },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { t, lang, setLang } = useI18n();
  const { user, logout } = useAuth();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <>
      {/* Mobile top bar (hidden on desktop via CSS). */}
      <header className="topbar">
        <button
          className="hamburger"
          aria-label="Toggle navigation"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          ☰
        </button>
        <span className="topbar-logo">
          <Logo size={24} />
          ATLAS
        </span>
      </header>

      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-row">
            <Logo size={34} />
            <span className="logo">ATLAS</span>
          </div>
          <span className="tagline">{t("sidebar.tagline")}</span>
        </div>
        <nav className="nav">
          {NAV_GROUPS.map((group, gi) => (
            <div key={group.section ?? gi} className="nav-group">
              {group.section && <div className="nav-section">{t(group.section)}</div>}
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={pathname === item.href ? "active" : ""}
                >
                  {t(item.key)}
                </Link>
              ))}
            </div>
          ))}
        </nav>
        <div style={{ marginTop: "auto" }}>
          <label className="lang-switch">
            <span className="muted">🌐 {t("sidebar.language")}</span>
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as Lang)}
              aria-label={t("sidebar.language")}
            >
              <option value="it">Italiano</option>
              <option value="en">English</option>
            </select>
          </label>
          <div className="account">
            {user ? (
              <>
                <span className="muted" style={{ fontSize: 12 }}>
                  {t("auth.signedInAs")} <strong>{user.email}</strong>
                  {user.role === "admin" ? " · admin" : ""}
                </span>
                <button className="btn secondary" style={{ fontSize: 12 }} onClick={logout}>
                  {t("auth.logout")}
                </button>
              </>
            ) : (
              <Link href="/login" className="btn secondary" style={{ fontSize: 12, textAlign: "center" }}>
                {t("auth.login")}
              </Link>
            )}
          </div>
          <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            {t("sidebar.footer")}
          </div>
        </div>
      </aside>
    </>
  );
}
