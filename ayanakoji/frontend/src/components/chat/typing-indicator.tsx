"use client";

import { motion, useReducedMotion } from "framer-motion";

/**
 * The assistant's "thinking" bubble: three dots that rise and fall in sequence
 * while a turn is streaming but has produced no visible reply yet. It mirrors the
 * assistant MessageBubble shell so the swap to real content is seamless.
 */
export function TypingIndicator() {
  const reduce = useReducedMotion();

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className="flex w-full justify-start"
    >
      <div
        role="status"
        aria-label="Assistant is thinking"
        className="flex items-center gap-1.5 rounded-2xl rounded-bl-md px-4 py-3.5"
      >
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            aria-hidden
            className="bg-muted-foreground/70 inline-block size-1.5 rounded-full"
            animate={
              reduce
                ? { opacity: [0.35, 1, 0.35] }
                : { y: [0, -4, 0], opacity: [0.4, 1, 0.4] }
            }
            transition={{
              duration: reduce ? 1.2 : 0.9,
              ease: "easeInOut",
              repeat: Infinity,
              delay: i * 0.15,
            }}
          />
        ))}
        <span className="sr-only">Thinking…</span>
      </div>
    </motion.div>
  );
}
