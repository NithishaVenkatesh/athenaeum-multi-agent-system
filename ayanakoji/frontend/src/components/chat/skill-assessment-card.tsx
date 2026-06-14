"use client";

/**
 * The multi-tab skill check. One tab per module, each with up to 4 questions.
 * MCQ renders single-select (radio), MSQ multi-select (checkbox, "select all that
 * apply"). The learner steps module-by-module with "Next module" (which scrolls
 * the card back to the top); "Submit skill check" appears only on the last module
 * and unlocks once every question across every tab is answered.
 */

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Check } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { SkillAnswer, SkillCheck } from "@/lib/api";

type Selections = Record<string, string[]>; // question id → chosen choice texts

function toggle(list: string[], value: string, single: boolean): string[] {
  if (single) return [value];
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

export function SkillAssessmentCard({
  check,
  busy,
  onSubmit,
}: {
  check: SkillCheck;
  busy: boolean;
  onSubmit: (answers: SkillAnswer[]) => void;
}) {
  const reduce = useReducedMotion();
  const [tab, setTab] = useState(0);
  const [selections, setSelections] = useState<Selections>({});
  const cardRef = useRef<HTMLDivElement>(null);

  const isLastModule = tab === check.modules.length - 1;

  /** Switch module and bring the top of the card into view (questions reset to top). */
  function goToModule(index: number) {
    setTab(index);
    cardRef.current?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "start",
    });
  }

  const allQuestions = useMemo(
    () =>
      check.modules.flatMap((m) =>
        m.questions.map((q) => ({ moduleId: m.module_id, q })),
      ),
    [check],
  );
  const answeredCount = allQuestions.filter(
    ({ q }) => (selections[q.id]?.length ?? 0) > 0,
  ).length;
  const complete = answeredCount === allQuestions.length && allQuestions.length > 0;
  const active = check.modules[tab];

  function moduleAnswered(moduleId: string): boolean {
    const mod = check.modules.find((m) => m.module_id === moduleId);
    return (
      !!mod && mod.questions.every((q) => (selections[q.id]?.length ?? 0) > 0)
    );
  }

  function submit() {
    const answers: SkillAnswer[] = allQuestions.map(({ moduleId, q }) => ({
      module_id: moduleId,
      question_id: q.id,
      selections: selections[q.id] ?? [],
    }));
    onSubmit(answers);
  }

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      ref={cardRef}
      className="border-brand/30 bg-card/70 max-w-[88%] space-y-3 rounded-2xl rounded-bl-md border p-3 shadow-sm scroll-mt-4"
    >
      {/* Tabs: one per module, with a completion tick */}
      <div className="flex flex-wrap gap-1.5">
        {check.modules.map((m, i) => (
          <button
            key={m.module_id}
            type="button"
            onClick={() => goToModule(i)}
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
              i === tab
                ? "border-brand bg-brand/10 text-brand"
                : "border-border/60 text-muted-foreground hover:text-foreground"
            }`}
          >
            {moduleAnswered(m.module_id) && <Check className="size-3" />}
            <span className="max-w-40 truncate">{m.title}</span>
          </button>
        ))}
      </div>

      {/* Active tab questions */}
      {active && (
        <ol className="space-y-3">
          {active.questions.map((q) => {
            const single = q.kind === "mcq";
            const chosen = selections[q.id] ?? [];
            return (
              <li key={q.id} className="space-y-1.5">
                <p className="text-foreground text-xs font-medium text-pretty">
                  {q.prompt}
                  {!single && (
                    <span className="text-muted-foreground ml-1 text-[10px]">
                      (select all that apply)
                    </span>
                  )}
                </p>
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
                          type={single ? "radio" : "checkbox"}
                          name={q.id}
                          checked={picked}
                          onChange={() =>
                            setSelections((prev) => ({
                              ...prev,
                              [q.id]: toggle(chosen, choice, single),
                            }))
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
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground text-[11px]">
          {answeredCount}/{allQuestions.length} answered
        </span>
        {isLastModule ? (
          <Button
            size="sm"
            disabled={!complete || busy}
            onClick={submit}
            className="text-xs"
          >
            Submit skill check
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => goToModule(tab + 1)}
            className="gap-1 text-xs"
          >
            Next module
            <ArrowRight className="size-3.5" />
          </Button>
        )}
      </div>
    </motion.div>
  );
}
