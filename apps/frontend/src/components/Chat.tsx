"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "@/components/Markdown";
import { useI18n } from "@/lib/i18n";
import {
  ConversationSummary,
  Message,
  ModelInfo,
  WebCitation,
  addMemory,
  archiveConversation,
  createTask,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  fetchDefaultModel,
  fetchModels,
  fetchNodes,
  fetchSystemStatus,
  searchMemories,
  streamChat,
  webSearch,
} from "@/lib/api";

type Phase = "idle" | "waiting" | "streaming";

function Citations({ items, label }: { items: WebCitation[]; label: string }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="citations">
      <span className="meta">{label}</span>
      <ol>
        {items.map((c, i) => (
          <li key={`${c.url}-${i}`}>
            <a href={c.url} target="_blank" rel="noreferrer noopener">
              {c.title || c.url}
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

const HELP = [
  "Commands you can type here:",
  "• /web <question> — answer using a web search (cites sources)",
  "• /search <query> — show web results only",
  "• /remember <text> — save a memory",
  "• /recall <query> — recall saved memories",
  "• /model <name> — pick the model (or /models to list)",
  "• /task <title> — create a task · /nodes — list nodes · /status — health",
  "• /help — show this help",
].join("\n");

export default function Chat() {
  const { t } = useI18n();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [viewArchived, setViewArchived] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [live, setLive] = useState("");
  const [liveCitations, setLiveCitations] = useState<WebCitation[]>([]);
  const [statusLine, setStatusLine] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [webOn, setWebOn] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState("");  // "" = Auto (server default)
  const [webNote, setWebNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const streaming = phase !== "idle";

  const loadConversations = useCallback(async () => {
    try {
      const list = await fetchConversations(viewArchived);
      setConversations(list.items);
    } catch {
      /* backend may be starting */
    }
  }, [viewArchived]);

  useEffect(() => {
    loadConversations();
    // Load the model list + current default so the chat can pick a model.
    (async () => {
      try {
        const [list, def] = await Promise.all([fetchModels(), fetchDefaultModel()]);
        setModels(list.items.filter((m) => m.available));
        setModel(def.default_model || "");
      } catch {
        /* backend may be starting */
      }
    })();
  }, [loadConversations]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, live, phase]);

  // Elapsed-time ticker so the user can see the system is working, not stuck.
  const startTimer = useCallback(() => {
    setElapsed(0);
    const started = Date.now();
    timerRef.current = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      500,
    );
  }, []);
  const stopTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  }, []);
  useEffect(() => () => stopTimer(), [stopTimer]);

  const openConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setError(null);
    const convo = await fetchConversation(id);
    setMessages(convo.messages);
  }, []);

  const newConversation = () => {
    setActiveId(null);
    setMessages([]);
    setLive("");
    setError(null);
  };

  // Resume an in-flight reply: if the open conversation has a pending assistant
  // message (e.g. after reloading the page), poll until it completes.
  useEffect(() => {
    if (!activeId || phase !== "idle") return;
    const hasPending = messages.some(
      (m) => m.role === "assistant" && m.status === "pending",
    );
    if (!hasPending) return;
    const id = setInterval(async () => {
      try {
        const convo = await fetchConversation(activeId);
        setMessages(convo.messages);
      } catch {
        /* transient */
      }
    }, 1500);
    return () => clearInterval(id);
  }, [activeId, messages, phase]);

  const archiveConvo = async (id: string, archived: boolean) => {
    try {
      await archiveConversation(id, archived);
      if (id === activeId) newConversation();
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : "archive failed");
    }
  };

  const removeConvo = async (id: string) => {
    if (typeof window !== "undefined" && !window.confirm(t("chat.confirmDelete"))) return;
    try {
      await deleteConversation(id);
      if (id === activeId) newConversation();
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : "delete failed");
    }
  };

  const pushBubble = (role: "user" | "assistant", content: string, citations?: WebCitation[]) =>
    setMessages((prev) => [
      ...prev,
      {
        id: `${role}-${Date.now()}-${Math.random()}`,
        conversation_id: activeId ?? "",
        role,
        content,
        citations: citations && citations.length ? citations : null,
        created_at: new Date().toISOString(),
      },
    ]);

  // ---- slash commands (run platform actions without leaving the chat) ----
  const handleCommand = async (raw: string): Promise<boolean> => {
    const [cmd, ...rest] = raw.slice(1).split(" ");
    const arg = rest.join(" ").trim();
    const c = cmd.toLowerCase();
    if (c === "help") {
      pushBubble("assistant", HELP);
      return true;
    }
    if (c === "remember") {
      if (!arg) return pushBubble("assistant", "Usage: /remember <text>"), true;
      pushBubble("user", raw);
      await addMemory({ content: arg, source: "chat" });
      pushBubble("assistant", `🧠 Saved to memory: “${arg}”`);
      return true;
    }
    if (c === "recall") {
      pushBubble("user", raw);
      const hits = await searchMemories(arg || "");
      pushBubble(
        "assistant",
        hits.length
          ? "🧠 Memories:\n" + hits.map((h, i) => `${i + 1}. ${h.content}`).join("\n")
          : "No memories found.",
      );
      return true;
    }
    if (c === "search") {
      pushBubble("user", raw);
      try {
        const res = await webSearch(arg);
        pushBubble(
          "assistant",
          res.count ? `🔎 ${res.count} result(s) for “${arg}”:` : `No results for “${arg}”.`,
          res.citations,
        );
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : "search failed"}`);
      }
      return true;
    }
    if (c === "models") {
      pushBubble(
        "assistant",
        models.length
          ? "Available models:\n" + models.map((m) => `• ${m.name}`).join("\n") + `\n\nCurrent: ${model || "Auto"}`
          : "No models yet — download one from the Models page.",
      );
      return true;
    }
    if (c === "model") {
      if (!arg) return pushBubble("assistant", `Current model: ${model || "Auto"}. Usage: /model <name>`), true;
      setModel(arg);
      pushBubble("assistant", `✅ This chat will use model: ${arg}`);
      return true;
    }
    if (c === "task") {
      if (!arg) return pushBubble("assistant", "Usage: /task <title>"), true;
      pushBubble("user", raw);
      try {
        const t = await createTask({ title: arg });
        pushBubble("assistant", `📋 Task created: “${t.title}” (${t.status}).`);
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : "task failed"}`);
      }
      return true;
    }
    if (c === "nodes") {
      pushBubble("user", raw);
      try {
        const n = await fetchNodes();
        pushBubble(
          "assistant",
          n.items.length
            ? `🖥️ ${n.online}/${n.total} online:\n` +
                n.items.map((x) => `• ${x.label || x.node_id} — ${x.online ? "online" : "offline"}`).join("\n")
            : "No nodes registered.",
        );
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : "failed"}`);
      }
      return true;
    }
    if (c === "status") {
      pushBubble("user", raw);
      try {
        const s = await fetchSystemStatus();
        const parts = s.components.map((x) => `${x.name}: ${x.status}`).join(" · ");
        pushBubble("assistant", `⚙️ ${s.status} (v${s.version}) — ${parts}`);
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : "failed"}`);
      }
      return true;
    }
    if (c === "web") {
      // Fall through to a normal chat turn, but force web grounding on.
      setDraft(arg);
      await send(arg, true);
      return true;
    }
    pushBubble("assistant", `Unknown command “/${c}”. Type /help.`);
    return true;
  };

  const send = async (text?: string, forceWeb = false) => {
    const content = (text ?? draft).trim();
    if (!content || streaming) return;

    // Slash command? Handle it and stop.
    if (content.startsWith("/") && text === undefined) {
      setDraft("");
      await handleCommand(content);
      return;
    }

    setDraft("");
    setError(null);
    setLive("");
    setLiveCitations([]);
    setWebNote(null);
    setPhase("waiting");
    setStatusLine((forceWeb || webOn) ? t("chat.searching") : t("chat.thinking"));
    startTimer();
    pushBubble("user", content);

    let acc = "";
    let citations: WebCitation[] = [];

    const controller = new AbortController();
    abortRef.current = controller;

    await streamChat(
      {
        content,
        conversation_id: activeId ?? undefined,
        web: forceWeb || webOn,
        model: model || undefined,
      },
      {
        onStart: (e) => {
          setStatusLine(`${e.provider} · ${e.model} — ${t("chat.generating")}`);
          if (!activeId) setActiveId(e.conversation_id);
        },
        onToken: (t) => {
          acc += t;
          setPhase("streaming");
          setLive(acc);
        },
        onCitations: (items, note) => {
          citations = items;
          setLiveCitations(items);
          setWebNote(note ?? null);
        },
        onDone: async () => {
          stopTimer();
          pushBubble("assistant", acc || "(no output)", citations);
          setLive("");
          setLiveCitations([]);
          setPhase("idle");
          abortRef.current = null;
          loadConversations();
        },
        onError: (detail) => {
          stopTimer();
          setError(detail);
          setLive("");
          setPhase("idle");
          abortRef.current = null;
        },
      },
      controller.signal,
    );
  };

  const stop = () => {
    abortRef.current?.abort();
    stopTimer();
    if (live) pushBubble("assistant", live + " …(stopped)");
    setLive("");
    setPhase("idle");
    abortRef.current = null;
  };

  return (
    <div>
      <h1 className="page-title">{t("chat.title")}</h1>
      <p className="page-subtitle">{t("chat.subtitle")}</p>

      <div className="chat-layout chat-fill">
        <div className="convo-list">
          <button
            className="btn secondary"
            style={{ width: "100%", marginBottom: 8 }}
            onClick={newConversation}
          >
            {t("chat.newChat")}
          </button>
          <button
            className="btn secondary convo-toggle"
            style={{ width: "100%", marginBottom: 8, fontSize: 12 }}
            onClick={() => {
              setViewArchived((v) => !v);
              newConversation();
            }}
          >
            {viewArchived ? `← ${t("chat.showActive")}` : `🗄 ${t("chat.showArchived")}`}
          </button>
          {viewArchived && conversations.length === 0 && (
            <p className="muted" style={{ fontSize: 12 }}>{t("chat.noArchived")}</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`convo-item ${c.id === activeId ? "active" : ""}`}
              title={c.title ?? c.id}
            >
              <span className="convo-title" onClick={() => openConversation(c.id)}>
                {c.title ?? t("chat.untitled")}
              </span>
              <span className="convo-actions">
                <button
                  className="convo-act"
                  title={viewArchived ? t("chat.unarchive") : t("chat.archive")}
                  onClick={(e) => {
                    e.stopPropagation();
                    archiveConvo(c.id, !viewArchived);
                  }}
                >
                  {viewArchived ? "↩" : "🗄"}
                </button>
                <button
                  className="convo-act danger"
                  title={t("chat.delete")}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeConvo(c.id);
                  }}
                >
                  🗑
                </button>
              </span>
            </div>
          ))}
        </div>

        <div className="chat-main">
          <div className="chat-messages" ref={scrollRef}>
            {messages.length === 0 && !live && phase === "idle" && (
              <div className="muted">
                <p>{t("chat.empty")}</p>
                <pre style={{ background: "var(--panel-2)", padding: 12, borderRadius: 8 }}>
                  {HELP}
                </pre>
              </div>
            )}
            {messages.map((m) => {
              // A reply still generating in the background (e.g. resumed after a
              // reload): show its partial text + a clear "working" indicator.
              if (m.role === "assistant" && m.status === "pending") {
                return (
                  <div key={m.id} className="bubble assistant">
                    <Markdown text={m.content} />
                    <span className="caret">▌</span>
                    <span className="working-row">
                      <span className="typing">
                        <span></span>
                        <span></span>
                        <span></span>
                      </span>
                      <span className="meta">{t("chat.working")}</span>
                    </span>
                  </div>
                );
              }
              return (
                <div key={m.id} className={`bubble ${m.role}`}>
                  {m.role === "assistant" ? <Markdown text={m.content} /> : m.content}
                  {m.role === "assistant" && m.citations && (
                    <Citations items={m.citations} label={t("chat.sources")} />
                  )}
                  {m.role === "assistant" && m.model && (
                    <span className="meta">
                      {m.provider} · {m.model}
                      {m.latency_ms != null ? ` · ${m.latency_ms} ms` : ""}
                    </span>
                  )}
                </div>
              );
            })}

            {/* Live streaming text once tokens arrive. */}
            {phase === "streaming" && (
              <div className="bubble assistant">
                <Markdown text={live} />
                <span className="caret">▌</span>
                <Citations items={liveCitations} label={t("chat.sources")} />
              </div>
            )}

            {/* Processing indicator BEFORE the first token, so it never looks stuck. */}
            {phase === "waiting" && (
              <div className="bubble assistant thinking">
                <span className="typing">
                  <span></span>
                  <span></span>
                  <span></span>
                </span>
                <span className="meta">
                  {statusLine} {elapsed > 0 ? `· ${elapsed}s` : ""}
                  {elapsed >= 8 ? ` · ${t("chat.modelLoad")}` : ""}
                </span>
              </div>
            )}

            {webNote && <p className="muted">🌐 {webNote}</p>}
            {error && <p className="error">Error: {error}</p>}
          </div>

          <div className="chat-input">
            <select
              className="model-select"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={streaming}
              title="Model for this chat"
            >
              <option value="">{t("chat.auto")}</option>
              {models.map((m) => (
                <option key={`${m.provider}:${m.name}`} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
            <label className="web-toggle" title="Ground the reply with a web search">
              <input
                type="checkbox"
                checked={webOn}
                onChange={(e) => setWebOn(e.target.checked)}
                disabled={streaming}
              />
              🌐 {t("chat.web")}
            </label>
            <input
              value={draft}
              placeholder={webOn ? t("chat.placeholderWeb") : t("chat.placeholder")}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
              disabled={streaming}
            />
            {streaming ? (
              <button className="btn secondary" onClick={stop}>
                {t("chat.stop")}
              </button>
            ) : (
              <button className="btn" onClick={() => send()} disabled={!draft.trim()}>
                {t("chat.send")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
