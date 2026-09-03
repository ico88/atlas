"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV = [
  { href: "/", label: "Chat" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/queries", label: "Queries" },
  { href: "/queue", label: "Queue" },
  { href: "/tasks", label: "Tasks" },
  { href: "/system", label: "System Status" },
  { href: "/nodes", label: "Nodes" },
  { href: "/resources", label: "Resources" },
  { href: "/models", label: "Models" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/environments", label: "Environments" },
  { href: "/maintenance", label: "Maintenance" },
  { href: "/evals", label: "Evals" },
  { href: "/escalation", label: "Escalation" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

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
          <span className="tagline">Adaptive Task &amp; LLM Array System</span>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "active" : ""}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div style={{ marginTop: "auto" }} className="muted">
          Local-first · Human-governed
        </div>
      </aside>
    </>
  );
}
