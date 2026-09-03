"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Lang, useI18n } from "@/lib/i18n";

const NAV = [
  { href: "/", key: "nav.chat" },
  { href: "/dashboard", key: "nav.dashboard" },
  { href: "/queries", key: "nav.queries" },
  { href: "/queue", key: "nav.queue" },
  { href: "/tasks", key: "nav.tasks" },
  { href: "/system", key: "nav.system" },
  { href: "/nodes", key: "nav.nodes" },
  { href: "/resources", key: "nav.resources" },
  { href: "/models", key: "nav.models" },
  { href: "/knowledge", key: "nav.knowledge" },
  { href: "/environments", key: "nav.environments" },
  { href: "/maintenance", key: "nav.maintenance" },
  { href: "/evals", key: "nav.evals" },
  { href: "/improvements", key: "nav.improvements" },
  { href: "/escalation", key: "nav.escalation" },
  { href: "/settings", key: "nav.settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const { t, lang, setLang } = useI18n();

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
        <span className="topbar-logo">ATLAS</span>
      </header>

      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <span className="logo">ATLAS</span>
          <span className="tagline">{t("sidebar.tagline")}</span>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "active" : ""}
            >
              {t(item.key)}
            </Link>
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
          <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            {t("sidebar.footer")}
          </div>
        </div>
      </aside>
    </>
  );
}
