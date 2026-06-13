"use client";

/**
 * The Modules tab — a navigation index into the course's modules. Each module
 * is its own page (content + completion). Modules are done in order: the first
 * incomplete unlocked module is active; completed modules stay accessible to
 * revisit; later ones are locked until their predecessor is done.
 */

import { CalendarClock, CheckCircle2, ChevronRight, Circle, Loader2, Lock } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listModules, type CourseModuleProgress } from "@/lib/api";
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

function ModuleRow({ courseId, m }: { courseId: string; m: CourseModuleProgress }) {
  const status = statusOf(m);
  const icon =
    status === "done" ? (
      <CheckCircle2 className="text-brand size-5" />
    ) : status === "locked" ? (
      <Lock className="text-muted-foreground size-5" />
    ) : (
      <Circle className="text-brand size-5" />
    );

  const body = (
    <div
      className={cn(
        "flex items-center gap-3 rounded-2xl border p-4 transition-colors",
        status === "active" ? "border-brand/40 bg-card" : "border-border/70 bg-card/50",
        status === "locked" ? "opacity-60" : "hover:border-brand/40 cursor-pointer",
      )}
    >
      <span className="shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-[11px]">
          <span className="font-medium">Module {m.sequence}</span>
          <span className="inline-flex items-center gap-1">
            <CalendarClock className="size-3" /> by {fmtDate(m.complete_before)}
          </span>
          <span>~{fmtMinutes(m.estimated_minutes)}</span>
          {status === "active" && <span className="text-brand font-medium">Up next</span>}
        </div>
        <h3 className="font-display text-foreground mt-0.5 text-base tracking-tight">{m.title}</h3>
        {status === "locked" && (
          <p className="text-muted-foreground mt-0.5 text-xs">
            Complete the previous module to unlock.
          </p>
        )}
      </div>
      {status !== "locked" && <ChevronRight className="text-muted-foreground size-4 shrink-0" />}
    </div>
  );

  if (status === "locked") return body;
  return <Link href={`/chat/${courseId}/modules/${m.module_id}`}>{body}</Link>;
}

export function ModulesView({ courseId }: { courseId: string }) {
  const [modules, setModules] = useState<CourseModuleProgress[] | null>(null);

  useEffect(() => {
    listModules(courseId)
      .then(setModules)
      .catch(() => setModules([]));
  }, [courseId]);

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
          {done} of {modules.length} complete
        </p>
        <div className="bg-muted mt-2 h-1.5 overflow-hidden rounded-full">
          <div
            className="bg-brand h-full rounded-full transition-all"
            style={{ width: `${(done / modules.length) * 100}%` }}
          />
        </div>
      </header>

      <ol className="space-y-2">
        {modules.map((m) => (
          <li key={m.module_id}>
            <ModuleRow courseId={courseId} m={m} />
          </li>
        ))}
      </ol>
    </div>
  );
}
