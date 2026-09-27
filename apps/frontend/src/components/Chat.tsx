"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Logo from "@/components/Logo";
import Markdown from "@/components/Markdown";
import { LanguageSelect, useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import {
  AttachmentInfo,
  ConversationSummary,
  Message,
  ModelInfo,
  SystemStatus,
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
  sendMessageFeedback,
  streamChat,
  uploadAttachment,
  webSearch,
} from "@/lib/api";

type Phase = "idle" | "waiting" | "streaming";
type Bubble = Message & { attachments?: string[] };

const MOBILE_QUERY = "(max-width: 900px)";

const SUGGESTIONS: { icon: string; key: string; prefill: string }[] = [
  { icon: "🌐", key: "chat.suggest.web", prefill: "/web " },
  { icon: "🧠", key: "chat.suggest.remember", prefill: "/remember " },
  { icon: "🔍", key: "chat.suggest.recall", prefill: "/recall " },
  { icon: "🖥", key: "chat.suggest.status", prefill: "/status" },
];

type Bucket = "today" | "yesterday" | "week" | "month" | "older";
const BUCKETS: Bucket[] = ["today", "yesterday", "week", "month", "older"];

function bucketOf(iso: string, now: Date): Bucket {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const ts = new Date(iso).getTime();
  const day = 86_400_000;
  if (ts >= startOfToday) return "today";
  if (ts >= startOfToday - day) return "yesterday";
  if (ts >= startOfToday - 7 * day) return "week";
  if (ts >= startOfToday - 30 * day) return "month";
  return "older";
}

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

function Typing() {
  return (
    <span className="typing">
      <span></span>
      <span></span>
      <span></span>
    </span>
  );
}

export default function Chat() {
  const { t, lang } = useI18n();
  const { user, logout } = useAuth();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [viewArchived, setViewArchived] = useState(false);
  const [filter, setFilter] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState("");
  const [attached, setAttached] = useState<AttachmentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [live, setLive] = useState("");
  const [liveCitations, setLiveCitations] = useState<WebCitation[]>([]);
  const [statusLine, setStatusLine] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [webOn, setWebOn] = useState(false);
  const [anon, setAnon] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState(""); // "" = Auto (server default)
  const [webNote, setWebNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<SystemStatus | null>(null);
  const [ratings, setRatings] = useState<Record<string, -1 | 1>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  // Desktop: sidebar can be collapsed. Mobile: sidebar is an off-canvas drawer.
  const [collapsed, setCollapsed] = useState(false);
  const [drawer, setDrawer] = useState(false);

  const fileRef = useRef<HTMLInputElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
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
  }, [loadConversations]);

  useEffect(() => {
    (async () => {
      try {
        const [list, def] = await Promise.all([fetchModels(), fetchDefaultModel()]);
        setModels(list.items.filter((m) => m.available));
        setModel(def.default_model || "");
      } catch {
        /* backend may be starting */
      }
    })();
    fetchSystemStatus().then(setHealth).catch(() => {});
  }, []);

  // Focus the composer on desktop only; on phones it would pop the keyboard.
  useEffect(() => {
    if (!window.matchMedia(MOBILE_QUERY).matches) inputRef.current?.focus();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, live, phase]);

  // Grow the composer with its content, up to the CSS max-height.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [draft]);

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

  // Keep the open conversation in the URL (?c=<id>) so a reload or a shared
  // link reopens it.
  const syncUrl = (id: string | null) => {
    const url = id ? `/?c=${encodeURIComponent(id)}` : "/";
    window.history.replaceState(null, "", url);
  };

  const closeDrawer = () => setDrawer(false);

  const openConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setError(null);
    setLive("");
    syncUrl(id);
    setDrawer(false);
    try {
      const convo = await fetchConversation(id);
      setMessages(convo.messages);
    } catch (e) {
      setMessages([]);
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  }, [t]);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("c");
    if (id) openConversation(id);
  }, [openConversation]);

  const newConversation = () => {
    if (streaming) return;
    setActiveId(null);
    setMessages([]);
    setLive("");
    setError(null);
    syncUrl(null);
    setDrawer(false);
    inputRef.current?.focus();
  };

  const toggleSidebar = () => {
    if (window.matchMedia(MOBILE_QUERY).matches) setDrawer((v) => !v);
    else setCollapsed((v) => !v);
  };

  // Resume an in-flight reply: if the open conversation has a pending assistant
  // message (e.g. after reloading the page), poll until it completes.
  useEffect(() => {
    if (!activeId || phase !== "idle") return;
    const hasPending = messages.some((m) => m.role === "assistant" && m.status === "pending");
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
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  const removeConvo = async (id: string) => {
    if (!window.confirm(t("chat.confirmDelete"))) return;
    try {
      await deleteConversation(id);
      if (id === activeId) newConversation();
      await loadConversations();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  const pushBubble = (
    role: "user" | "assistant",
    content: string,
    citations?: WebCitation[],
    attachments?: string[],
  ) =>
    setMessages((prev) => [
      ...prev,
      {
        id: `${role}-${Date.now()}-${Math.random()}`,
        conversation_id: activeId ?? "",
        role,
        content,
        citations: citations && citations.length ? citations : null,
        attachments: attachments && attachments.length ? attachments : undefined,
        created_at: new Date().toISOString(),
      },
    ]);

  const onPickFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const info = await uploadAttachment(file, activeId ?? undefined);
        setAttached((prev) => [...prev, info]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  // ---- slash commands (run platform actions without leaving the chat) ----
  const handleCommand = async (raw: string): Promise<boolean> => {
    const [cmd, ...rest] = raw.slice(1).split(" ");
    const arg = rest.join(" ").trim();
    const c = cmd.toLowerCase();
    if (c === "help") {
      pushBubble("assistant", t("chat.cmd.help"));
      return true;
    }
    if (c === "remember") {
      if (!arg) return pushBubble("assistant", t("chat.cmd.rememberUsage")), true;
      pushBubble("user", raw);
      await addMemory({ content: arg, source: "chat" });
      pushBubble("assistant", t("chat.cmd.saved", { text: arg }));
      return true;
    }
    if (c === "recall") {
      pushBubble("user", raw);
      const hits = await searchMemories(arg || "");
      pushBubble(
        "assistant",
        hits.length
          ? t("chat.cmd.memories") + "\n" + hits.map((h, i) => `${i + 1}. ${h.content}`).join("\n")
          : t("chat.cmd.noMemories"),
      );
      return true;
    }
    if (c === "search") {
      pushBubble("user", raw);
      try {
        const res = await webSearch(arg);
        pushBubble(
          "assistant",
          res.count ? t("chat.cmd.results", { n: res.count, q: arg }) : t("chat.cmd.noResults", { q: arg }),
          res.citations,
        );
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : t("common.failed")}`);
      }
      return true;
    }
    if (c === "models") {
      pushBubble(
        "assistant",
        models.length
          ? t("chat.cmd.models") +
              "\n" +
              models.map((m) => `• ${m.name}`).join("\n") +
              "\n\n" +
              t("chat.cmd.current", { model: model || t("chat.auto") })
          : t("chat.cmd.noModels"),
      );
      return true;
    }
    if (c === "model") {
      if (!arg)
        return pushBubble("assistant", t("chat.cmd.modelUsage", { model: model || t("chat.auto") })), true;
      setModel(arg);
      pushBubble("assistant", t("chat.cmd.modelSet", { model: arg }));
      return true;
    }
    if (c === "task") {
      if (!arg) return pushBubble("assistant", t("chat.cmd.taskUsage")), true;
      pushBubble("user", raw);
      try {
        const task = await createTask({ title: arg });
        pushBubble("assistant", t("chat.cmd.taskCreated", { title: task.title ?? "", status: task.status }));
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : t("common.failed")}`);
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
            ? t("chat.cmd.nodes", { online: n.online, total: n.total }) +
                "\n" +
                n.items
                  .map(
                    (x) =>
                      `• ${x.label || x.node_id} — ${x.online ? t("common.online") : t("common.offline")}`,
                  )
                  .join("\n")
            : t("chat.cmd.noNodes"),
        );
      } catch (e) {
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : t("common.failed")}`);
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
        pushBubble("assistant", `⚠️ ${e instanceof Error ? e.message : t("common.failed")}`);
      }
      return true;
    }
    if (c === "web") {
      await send(arg, true);
      return true;
    }
    pushBubble("assistant", t("chat.cmd.unknown", { cmd: c }));
    return true;
  };

  const send = async (text?: string, forceWeb = false) => {
    const content = (text ?? draft).trim();
    if ((!content && attached.length === 0) || streaming) return;

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
    setStatusLine(forceWeb || webOn ? t("chat.searching") : t("chat.thinking"));
    startTimer();
    const attachmentIds = attached.map((a) => a.id);
    const attachmentNames = attached.map((a) => a.filename);
    pushBubble("user", content, undefined, attachmentNames);
    setAttached([]);

    let acc = "";
    let citations: WebCitation[] = [];
    let convoId = activeId ?? null;

    const controller = new AbortController();
    abortRef.current = controller;

    await streamChat(
      {
        content: content || t("chat.analyzeFile"),
        conversation_id: activeId ?? undefined,
        web: forceWeb || webOn,
        model: model || undefined,
        anonymous: anon || undefined,
        attachment_ids: attachmentIds.length ? attachmentIds : undefined,
        language: lang,
      },
      {
        onStart: (e) => {
          setStatusLine(`${e.provider} · ${e.model} — ${t("chat.generating")}`);
          // Anonymous turns have no persisted conversation id.
          if (e.conversation_id) {
            convoId = e.conversation_id;
            if (!activeId) {
              setActiveId(e.conversation_id);
              syncUrl(e.conversation_id);
            }
          }
        },
        onToken: (tok) => {
          acc += tok;
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
          setLive("");
          setLiveCitations([]);
          setPhase("idle");
          abortRef.current = null;
          // Reload the persisted conversation so the reply carries its real DB
          // id — that's what a 👍/👎 attaches to. Anonymous turns are never
          // persisted, so they keep a local bubble.
          if (!anon && convoId) {
            try {
              const convo = await fetchConversation(convoId);
              setMessages(convo.messages);
            } catch {
              pushBubble("assistant", acc || t("chat.noOutput"), citations);
            }
            loadConversations();
          } else {
            pushBubble("assistant", acc || t("chat.noOutput"), citations);
          }
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

  // A 👍 becomes training data for fine-tuning and raises the model's quality
  // signal; a 👎 lowers it. Clicking the same thumb again clears it.
  const rate = async (messageId: string, value: -1 | 1) => {
    const next = ratings[messageId] === value ? 0 : value;
    setRatings((prev) => {
      const copy = { ...prev };
      if (next === 0) delete copy[messageId];
      else copy[messageId] = next;
      return copy;
    });
    try {
      await sendMessageFeedback(messageId, next);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.failed"));
    }
  };

  const copy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId((c) => (c === id ? null : c)), 1500);
    } catch {
      /* clipboard unavailable (e.g. insecure context) */
    }
  };

  const stop = () => {
    abortRef.current?.abort();
    stopTimer();
    if (live) pushBubble("assistant", `${live} …(${t("chat.stopped")})`);
    setLive("");
    setPhase("idle");
    abortRef.current = null;
  };

  const prefill = (text: string) => {
    setDraft(text);
    inputRef.current?.focus();
  };

  const grouped = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const now = new Date();
    const out: Record<Bucket, ConversationSummary[]> = {
      today: [],
      yesterday: [],
      week: [],
      month: [],
      older: [],
    };
    for (const c of conversations) {
      if (q && !(c.title ?? "").toLowerCase().includes(q)) continue;
      out[bucketOf(c.updated_at || c.created_at, now)].push(c);
    }
    return out;
  }, [conversations, filter]);

  const empty = messages.length === 0 && !live && phase === "idle";
  const activeTitle = conversations.find((c) => c.id === activeId)?.title;
  const hasAnyConvo = BUCKETS.some((b) => grouped[b].length > 0);

  const composer = (
    <div className="composer">
      <input
        ref={fileRef}
        type="file"
        multiple
        hidden
        onChange={(e) => onPickFiles(e.target.files)}
      />

      {attached.length > 0 && (
        <div className="composer-chips">
          {attached.map((a) => (
            <span key={a.id} className="attach-chip">
              📎 {a.filename}
              <button
                className="attach-x"
                title={t("common.delete")}
                onClick={() => setAttached((prev) => prev.filter((x) => x.id !== a.id))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <textarea
        ref={inputRef}
        className="composer-text"
        value={draft}
        rows={1}
        placeholder={webOn ? t("chat.placeholderWeb") : t("chat.placeholder")}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
          }
        }}
        disabled={streaming}
      />

      <div className="composer-bar">
        <button
          className="composer-icon"
          onClick={() => fileRef.current?.click()}
          disabled={streaming || uploading}
          title={t("chat.attach")}
          aria-label={t("chat.attach")}
        >
          {uploading ? "…" : "+"}
        </button>
        <button
          className={`composer-pill${webOn ? " on" : ""}`}
          onClick={() => setWebOn((v) => !v)}
          disabled={streaming}
          aria-pressed={webOn}
          title={t("chat.web")}
        >
          🌐 {t("chat.web")}
        </button>
        <button
          className={`composer-pill${anon ? " on" : ""}`}
          onClick={() => setAnon((v) => !v)}
          disabled={streaming}
          aria-pressed={anon}
          title={t("chat.anonHint")}
        >
          🕶 {t("chat.anon")}
        </button>

        <div className="composer-spacer" />

        {streaming ? (
          <button
            className="composer-send stop"
            onClick={stop}
            title={t("chat.stop")}
            aria-label={t("chat.stop")}
          >
            <span className="composer-square" />
          </button>
        ) : (
          <button
            className="composer-send"
            onClick={() => send()}
            disabled={!draft.trim() && attached.length === 0}
            title={t("chat.send")}
            aria-label={t("chat.send")}
          >
            ↑
          </button>
        )}
      </div>
    </div>
  );

  return (
    <div className={`alma-shell${collapsed ? " side-collapsed" : ""}`}>
      {drawer && <div className="alma-scrim" onClick={closeDrawer} />}

      <aside className={`alma-side${drawer ? " open" : ""}`} aria-label={t("chat.history")}>
        <div className="alma-side-head">
          <span className="alma-brand">
            <Logo size={26} />
            ALMA
          </span>
          <button
            className="alma-icon-btn"
            onClick={toggleSidebar}
            title={t("chat.toggleSidebar")}
            aria-label={t("chat.toggleSidebar")}
          >
            ⟨
          </button>
        </div>

        <button className="alma-new" onClick={newConversation} disabled={streaming}>
          <span aria-hidden>✎</span> {t("chat.newChatShort")}
        </button>

        <input
          className="alma-search"
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("chat.searchChats")}
          aria-label={t("chat.searchChats")}
        />

        <nav className="alma-history">
          {viewArchived && <div className="alma-group-label">{t("chat.showArchived")}</div>}
          {!hasAnyConvo && (
            <p className="alma-history-empty">
              {viewArchived ? t("chat.noArchived") : filter ? t("chat.noMatch") : t("chat.noChats")}
            </p>
          )}
          {BUCKETS.map((b) =>
            grouped[b].length === 0 ? null : (
              <div key={b} className="alma-group">
                {!viewArchived && <div className="alma-group-label">{t(`chat.bucket.${b}`)}</div>}
                {grouped[b].map((c) => (
                  <div
                    key={c.id}
                    className={`alma-item${c.id === activeId ? " active" : ""}`}
                    title={c.title ?? c.id}
                  >
                    <button className="alma-item-title" onClick={() => openConversation(c.id)}>
                      {c.title ?? t("chat.untitled")}
                    </button>
                    <span className="alma-item-actions">
                      <button
                        title={viewArchived ? t("chat.unarchive") : t("chat.archive")}
                        aria-label={viewArchived ? t("chat.unarchive") : t("chat.archive")}
                        onClick={() => archiveConvo(c.id, !viewArchived)}
                      >
                        {viewArchived ? "↩" : "🗄"}
                      </button>
                      <button
                        className="danger"
                        title={t("chat.delete")}
                        aria-label={t("chat.delete")}
                        onClick={() => removeConvo(c.id)}
                      >
                        🗑
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            ),
          )}
        </nav>

        <div className="alma-side-foot">
          <button
            className="alma-foot-link"
            onClick={() => {
              setViewArchived((v) => !v);
              newConversation();
            }}
          >
            {viewArchived ? `← ${t("chat.showActive")}` : `🗄 ${t("chat.showArchived")}`}
          </button>
          <Link href="/dashboard" className="alma-foot-link">
            ⚙ {t("sidebar.openControl")}
          </Link>
          <div className="alma-foot-row">
            <LanguageSelect />
            {user ? (
              <button className="alma-foot-link" onClick={logout} title={user.email}>
                {t("auth.logout")}
              </button>
            ) : (
              <Link href="/login" className="alma-foot-link">
                {t("auth.login")}
              </Link>
            )}
          </div>
          {user && <div className="alma-user">{user.email}</div>}
        </div>
      </aside>

      <section className="alma-main">
        <header className="alma-top">
          <button
            className="alma-icon-btn alma-open-side"
            onClick={toggleSidebar}
            title={t("chat.toggleSidebar")}
            aria-label={t("chat.toggleSidebar")}
          >
            ☰
          </button>
          <select
            className="alma-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={streaming}
            title={t("chat.modelPick")}
            aria-label={t("chat.modelPick")}
          >
            <option value="">{t("chat.auto")}</option>
            {models.map((m) => (
              <option key={`${m.provider}:${m.name}`} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
          <span className="alma-top-title">{activeTitle ?? ""}</span>
          <button
            className="alma-icon-btn"
            onClick={newConversation}
            disabled={streaming}
            title={t("chat.newChatShort")}
            aria-label={t("chat.newChatShort")}
          >
            ✎
          </button>
        </header>

        {empty ? (
          <div className="alma-empty">
            <Logo size={44} />
            <h1>{t("chat.greeting")}</h1>
            {health && (
              <p className="alma-health">
                <span className={`dot ${health.status === "healthy" ? "ok" : "warn"}`} />
                {health.status === "healthy" ? t("chat.healthy") : t("chat.degraded")} · v
                {health.version}
              </p>
            )}
            <div className="alma-empty-composer">{composer}</div>
            <div className="alma-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s.key} onClick={() => prefill(s.prefill)}>
                  <span aria-hidden>{s.icon}</span> {t(s.key)}
                </button>
              ))}
            </div>
            {error && <p className="error">{error}</p>}
          </div>
        ) : (
          <>
            <div className="alma-scroll" ref={scrollRef}>
              <div className="alma-thread">
                {messages.map((m) => {
                  if (m.role === "user") {
                    return (
                      <div key={m.id} className="msg msg-user">
                        {m.attachments && m.attachments.length > 0 && (
                          <div className="attach-chips">
                            {m.attachments.map((name, i) => (
                              <span key={i} className="attach-chip">
                                📎 {name}
                              </span>
                            ))}
                          </div>
                        )}
                        {m.content}
                      </div>
                    );
                  }
                  const pending = m.status === "pending";
                  const persisted = !m.id.startsWith("assistant-");
                  return (
                    <div key={m.id} className="msg msg-assistant">
                      <Markdown text={m.content} />
                      {pending && (
                        <span className="working-row">
                          <Typing />
                          <span className="meta">{t("chat.working")}</span>
                        </span>
                      )}
                      {m.status === "error" && (
                        <span className="meta" style={{ color: "var(--bad)" }}>
                          {t("chat.interrupted")}
                        </span>
                      )}
                      {m.citations && <Citations items={m.citations} label={t("chat.sources")} />}
                      {!pending && (
                        <div className="msg-actions">
                          <button
                            onClick={() => copy(m.id, m.content)}
                            title={t("chat.copy")}
                            aria-label={t("chat.copy")}
                          >
                            {copiedId === m.id ? "✓" : "⧉"}
                          </button>
                          {persisted && m.status !== "error" && (
                            <>
                              <button
                                className={ratings[m.id] === 1 ? "on" : ""}
                                title={t("chat.feedbackUp")}
                                aria-label={t("chat.feedbackUp")}
                                onClick={() => rate(m.id, 1)}
                              >
                                👍
                              </button>
                              <button
                                className={ratings[m.id] === -1 ? "on" : ""}
                                title={t("chat.feedbackDown")}
                                aria-label={t("chat.feedbackDown")}
                                onClick={() => rate(m.id, -1)}
                              >
                                👎
                              </button>
                            </>
                          )}
                          {m.model && (
                            <span className="meta">
                              {m.model}
                              {m.latency_ms != null ? ` · ${(m.latency_ms / 1000).toFixed(1)}s` : ""}
                            </span>
                          )}
                          {ratings[m.id] === 1 && (
                            <span className="meta">{t("chat.feedbackThanks")}</span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

                {phase === "streaming" && (
                  <div className="msg msg-assistant">
                    <Markdown text={live} />
                    <span className="caret">▌</span>
                    <Citations items={liveCitations} label={t("chat.sources")} />
                  </div>
                )}

                {phase === "waiting" && (
                  <div className="msg msg-assistant msg-thinking">
                    <Typing />
                    <span className="meta">
                      {statusLine} {elapsed > 0 ? `· ${elapsed}s` : ""}
                      {elapsed >= 8 ? ` · ${t("chat.modelLoad")}` : ""}
                    </span>
                  </div>
                )}

                {webNote && <p className="muted">🌐 {webNote}</p>}
                {error && <p className="error">{error}</p>}
              </div>
            </div>
            <div className="alma-bottom">
              {composer}
              <p className="alma-disclaimer">{t("chat.disclaimer")}</p>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
