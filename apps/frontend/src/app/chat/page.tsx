"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConversationSummary,
  Message,
  fetchConversation,
  fetchConversations,
  streamChat,
} from "@/lib/api";

export default function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [live, setLive] = useState("");
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(async () => {
    try {
      const list = await fetchConversations();
      setConversations(list.items);
    } catch {
      /* backend may be starting */
    }
  }, []);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages, live]);

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

  const send = async () => {
    const content = draft.trim();
    if (!content || streaming) return;
    setDraft("");
    setError(null);
    setStreaming(true);
    setLive("");

    // Optimistically render the user message.
    setMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        conversation_id: activeId ?? "",
        role: "user",
        content,
        created_at: new Date().toISOString(),
      },
    ]);

    let acc = "";
    let convId = activeId;
    let provider = "";
    let model = "";

    await streamChat(
      { content, conversation_id: activeId ?? undefined },
      {
        onStart: (e) => {
          convId = e.conversation_id;
          provider = e.provider;
          model = e.model;
          if (!activeId) setActiveId(e.conversation_id);
        },
        onToken: (t) => {
          acc += t;
          setLive(acc);
        },
        onDone: async () => {
          setMessages((prev) => [
            ...prev,
            {
              id: `a-${Date.now()}`,
              conversation_id: convId ?? "",
              role: "assistant",
              content: acc,
              provider,
              model,
              created_at: new Date().toISOString(),
            },
          ]);
          setLive("");
          setStreaming(false);
          loadConversations();
        },
        onError: (detail) => {
          setError(detail);
          setLive("");
          setStreaming(false);
        },
      },
    );
  };

  return (
    <div>
      <h1 className="page-title">Chat</h1>
      <p className="page-subtitle">
        Local-first chat with streaming replies (spec §9). Uses Ollama when
        available, otherwise the built-in echo model.
      </p>

      <div className="chat-layout">
        <div className="convo-list">
          <button
            className="btn secondary"
            style={{ width: "100%", marginBottom: 8 }}
            onClick={newConversation}
          >
            + New chat
          </button>
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`convo-item ${c.id === activeId ? "active" : ""}`}
              onClick={() => openConversation(c.id)}
              title={c.title ?? c.id}
            >
              {c.title ?? "Untitled"}
            </div>
          ))}
        </div>

        <div className="chat-main">
          <div className="chat-messages" ref={scrollRef}>
            {messages.length === 0 && !live && (
              <p className="muted">Start the conversation below.</p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`bubble ${m.role}`}>
                {m.content}
                {m.role === "assistant" && m.model && (
                  <span className="meta">
                    {m.provider} · {m.model}
                    {m.latency_ms != null ? ` · ${m.latency_ms} ms` : ""}
                  </span>
                )}
              </div>
            ))}
            {live && <div className="bubble assistant">{live}▌</div>}
            {error && <p className="error">Error: {error}</p>}
          </div>

          <div className="chat-input">
            <input
              value={draft}
              placeholder="Type a message…"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
              disabled={streaming}
            />
            <button className="btn" onClick={send} disabled={streaming || !draft.trim()}>
              {streaming ? "…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
