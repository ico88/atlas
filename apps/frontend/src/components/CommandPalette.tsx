"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";

type Item = { key: string; hint: string; href: string };

const ITEMS: Item[] = [
  { key: "nav.chat", hint: "cmdk.chat", href: "/" },
  { key: "nav.dashboard", hint: "cmdk.dashboard", href: "/dashboard" },
  { key: "nav.queries", hint: "cmdk.queries", href: "/queries" },
  { key: "nav.queue", hint: "cmdk.queue", href: "/queue" },
  { key: "nav.tasks", hint: "cmdk.tasks", href: "/tasks" },
  { key: "nav.system", hint: "cmdk.system", href: "/system" },
  { key: "nav.nodes", hint: "cmdk.nodes", href: "/nodes" },
  { key: "nav.fleet", hint: "cmdk.fleet", href: "/fleet" },
  { key: "nav.compliance", hint: "cmdk.compliance", href: "/compliance" },
  { key: "nav.resources", hint: "cmdk.resources", href: "/resources" },
  { key: "nav.models", hint: "cmdk.models", href: "/models" },
  { key: "nav.runtimes", hint: "cmdk.runtimes", href: "/runtimes" },
  { key: "nav.knowledge", hint: "cmdk.knowledge", href: "/knowledge" },
  { key: "nav.environments", hint: "cmdk.environments", href: "/environments" },
  { key: "nav.logs", hint: "cmdk.logs", href: "/logs" },
  { key: "nav.agents", hint: "cmdk.agents", href: "/agents" },
  { key: "nav.autopilot", hint: "cmdk.autopilot", href: "/autopilot" },
  { key: "nav.maintenance", hint: "cmdk.maintenance", href: "/maintenance" },
  { key: "nav.evals", hint: "cmdk.evals", href: "/evals" },
  { key: "nav.improvements", hint: "cmdk.improvements", href: "/improvements" },
  { key: "nav.reviews", hint: "cmdk.reviews", href: "/reviews" },
  { key: "nav.escalation", hint: "cmdk.escalation", href: "/escalation" },
  { key: "nav.users", hint: "cmdk.users", href: "/users" },
  { key: "nav.security", hint: "cmdk.security", href: "/admin/security" },
  { key: "nav.settings", hint: "cmdk.settings", href: "/settings" },
];

export default function CommandPalette() {
  const router = useRouter();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return ITEMS;
    return ITEMS.filter(
      (i) => t(i.key).toLowerCase().includes(term) || t(i.hint).toLowerCase().includes(term),
    );
  }, [q, t]);

  const go = (item?: Item) => {
    const target = item ?? results[active];
    if (!target) return;
    setOpen(false);
    router.push(target.href);
  };

  if (!open) return null;

  return (
    <div className="cmdk-scrim" onClick={() => setOpen(false)}>
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="cmdk-input"
          placeholder={t("cmdk.placeholder")}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, results.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              go();
            }
          }}
        />
        <div className="cmdk-list">
          {results.length === 0 && <div className="cmdk-empty">{t("cmdk.empty")}</div>}
          {results.map((item, i) => (
            <div
              key={item.href}
              className={`cmdk-item ${i === active ? "active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => go(item)}
            >
              <span>{t(item.key)}</span>
              <span className="cmdk-hint">{t(item.hint)}</span>
            </div>
          ))}
        </div>
        <div className="cmdk-foot">{t("cmdk.foot")}</div>
      </div>
    </div>
  );
}
