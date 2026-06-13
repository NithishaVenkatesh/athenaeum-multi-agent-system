"use client";

import { motion, useReducedMotion } from "framer-motion";
import ReactMarkdown from "react-markdown";

import { cn } from "@/lib/utils";

export function MessageBubble({
  role,
  content,
  streaming = false,
}: {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}) {
  const reduce = useReducedMotion();
  const isUser = role === "user";

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-md whitespace-pre-wrap"
            : "bg-card text-foreground border-border rounded-bl-md border",
        )}
      >
        {/* User text is literal; assistant replies render as markdown. */}
        {isUser ? (
          content
        ) : (
          <div className="prose-athenaeum prose-chat">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}
        {streaming && (
          <span className="bg-brand ml-1 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse rounded-sm" />
        )}
      </div>
    </motion.div>
  );
}
