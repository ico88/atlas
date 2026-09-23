"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Logo from "@/components/Logo";
import { Lang, useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

// ATLAS Control (admin cockpit) navigation. ALMA (the chat) is reached via the
// "← ALMA" link, not listed here — keeping the two shells cleanly separated.
const NAV_GROUPS: { section?: string; items: { href: string; key: string }[] }[] = [
  {
    items: [
      { href: "/dashboard", key: "nav.dashboard" },
      { href: "/autopilot", key: "nav.autopilot" },
      { href: "/setup", key: "nav.setup" },
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
      { href: "/runtimes", key: "nav.runtimes" },
      { href: "/system", key: "nav.system" },
    ],
  },
  {
    section: "nav.section.govern",
    items: [
      { href: "/maintenance", key: "nav.maintenance" },
      { href: "/improvements", key: "nav.improvements" },
      { href: "/finetune", key: "nav.finetune" },
      { href: "/reviews", key: "nav.reviews" },
      { href: "/evals", key: "nav.evals" },
      { href: "/escalation", key: "nav.escalation" },
    ],
  },
  {
    section: "nav.section.admin",
    items: [
      { href: "/admin", key: "nav.admin" },
      { href: "/users", key: "nav.users" },
      { href: "/admin/security", key: "nav.security" },
      { href: "/settings", key: "nav.settings" },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { t, lang, setLang } = useI18n();
  const { user, logout } = useAuth();

  // ALMA = the clean conversational shell (the chat, `/`); everything else is
  // ATLAS Control, the technical cockpit. The two shells share this component
  // but show completely different chrome (SPEC §2, §3, §25).
  const isAlma = pathname === "/" || pathname === "/login";
  const brand = isAlma ? "ALMA" : "ATLAS Control";

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
          {brand}
        </span>
      </header>

      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <aside className={`sidebar ${isAlma ? "sidebar-alma" : ""} ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-row">
            <Logo size={34} />
            <span className="logo">{brand}</span>
          </div>
          <span className="tagline">
            {isAlma ? t("sidebar.tagline") : t("sidebar.controlTagline")}
          </span>
        </div>
        {isAlma ? (
          // ALMA: keep it clean — conversations live in the chat itself; the only
          // navigation here is the doorway into the technical cockpit.
          <nav className="nav">
            <div className="nav-group">
              <Link href="/dashboard" className="control-entry">
                ⚙ {t("sidebar.openControl")}
              </Link>
            </div>
          </nav>
        ) : (
          <nav className="nav">
            <div className="nav-group">
              <Link href="/" className="alma-back">
                {t("sidebar.backToChat")}
              </Link>
            </div>
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
        )}
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
