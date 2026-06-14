"use client";

/**
 * The assessor's practice round: 5 single-select MCQs for the module the learner is
 * currently in. The learner answers every question; "Submit practice" unlocks once
 * all are answered and grades server-side (the answer key never reaches the client).
 */

import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { Practice } from "@/lib/api";

type Selections = Record<string, string[]>; // question id → chosen choice text

export function PracticeCard({
  practice,
  busy,
  onSubmit,
}: {
  practice: Practice;
  busy: boolean;
  onSubmit: (selections: Selections) => void;
}) {
  const reduce = useReducedMotion();
  const [selections, setSelections] = useState<Selections>({});

  const answeredCount = practice.questions.filter(
    (q) => (selections[q.id]?.length ?? 0) > 0,
  ).length;
  const complete = answeredCount === practice.questions.length && practice.questions.length > 0;

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[88%] space-y-3 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      <p className="text-muted-foreground text-[11px]">
        Practice · {practice.title}
      </p>
      <ol className="space-y-3">
        {practice.questions.map((q) => {
          const chosen = selections[q.id] ?? [];
          return (
            <li key={q.id} className="space-y-1.5">
              <p className="text-foreground text-xs font-medium text-pretty">{q.prompt}</p>
              <div className="space-y-1">
                {q.choices.map((choice) => {
                  const picked = chosen.includes(choice);
                  return (
                    <label
                      key={choice}
                      className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
                        picked
                          ? "border-brand bg-brand/5"
                          : "border-border/60 hover:bg-accent/40"
                      }`}
                    >
                      <input
                        aria-label={choice}
                        type="radio"
                        name={q.id}
                        checked={picked}
                        onChange={() =>
                          setSelections((prev) => ({ ...prev, [q.id]: [choice] }))
                        }
                        className="accent-brand"
                      />
                      <span className="text-pretty">{choice}</span>
                    </label>
                  );
                })}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground text-[11px]">
          {answeredCount}/{practice.questions.length} answered
        </span>
        <Button
          size="sm"
          disabled={!complete || busy}
          onClick={() => onSubmit(selections)}
          className="text-xs"
        >
          Submit practice
        </Button>
      </div>
    </motion.div>
  );
}
