"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function isTypingElsewhere(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || (el as HTMLElement).isContentEditable;
}

export function ChatComposer({
  onSend,
  busy,
  placeholder = "Ask about a course…",
}: {
  onSend: (text: string) => void;
  busy: boolean;
  placeholder?: string;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus the composer on mount and whenever the learner starts typing a
  // printable character anywhere on the page (ChatGPT-style autofocus).
  useEffect(() => {
    textareaRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.length !== 1) return; // ignore non-printable keys
      if (isTypingElsewhere()) return;
      textareaRef.current?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function submit() {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text);
    setValue("");
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="border-border bg-card focus-within:border-brand/50 focus-within:ring-brand/15 flex items-end gap-2 rounded-2xl border p-2 shadow-sm transition-shadow focus-within:ring-[3px]"
    >
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        aria-label="Message"
        rows={1}
        className="max-h-40 min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      <Button
        type="submit"
        size="icon"
        disabled={busy || value.trim().length === 0}
        aria-label="Send message"
        className="active:scale-97 transition-transform"
      >
        <ArrowUp />
      </Button>
    </form>
  );
}
