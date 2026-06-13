"use client";

/**
 * The 'pursue this course?' tool the Foundry-IQ agent offers after a grounded
 * answer. Accepting links the course to this chat (catalog_id) and starts
 * attempt 1 — the learner is enriched with the course they commit to.
 */

import { motion, useReducedMotion } from "framer-motion";
import { BookOpen, Check, GraduationCap } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { CourseSuggestion } from "@/lib/api";

type AcceptState = "idle" | "accepting" | "accepted" | "declined";

export function CourseSuggestionCard({
  suggestion,
  state,
  onAccept,
  onDecline,
}: {
  suggestion: CourseSuggestion;
  state: AcceptState;
  onAccept: () => void;
  onDecline: () => void;
}) {
  const reduce = useReducedMotion();
  const settled = state === "accepted" || state === "declined";

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 from-card to-brand/5 max-w-[78%] overflow-hidden rounded-2xl rounded-bl-md border bg-gradient-to-br shadow-sm"
    >
      <div className="flex items-start gap-3 p-4">
        <span className="bg-brand/10 text-brand mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl">
          <BookOpen className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="bg-brand/10 text-brand inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide">
              <GraduationCap className="size-3" />
              {suggestion.cert}
            </span>
            <span className="text-muted-foreground text-[11px]">Suggested course</span>
          </div>
          <h3 className="font-display text-foreground mt-1.5 text-base leading-tight tracking-tight">
            {suggestion.title}
          </h3>
          <p className="text-muted-foreground mt-1 text-xs leading-relaxed text-pretty">
            {suggestion.pitch}
          </p>

          {suggestion.prep_points.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {suggestion.prep_points.map((point) => (
                <li key={point} className="text-foreground/90 flex items-start gap-2 text-xs">
                  <Check className="text-brand mt-0.5 size-3.5 shrink-0" />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="border-border/60 bg-card/40 flex items-center justify-between gap-3 border-t px-4 py-2.5">
        <p className="text-muted-foreground text-[11px]">
          {state === "accepted"
            ? "Enrolled — this chat is now your course workspace."
            : state === "declined"
              ? "No problem — ask me anything else."
              : "Ready to pursue this and prepare the above?"}
        </p>
        {!settled && (
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onDecline}
              disabled={state === "accepting"}
              className="h-8 text-xs"
            >
              Not now
            </Button>
            <Button
              size="sm"
              onClick={onAccept}
              disabled={state === "accepting"}
              className="h-8 text-xs"
            >
              {state === "accepting" ? "Enrolling…" : "Pursue this course"}
            </Button>
          </div>
        )}
        {state === "accepted" && (
          <span className="text-brand inline-flex items-center gap-1 text-xs font-medium">
            <Check className="size-4" /> Enrolled
          </span>
        )}
      </div>
    </motion.div>
  );
}
