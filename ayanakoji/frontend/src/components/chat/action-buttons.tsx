"use client";

/**
 * CTA buttons beneath an assistant turn. Navigation actions are real links to the
 * existing module / evaluation routes; "practise again" re-sends a practice message
 * via the supplied callback. If a course has no id yet (brand-new chat), nav actions
 * are disabled rather than linking nowhere.
 */

import { ArrowRight, BookOpen, RotateCcw } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { Action } from "@/lib/api";

const LINK_CLASS =
  "border-input bg-background hover:bg-accent hover:text-accent-foreground inline-flex shrink-0 items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors";

function hrefFor(action: Action, courseId: string | null): string | null {
  if (!courseId || !action.module_id) return null;
  if (action.kind === "take_evaluation") {
    return `/chat/${courseId}/modules/${action.module_id}/assessment/choices`;
  }
  if (action.kind === "go_to_module") {
    return `/chat/${courseId}/modules/${action.module_id}`;
  }
  return null;
}

export function ActionButtons({
  actions,
  courseId,
  onPracticeAgain,
}: {
  actions: Action[];
  courseId: string | null;
  onPracticeAgain: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((action) => {
        if (action.kind === "practice_again") {
          return (
            <Button
              key={action.kind}
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={onPracticeAgain}
            >
              <RotateCcw className="size-3.5" />
              {action.label}
            </Button>
          );
        }
        const href = hrefFor(action, courseId);
        const icon =
          action.kind === "take_evaluation" ? (
            <ArrowRight className="size-3.5" />
          ) : (
            <BookOpen className="size-3.5" />
          );
        if (!href) {
          return (
            <Button key={action.kind} size="sm" variant="outline" disabled className="gap-1.5 text-xs">
              {icon}
              {action.label}
            </Button>
          );
        }
        return (
          <Link key={action.kind} href={href} className={LINK_CLASS}>
            {icon}
            {action.label}
          </Link>
        );
      })}
    </div>
  );
}
