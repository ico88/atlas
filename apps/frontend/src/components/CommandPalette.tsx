"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Item = { label: string; hint?: string; href: string };

const ITEMS: Item[] = [
  { label: "Chat", hint: "ask anything", href: "/" },
  { label: "Dashboard", hint: "overview", href: "/dashboard" },
  { label: "Queries", hint: "background AI runs", href: "/queries" },
  { label: "Queue", hint: "conversation queue", href: "/queue" },
  { label: "Tasks", hint: "task engine", href: "/tasks" },
  { label: "System Status", hint: "health", href: "/system" },
  { label: "Nodes", hint: "workers & enrollment", href: "/nodes" },
  { label: "Resources", hint: "telemetry", href: "/resources" },
  { label: "Models", hint: "download / default", href: "/models" },
  { label: "Knowledge", hint: "RAG & memory", href: "/knowledge" },
  { label: "Environments", hint: "workspaces", href: "/environments" },
  { label: "Maintenance", hint: "self-healing", href: "/maintenance" },
  { label: "Escalation", hint: "external help", href: "/escalation" },
  { label: "Settings", hint: "web tools & config", href: "/settings" },
];

export default function CommandPalette() {
  const router = useRouter();
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
      (i) => i.label.toLowerCase().includes(term) || (i.hint ?? "").includes(term),
    );
  }, [q]);

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
          placeholder="Jump to… (type a page)"
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
          {results.length === 0 && <div className="cmdk-empty">No matches</div>}
          {results.map((item, i) => (
            <div
              key={item.href}
              className={`cmdk-item ${i === active ? "active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => go(item)}
            >
              <span>{item.label}</span>
              {item.hint && <span className="cmdk-hint">{item.hint}</span>}
            </div>
          ))}
        </div>
        <div className="cmdk-foot">↑↓ navigate · ↵ open · esc close · ⌘/Ctrl-K toggle</div>
      </div>
    </div>
  );
}
