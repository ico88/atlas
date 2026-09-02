"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/chat", label: "Chat" },
  { href: "/tasks", label: "Tasks" },
  { href: "/system", label: "System Status" },
  { href: "/nodes", label: "Nodes" },
  { href: "/models", label: "Models" },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
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
  );
}
