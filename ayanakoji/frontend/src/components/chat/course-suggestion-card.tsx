"use client";

/**
 * The course-selection tool the agent offers — one or more courses the learner
 * can choose from. Choosing one links it to this chat (catalog_id) and starts
 * attempt 1, enriching the learner with the course they commit to.
 *
 * One option → a single confirm card. Several → a "pick one" chooser (e.g. a
 * profile-based recommendation across the learner's current and target tracks).
 */

import { motion, useReducedMotion } from "framer-motion";
import { BookOpen, Check, GraduationCap } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { CourseSuggestion, Suggestion } from "@/lib/api";

type AcceptState = "idle" | "accepting" | "accepted" | "declined";

const LEVEL_LABEL: Record<string, string> = {
  foundational: "Foundational",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

function OptionRow({
  option,
  state,
  chosen,
  onChoose,
}: {
  option: CourseSuggestion;
  state: AcceptState;
  chosen: boolean;
  onChoose: () => void;
}) {
  const settled = state === "accepted" || state === "declined";
  return (
    <div className="border-border/60 bg-card/50 flex items-start gap-3 rounded-xl border p-3">
      <span className="bg-brand/10 text-brand mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg">
        <BookOpen className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="bg-brand/10 text-brand inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold">
            <GraduationCap className="size-3" />
            {option.cert}
          </span>
          {option.level && LEVEL_LABEL[option.level] && (
            <span className="text-muted-foreground text-[10px]">{LEVEL_LABEL[option.level]}</span>
          )}
        </div>
        <h3 className="font-display text-foreground mt-1 text-[15px] leading-tight tracking-tight">
          {option.title}
        </h3>
        <p className="text-muted-foreground mt-0.5 text-xs leading-relaxed text-pretty">
          {option.reason || option.pitch}
        </p>
        {option.prep_points.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
            {option.prep_points.slice(0, 3).map((point) => (
              <li key={point} className="text-foreground/80 flex items-center gap-1 text-[11px]">
                <Check className="text-brand size-3 shrink-0" />
                {point}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="shrink-0 self-center">
        {chosen && state === "accepted" ? (
          <span className="text-brand inline-flex items-center gap-1 text-xs font-medium">
            <Check className="size-4" /> Enrolled
          </span>
        ) : (
          !settled && (
            <Button
              size="sm"
              onClick={onChoose}
              disabled={state === "accepting"}
              className="h-8 text-xs"
            >
              {state === "accepting" && chosen ? "Enrolling…" : "Choose"}
            </Button>
          )
        )}
      </div>
    </div>
  );
}

export function CourseSuggestionCard({
  suggestion,
  state,
  chosenId,
  onAccept,
  onDecline,
}: {
  suggestion: Suggestion;
  state: AcceptState;
  chosenId: string | null;
  onAccept: (catalogId: string) => void;
  onDecline: () => void;
}) {
  const reduce = useReducedMotion();
  const settled = state === "accepted" || state === "declined";

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 from-card to-brand/5 max-w-[85%] space-y-2 rounded-2xl rounded-bl-md border bg-gradient-to-br p-3 shadow-sm"
    >
      <p className="text-foreground/90 px-1 text-xs font-medium">
        {state === "accepted"
          ? "Enrolled — this chat is now your course workspace."
          : state === "declined"
            ? "No problem — ask me anything else."
            : suggestion.prompt}
      </p>

      {suggestion.options.map((option) => (
        <OptionRow
          key={option.catalog_id}
          option={option}
          state={state}
          chosen={chosenId === option.catalog_id}
          onChoose={() => onAccept(option.catalog_id)}
        />
      ))}

      {!settled && (
        <div className="flex justify-end px-1">
          <Button variant="ghost" size="sm" onClick={onDecline} className="h-7 text-xs">
            Not now
          </Button>
        </div>
      )}
    </motion.div>
  );
}
