"use client";

/**
 * "Ask about your team" — the manager chat as a dedicated side section, with
 * multiple conversations (New chat + History), mirroring the learner experience.
 *
 * Sessions persist in localStorage per manager (no backend table needed); each
 * turn sends recent history so follow-ups stay coherent. Reuses the learner
 * chat's MessageBubble, TypingIndicator, and PipelineTrace so the guarded
 * gate -> route -> answer trace renders identically.
 */

import { History, Plus, SendHorizonal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MessageBubble } from "@/components/chat/message-bubble";
import { PipelineTrace } from "@/components/chat/pipeline-trace";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { PhaseTelemetry } from "@/lib/api";
import { streamManagerChat } from "@/lib/manager-api";

interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  phases: PhaseTelemetry[];
  streaming: boolean;
}

interface ChatSession {
  id: string;
  title: string;
  turns: Turn[];
  updatedAt: number;
}

interface ChatState {
  sessions: ChatSession[];
  activeId: string | null;
  loaded: boolean;
}

const STARTERS = [
  "Where is my biggest exam-readiness risk?",
  "Is the team's meeting load squeezing study time?",
  "How is platform engagement so far?",
];

const NEW_TITLE = "New chat";

function storageKey(employeeId: string): string {
  return `athenaeum.manager.chats.${employeeId}`;
}

function freshSession(): ChatSession {
  return { id: crypto.randomUUID(), title: NEW_TITLE, turns: [], updatedAt: Date.now() };
}

function titleFrom(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 40 ? `${t.slice(0, 40)}…` : t;
}

function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

function patchLast(turns: Turn[], patch: (turn: Turn) => Turn): Turn[] {
  const next = [...turns];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === "assistant") {
      next[i] = patch(next[i]);
      break;
    }
  }
  return next;
}

