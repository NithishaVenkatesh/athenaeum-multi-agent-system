"use client";

import {
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Dumbbell,
  Loader2,
  Lock,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import { Button } from "@/components/ui/button";
import {
  getModuleContent,
  listModuleAssessments,
  listModules,
  type CourseModuleProgress,
  type ModuleAssessmentSummary,
  type ModuleContent,
} from "@/lib/api";

function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function ModuleDetailView({
  courseId,
  moduleId,
}: {
  courseId: string;
  moduleId: string;
}) {
  const [modules, setModules] = useState<CourseModuleProgress[] | null>(null);
  const [content, setContent] = useState<ModuleContent | null>(null);
  const [attempts, setAttempts] = useState<ModuleAssessmentSummary[]>([]);

  const reload = useCallback(() => {
    listModules(courseId)
      .then(setModules)
      .catch(() => setModules([]));
    listModuleAssessments(courseId, moduleId)
      .then(setAttempts)
      .catch(() => setAttempts([]));
  }, [courseId, moduleId]);

  useEffect(() => reload(), [reload]);
  useEffect(() => {
    let active = true;
    getModuleContent(courseId, moduleId)
      .then((c) => active && setContent(c))
      .catch(() => active && setContent(null));
    return () => {
      active = false;
    };
  }, [courseId, moduleId]);

  const modulesHref = `/chat/${courseId}/modules`;
  const current = modules?.find((m) => m.module_id === moduleId) ?? null;
  const index = modules?.findIndex((m) => m.module_id === moduleId) ?? -1;
  const next = modules && index >= 0 ? (modules[index + 1] ?? null) : null;
  const assessmentHref = `/chat/${courseId}/modules/${moduleId}/assessment/choices`;
  // The Practise button lands in the chat, which auto-starts a generated practice
  // round for THIS module (formative; never counts toward the official evaluation).
  const practiseHref = `/chat/${courseId}?practise=${moduleId}`;

  // "Cleared" is permanent (passed at least once), derived from attempts_to_pass —
  // a later failed retake of the latest attempt must not flip this back.
  const choicesPassed = attempts.some(
    (a) => a.type === "choices" && a.attempts_to_pass !== null,
  );
  const llmPassed = attempts.some((a) => a.type === "llm" && a.attempts_to_pass !== null);
  const totalAttempts = attempts.reduce((sum, a) => sum + a.attempt_number, 0);

  if (modules === null) {
    return (
      <div className="text-muted-foreground mx-auto flex max-w-2xl items-center gap-2 px-4 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading module…
      </div>
    );
  }

  if (!current) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <Link href={modulesHref} className="text-brand inline-flex items-center gap-1 text-sm">
          <ArrowLeft className="size-4" /> Back to modules
        </Link>
        <p className="text-muted-foreground mt-4 text-sm">This module is not in your plan.</p>
      </div>
    );
  }

  if (current.locked) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <Link href={modulesHref} className="text-brand inline-flex items-center gap-1 text-sm">
          <ArrowLeft className="size-4" /> Back to modules
        </Link>
        <div className="text-muted-foreground mt-6 flex items-center gap-2 text-sm">
          <Lock className="size-4" /> Complete the earlier modules to unlock this one.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6">
      <Link
        href={modulesHref}
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Modules
      </Link>

      <header className="mt-3">
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-[11px]">
          <span className="font-medium">Module {current.sequence}</span>
          <span className="inline-flex items-center gap-1">
            <CalendarClock className="size-3" /> by {fmtDate(current.complete_before)}
          </span>
          {current.completed && (
            <span className="text-brand inline-flex items-center gap-1 font-medium">
              <CheckCircle2 className="size-3.5" /> Completed
            </span>
          )}
        </div>
        <h1 className="font-display text-foreground mt-1 text-2xl tracking-tight">
          {current.title}
        </h1>
      </header>

      <article className="prose-athenaeum mt-5 text-sm leading-relaxed">
        {content ? (
          <ReactMarkdown>{content.content}</ReactMarkdown>
        ) : (
          <p className="text-muted-foreground flex items-center gap-2">
            <Loader2 className="size-3.5 animate-spin" /> Loading content…
          </p>
        )}
      </article>

      <div className="border-border mt-8 border-t pt-4">
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              {current.completed ? (
                <span className="text-brand inline-flex items-center gap-1.5 text-sm font-medium">
                  <CheckCircle2 className="size-4" /> Module complete
                </span>
              ) : (
                <Link href={assessmentHref}>
                  <Button size="sm" className="gap-1.5">
                    <ClipboardCheck className="size-4" />
                    Take Assessment
                  </Button>
                </Link>
              )}
              <Link href={practiseHref}>
                <Button size="sm" variant="outline" className="gap-1.5">
                  <Dumbbell className="size-4" />
                  Practise
                </Button>
              </Link>
            </div>
            {totalAttempts > 0 && !current.completed && (
              <span className="text-muted-foreground text-[11px]">
                {totalAttempts} attempt{totalAttempts !== 1 ? "s" : ""} ·{" "}
                {choicesPassed ? "Quiz ✓" : "Quiz pending"} ·{" "}
                {llmPassed ? "Oral ✓" : "Oral pending"}
              </span>
            )}
          </div>
          {next && (
            <Link
              href={`/chat/${courseId}/modules/${next.module_id}`}
              className="text-brand inline-flex items-center gap-1 text-sm font-medium"
            >
              Next module <ArrowRight className="size-4" />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
