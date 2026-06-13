"use client";

/**
 * The chat surface — and a chat IS a course. Used for both a brand-new chat
 * (no courseId: the first message creates the course and the URL becomes
 * /chat/<id> without a remount) and an existing one (courseId: loaded from the
 * backend). Replies stream token-by-token over SSE; the backend persists turns.
 */

import { useEffect, useRef, useState } from "react";

import { ChatComposer } from "@/components/chat/chat-composer";
import { MessageBubble } from "@/components/chat/message-bubble";
import { RenameTitle } from "@/components/chat/rename-title";
import { useWorkspace } from "@/components/workspace/workspace-context";
import { Badge } from "@/components/ui/badge";
import {
  createCourse,
  getCourse,
  streamMessage,
  type ChatMessage,
  type Course,
} from "@/lib/api";

export function ChatView({ courseId }: { courseId?: string }) {
  const { personaId, reloadCourses } = useWorkspace();
  const [course, setCourse] = useState<Course | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load an existing course's conversation.
  useEffect(() => {
    if (!courseId) return;
    let active = true;
    getCourse(courseId)
      .then((loaded) => {
        if (active) {
          setCourse(loaded);
          setMessages(loaded.messages);
        }
      })
      .catch(() => active && setLoadError("Could not load this chat."));
    return () => {
      active = false;
    };
  }, [courseId]);

  // Keep the latest turn in view as content streams in.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function handleSend(text: string) {
    setBusy(true);
    let id = course?.id ?? courseId;
    try {
      if (!id) {
        const created = await createCourse(personaId, text);
        setCourse(created);
        id = created.id;
        // Reflect the new course in the URL without a navigation/remount so the
        // stream below keeps running on this mounted component.
        window.history.replaceState(null, "", `/chat/${created.id}`);
        void reloadCourses();
      }
      setMessages((prev) => [...prev, { role: "user", content: text }]);
      let accumulated = "";
      setStreaming("");
      await streamMessage(id, text, (token) => {
        accumulated += token;
        setStreaming(accumulated);
      });
      setMessages((prev) => [...prev, { role: "assistant", content: accumulated }]);
      setStreaming(null);
      void reloadCourses();
    } catch {
      setStreaming(null);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong generating a reply. Please try again.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  const isEmpty = messages.length === 0 && streaming === null;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
      {course && (
        <div className="flex flex-wrap items-center gap-3 py-4">
          <RenameTitle
            key={course.chat_name}
            course={course}
            onRenamed={(updated) => {
              setCourse(updated);
              void reloadCourses();
            }}
          />
          {course.catalog_title && (
            <Badge variant="secondary" className="font-mono text-[0.65rem]">
              {course.catalog_title}
            </Badge>
          )}
        </div>
      )}

      <div className="flex-1 space-y-4 py-4">
        {loadError ? (
          <p role="alert" className="text-destructive text-sm">
            {loadError}
          </p>
        ) : isEmpty ? (
          <div className="flex h-full flex-col items-center justify-center pt-24 text-center">
            <h2 className="font-display text-3xl tracking-tight">
              What would you like to learn?
            </h2>
            <p className="text-muted-foreground mt-2 max-w-sm text-sm text-pretty">
              Ask about any topic to begin. Your first message starts a course, and
              the whole conversation becomes it.
            </p>
          </div>
        ) : (
          <>
            {messages.map((message, index) => (
              <MessageBubble
                key={index}
                role={message.role}
                content={message.content}
              />
            ))}
            {streaming !== null && (
              <MessageBubble role="assistant" content={streaming} streaming />
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="bg-paper sticky bottom-0 pb-5 pt-2">
        <ChatComposer onSend={handleSend} busy={busy} />
        <p className="text-muted-foreground/70 mt-2 text-center text-xs">
          Replies are AI-generated and may be imperfect.
        </p>
      </div>
    </div>
  );
}