export function ManagerChat({ employeeId }: { employeeId: string }) {
  const [state, setState] = useState<ChatState>({
    sessions: [],
    activeId: null,
    loaded: false,
  });
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { sessions, activeId, loaded } = state;
  const key = storageKey(employeeId);

  // Load persisted sessions once (client-only; localStorage is unavailable on the server).
  useEffect(() => {
    let stored: ChatSession[] = [];
    try {
      const raw = window.localStorage.getItem(key);
      const parsed = raw ? (JSON.parse(raw) as ChatSession[]) : [];
      stored = Array.isArray(parsed) ? parsed.filter((s) => s.turns?.length > 0) : [];
    } catch {
      stored = [];
    }
    stored.sort((a, b) => b.updatedAt - a.updatedAt);
    const next: ChatState =
      stored.length > 0
        ? { sessions: stored, activeId: stored[0].id, loaded: true }
        : (() => {
            const fresh = freshSession();
            return { sessions: [fresh], activeId: fresh.id, loaded: true };
          })();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(next);
  }, [key]);

  // Persist sessions that have at least one turn.
  useEffect(() => {
    if (!loaded) return;
    const toStore = sessions
      .filter((s) => s.turns.length > 0)
      .map((s) => ({ ...s, turns: s.turns.map((t) => ({ ...t, streaming: false })) }));
    window.localStorage.setItem(key, JSON.stringify(toStore));
  }, [sessions, loaded, key]);

  const active = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId],
  );
  const turns = useMemo(() => active?.turns ?? [], [active]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  function patchAssistant(sid: string, patch: (turn: Turn) => Turn) {
    setState((prev) => ({
      ...prev,
      sessions: prev.sessions.map((s) =>
        s.id === sid ? { ...s, turns: patchLast(s.turns, patch), updatedAt: Date.now() } : s,
      ),
    }));
  }

  function newChat() {
    setHistoryOpen(false);
    setState((prev) => {
      const cur = prev.sessions.find((s) => s.id === prev.activeId);
      if (cur && cur.turns.length === 0) return prev; // already a fresh chat
      const fresh = freshSession();
      return { ...prev, sessions: [fresh, ...prev.sessions], activeId: fresh.id };
    });
  }

  function selectSession(id: string) {
    setHistoryOpen(false);
    setState((prev) => ({ ...prev, activeId: id }));
  }

  async function send(text: string) {
    const content = text.trim();
    const sid = activeId;
    if (!content || sending || !sid) return;
    setDraft("");
    setSending(true);

    const prior = (active?.turns ?? [])
      .filter((t) => t.content && !t.streaming)
      .map((t) => ({ role: t.role, content: t.content }));

    const userTurn: Turn = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      phases: [],
      streaming: false,
    };
    const botTurn: Turn = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      phases: [],
      streaming: true,
    };
    setState((prev) => ({
      ...prev,
      sessions: prev.sessions.map((s) =>
        s.id === sid
          ? {
              ...s,
              title: s.title === NEW_TITLE ? titleFrom(content) : s.title,
              turns: [...s.turns, userTurn, botTurn],
              updatedAt: Date.now(),
            }
          : s,
      ),
    }));

    try {
      await streamManagerChat(employeeId, content, prior, {
        onPhase: (phase) => patchAssistant(sid, (t) => ({ ...t, phases: [...t.phases, phase] })),
        onToken: (token) => patchAssistant(sid, (t) => ({ ...t, content: t.content + token })),
        onBlocked: (reason) => patchAssistant(sid, (t) => ({ ...t, content: reason })),
        onError: (message) => patchAssistant(sid, (t) => ({ ...t, content: message })),
        onDone: () => patchAssistant(sid, (t) => ({ ...t, streaming: false })),
      });
    } catch {
      patchAssistant(sid, (t) => ({
        ...t,
        content: t.content || "Something went wrong reaching the assistant.",
      }));
    } finally {
      patchAssistant(sid, (t) => ({ ...t, streaming: false }));
      setSending(false);
    }
  }

  const pastSessions = sessions.filter((s) => s.turns.length > 0);

  return (
    <section className="border-border bg-card/70 flex h-full flex-col overflow-hidden rounded-2xl border backdrop-blur-sm">
      {/* Header: title + New chat + History */}
      <header className="border-border/70 relative flex items-center justify-between gap-2 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 className="font-display text-foreground text-base leading-tight">
            Ask about your team
          </h2>
          <p className="text-muted-foreground truncate text-[11px]">
            {active && active.title !== NEW_TITLE ? active.title : "Aggregate-only, grounded"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setHistoryOpen((v) => !v)}
            aria-label="Chat history"
            aria-expanded={historyOpen}
          >
            <History className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={newChat} aria-label="New chat">
            <Plus className="size-4" />
          </Button>
        </div>

        {historyOpen && (
          <>
            <button
              type="button"
              aria-hidden
              tabIndex={-1}
              className="fixed inset-0 z-10 cursor-default"
              onClick={() => setHistoryOpen(false)}
            />
            <div className="border-border bg-popover absolute right-3 top-14 z-20 max-h-80 w-72 overflow-y-auto rounded-xl border p-1.5 shadow-lg">
              {pastSessions.length === 0 ? (
                <p className="text-muted-foreground px-2 py-3 text-xs">No past conversations yet.</p>
              ) : (
                pastSessions.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => selectSession(s.id)}
                    className={
                      "hover:bg-accent flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 text-left transition-colors" +
                      (s.id === activeId ? " bg-accent" : "")
                    }
                  >
                    <span className="text-foreground line-clamp-1 text-sm">{s.title}</span>
                    <span className="text-muted-foreground text-[10px]">
                      {relativeTime(s.updatedAt)}
                    </span>
                  </button>
                ))
              )}
            </div>
          </>
        )}
      </header>

      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {turns.length === 0 ? (
          <div className="flex flex-col gap-2">
            <p className="text-muted-foreground text-sm">Try one of these, or ask your own:</p>
            {STARTERS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void send(s)}
                className="border-border bg-background/60 text-muted-foreground hover:text-foreground hover:border-brand/40 rounded-xl border px-3 py-2 text-left text-xs transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          turns.map((turn) =>
            turn.role === "user" ? (
              <MessageBubble key={turn.id} role="user" content={turn.content} />
            ) : (
              <div key={turn.id} className="space-y-2">
                {turn.phases.length > 0 && <PipelineTrace phases={turn.phases} defaultOpen={false} />}
                {turn.streaming && !turn.content ? (
                  <TypingIndicator />
                ) : (
                  turn.content && (
                    <MessageBubble
                      role="assistant"
                      content={turn.content}
                      streaming={turn.streaming}
                    />
                  )
                )}
              </div>
            ),
          )
        )}
      </div>

      {/* Composer */}
      <form
        className="border-border/70 flex items-end gap-2 border-t px-3 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(draft);
            }
          }}
          placeholder="Ask about readiness, capacity, certs…"
          rows={1}
          className="max-h-28 min-h-10 flex-1 resize-none"
          disabled={sending}
        />
        <Button type="submit" size="icon" disabled={sending || !draft.trim()}>
          <SendHorizonal className="size-4" />
          <span className="sr-only">Send</span>
        </Button>
      </form>
    </section>
  );
}
