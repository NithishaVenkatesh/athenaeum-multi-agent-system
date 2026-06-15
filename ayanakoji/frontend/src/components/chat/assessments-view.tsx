"use client";

/**
 * Evaluations surface for a course. Lists the canonical set — two per module (a
 * quiz and an oral exam) — and unlocks them like modules: a module's evaluations
 * open once the prior module is complete, and the oral waits on that module's quiz.
 * Completed evaluations show a score and link to a read-only review or a retake.
 */

import {
  ArrowRight,
  CheckCircle2,
  GraduationCap,
  Lightbulb,
  Lock,
  MessageSquareText,
  RotateCcw,
  ScrollText,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { listEvaluations, type Evaluation } from "@/lib/api";

const TYPE_META = {
  choices: { label: "Quiz", icon: ScrollText, blurb: "5 questions" },
  llm: { label: "Oral exam", icon: MessageSquareText, blurb: "Spoken with an examiner" },
} as const;

function takeHref(courseId: string, e: Evaluation): string {
  const leaf = e.type === "choices" ? "choices" : "llm";
  return `/chat/${courseId}/modules/${e.module_id}/assessment/${leaf}`;
}

function EvaluationRow({ courseId, evaluation }: { courseId: string; evaluation: Evaluation }) {
  const meta = TYPE_META[evaluation.type];
  const Icon = meta.icon;
  const graded = evaluation.review_assessment_id !== null;
  const reviewHref = `/chat/${courseId}/assessment/${evaluation.review_assessment_id}/review`;

  const scoreLabel =
    evaluation.score !== null ? `${Math.round(evaluation.score)}/10` : null;

  return (
    <div
      className={`flex items-center gap-3 px-4 py-3 ${
        evaluation.locked ? "opacity-55" : ""
      }`}
    >
      <span
        className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${
          evaluation.locked
            ? "bg-muted text-muted-foreground"
            : evaluation.completed
              ? "bg-brand/10 text-brand"
              : "bg-accent text-foreground"
        }`}
      >
        {evaluation.locked ? <Lock className="size-4" /> : <Icon className="size-4" />}
      </span>

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{meta.label}</p>
        <p className="text-muted-foreground truncate text-xs">
          {evaluation.locked
            ? evaluation.type === "llm"
              ? "Pass this module's quiz to unlock"
              : "Complete the previous module to unlock"
            : meta.blurb}
        </p>
      </div>

      {/* Status pill */}
      {!evaluation.locked && graded && (
        <span
          className={`inline-flex items-center gap-1 text-xs font-medium tabular-nums ${
            evaluation.passed ? "text-brand" : "text-destructive"
          }`}
        >
          {evaluation.passed ? (
            <CheckCircle2 className="size-3.5" />
          ) : (
            <XCircle className="size-3.5" />
          )}
          {scoreLabel}
        </span>
      )}

      {/* Actions */}
      <div className="flex shrink-0 items-center gap-1.5">
        {evaluation.locked ? (
          <Badge variant="secondary" className="text-[10px]">
            Locked
          </Badge>
        ) : graded ? (
          <>
            <Link
              href={reviewHref}
              className="border-border hover:bg-accent inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors"
            >
              Review
            </Link>
            {/* Feedback is grounded on the learner's own answers, so it only makes
                sense once a test was missed. Reuses the post-test deep link, which
                lands on the Chat tab and auto-streams grounded feedback. */}
            {evaluation.passed === false && (
              <Link
                href={`/chat/${courseId}?feedback=${evaluation.type}&module=${evaluation.module_id}`}
                className="border-border hover:bg-accent inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors"
              >
                <Lightbulb className="size-3.5" />
                Get feedback
              </Link>
            )}
            <Link
              href={`${takeHref(courseId, evaluation)}?retake=1`}
              className="text-brand hover:bg-brand/5 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
            >
              <RotateCcw className="size-3.5" />
              {evaluation.passed ? "Retake" : "Try again"}
            </Link>
          </>
        ) : (
          <Link
            href={takeHref(courseId, evaluation)}
            className="bg-brand inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
          >
            {evaluation.attempted ? "Resume" : "Start"}
            <ArrowRight className="size-3.5" />
          </Link>
        )}
      </div>
    </div>
  );
}

export function AssessmentsView({ courseId }: { courseId: string }) {
  const [evaluations, setEvaluations] = useState<Evaluation[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listEvaluations(courseId, controller.signal)
      .then(setEvaluations)
      .catch(() => {
        if (!controller.signal.aborted) setEvaluations([]);
      });
    return () => controller.abort();
  }, [courseId]);

  const isEmpty = evaluations !== null && evaluations.length === 0;
  const passedCount = evaluations?.filter((e) => e.passed === true).length ?? 0;

  // Group the flat list into modules (preserves backend order: quiz then oral).
  const modules: { module_id: string; title: string; sequence: number; items: Evaluation[] }[] =
    [];
  for (const e of evaluations ?? []) {
    let group = modules.find((m) => m.module_id === e.module_id);
    if (!group) {
      group = { module_id: e.module_id, title: e.module_title, sequence: e.sequence, items: [] };
      modules.push(group);
    }
    group.items.push(e);
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-10">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl tracking-tight">Evaluations</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            A quiz and an oral exam for each module. Pass both to complete a module.
          </p>
        </div>
        {evaluations && evaluations.length > 0 && (
          <span className="border-border bg-card text-muted-foreground shrink-0 rounded-full border px-3 py-1 text-xs font-medium tabular-nums">
            {passedCount}/{evaluations.length} passed
          </span>
        )}
      </div>

      {evaluations === null ? (
        <ul className="mt-8 space-y-3">
          {[0, 1, 2].map((i) => (
            <li key={i} className="border-border bg-card h-28 animate-pulse rounded-2xl border" />
          ))}
        </ul>
      ) : isEmpty ? (
        <div className="border-border mt-8 flex flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-20 text-center">
          <span className="bg-accent text-brand flex size-12 items-center justify-center rounded-xl">
            <GraduationCap className="size-6" />
          </span>
          <h2 className="font-display mt-4 text-xl">No evaluations yet</h2>
          <p className="text-muted-foreground mt-2 max-w-sm text-pretty text-sm">
            Build and approve a study plan first. Each module then gets a quiz and an oral exam
            that unlock as you progress.
          </p>
        </div>
      ) : (
        <div className="mt-8 space-y-4">
          {modules.map((m) => (
            <section
              key={m.module_id}
              className="border-border bg-card overflow-hidden rounded-2xl border"
            >
              <header className="border-border/70 flex items-center gap-2 border-b px-4 py-2.5">
                <span className="bg-brand/10 text-brand flex size-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold tabular-nums">
                  {m.sequence}
                </span>
                <h2 className="truncate text-sm font-semibold">{m.title}</h2>
              </header>
              <div className="divide-border/60 divide-y">
                {m.items.map((e) => (
                  <EvaluationRow key={`${e.module_id}-${e.type}`} courseId={courseId} evaluation={e} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
