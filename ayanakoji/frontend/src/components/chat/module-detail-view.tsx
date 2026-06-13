"use client";

/**
 * A single module's page: its full content (markdown from approved material) and
 * a "mark complete" action when it's the active module. Completed modules stay
 * accessible (you can revisit the content); locked modules send you back.
 */

import {
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Loader2,
  Lock,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
  const router = useRouter();
  const [modules, setModules] = useState<CourseModuleProgress[] | null>(null);
  const [content, setContent] = useState<ModuleContent | null>(null);
  const [completing, setCompleting] = useState(false);

  const reload = useCallback(() => {
    listModules(courseId)
      .then(setModules)
      .catch(() => setModules([]));
  }, [courseId]);

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

  async function handleComplete() {
    setCompleting(true);
    try {
      await completeModule(courseId, moduleId);
      toast.success("Module complete", { description: "The next module is unlocked." });
      if (next) router.push(`/chat/${courseId}/modules/${next.module_id}`);
      else router.push(modulesHref);
    } catch {
      toast.error("Could not complete", { description: "Finish the earlier modules first." });
      setCompleting(false);
    }
  }

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

      <div className="border-border mt-8 flex items-center justify-between border-t pt-4">
        {current.completed ? (
          <span className="text-muted-foreground text-sm">You have completed this module.</span>
        ) : (
          <Button onClick={handleComplete} disabled={completing} size="sm">
            {completing ? "Marking…" : "Mark module complete"}
          </Button>
        )}
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
  );
}
