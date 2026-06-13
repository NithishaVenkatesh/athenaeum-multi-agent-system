"use client";

/**
 * The Modules tab — the study plan's module-level completion view.
 *
 * Modules are done sequentially: the first incomplete, unlocked module is the
 * active one — it expands to show its content (markdown from approved material)
 * and a "Mark complete" action (completion by a test comes later). Earlier
 * modules show as done; later ones are locked until their predecessor is done.
 */

import { CalendarClock, CheckCircle2, Circle, Loader2, Lock } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  completeModule,
  getModuleContent,
  listModules,
  type CourseModuleProgress,
  type ModuleContent,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function fmtDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function fmtMinutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h && m ? `${h}h ${m}m` : h ? `${h}h` : `${m}m`;
}

function statusOf(m: CourseModuleProgress): "done" | "active" | "locked" {
  if (m.completed) return "done";
  return m.locked ? "locked" : "active";
}

function ModuleBody({ courseId, moduleId }: { courseId: string; moduleId: string }) {
  const [content, setContent] = useState<ModuleContent | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    getModuleContent(courseId, moduleId)
      .then((c) => active && setContent(c))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [courseId, moduleId]);

  if (error) return <p className="text-muted-foreground text-xs">Content unavailable.</p>;
  if (!content)
    return (
      <p className="text-muted-foreground flex items-center gap-2 text-xs">
        <Loader2 className="size-3.5 animate-spin" /> Loading content…
      </p>
    );

  return (
    <div className="prose-athenaeum text-sm leading-relaxed">
      <ReactMarkdown>{content.content}</ReactMarkdown>
    </div>
  );
}

export function ModulesView({ courseId }: { courseId: string }) {
  const [modules, setModules] = useState<CourseModuleProgress[] | null>(null);
  const [completing, setCompleting] = useState<string | null>(null);

  const reload = useCallback(() => {
    listModules(courseId)
      .then(setModules)
      .catch(() => setModules([]));
  }, [courseId]);

  useEffect(() => reload(), [reload]);

  async function handleComplete(moduleId: string) {
    setCompleting(moduleId);
    try {
      setModules(await completeModule(courseId, moduleId));
      toast.success("Module complete", { description: "The next module is unlocked." });
    } catch {
      toast.error("Could not complete", { description: "Finish the earlier modules first." });
    } finally {
      setCompleting(null);
    }
  }

  if (modules === null) {
    return (
      <div className="text-muted-foreground mx-auto flex max-w-2xl items-center gap-2 px-4 py-16 text-sm">
        <Loader2 className="size-4 animate-spin" /> Loading your modules…
      </div>
    );
  }

  if (modules.length === 0) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <h2 className="font-display text-2xl tracking-tight">No modules yet</h2>
        <p className="text-muted-foreground mt-2 text-sm text-pretty">
          Build a study plan in the Chat tab and your course modules will appear here, in order,
          each with a complete-by date.
        </p>
      </div>
    );
  }

  const done = modules.filter((m) => m.completed).length;

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6">
      <header className="mb-4">
        <h2 className="font-display text-2xl tracking-tight">Modules</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          {done} of {modules.length} complete · done in order
        </p>
        <div className="bg-muted mt-2 h-1.5 overflow-hidden rounded-full">
          <div
            className="bg-brand h-full rounded-full transition-all"
            style={{ width: `${(done / modules.length) * 100}%` }}
          />
        </div>
      </header>

      <ol className="space-y-2">
        {modules.map((m) => {
          const status = statusOf(m);
          return (
            <li
              key={m.module_id}
              className={cn(
                "rounded-2xl border p-4 transition-colors",
                status === "active"
                  ? "border-brand/40 bg-card"
                  : "border-border/70 bg-card/50",
                status === "locked" && "opacity-60",
              )}
            >
              <div className="flex items-start gap-3">
                <span className="mt-0.5 shrink-0">
                  {status === "done" ? (
                    <CheckCircle2 className="text-brand size-5" />
                  ) : status === "locked" ? (
                    <Lock className="text-muted-foreground size-5" />
                  ) : (
                    <Circle className="text-brand size-5" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-muted-foreground text-[11px] font-medium">
                      Module {m.sequence}
                    </span>
                    <span className="text-muted-foreground inline-flex items-center gap-1 text-[11px]">
                      <CalendarClock className="size-3" />
                      by {fmtDate(m.complete_before)}
                    </span>
                    <span className="text-muted-foreground text-[11px]">
                      ~{fmtMinutes(m.estimated_minutes)}
                    </span>
                  </div>
                  <h3 className="font-display text-foreground mt-0.5 text-base tracking-tight">
                    {m.title}
                  </h3>

                  {status === "active" && (
                    <div className="mt-3 space-y-3">
                      <ModuleBody courseId={courseId} moduleId={m.module_id} />
                      <Button
                        size="sm"
                        onClick={() => handleComplete(m.module_id)}
                        disabled={completing === m.module_id}
                        className="text-xs"
                      >
                        {completing === m.module_id ? "Marking…" : "Mark module complete"}
                      </Button>
                    </div>
                  )}
                  {status === "locked" && (
                    <p className="text-muted-foreground mt-1 text-xs">
                      Complete the previous module to unlock.
                    </p>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
