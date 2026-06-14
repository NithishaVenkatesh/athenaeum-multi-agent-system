"use client";

/**
 * The skill-gap gate — shown after a course is accepted, before pacing. The
 * learner says they're new (fresher) or opts into a quick per-module skill check.
 */

import { motion, useReducedMotion } from "framer-motion";
import { GraduationCap, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SkillGateRequest } from "@/lib/api";

export function SkillGateCard({
  request,
  busy,
  onFresher,
  onTakeCheck,
}: {
  request: SkillGateRequest;
  busy: boolean;
  onFresher: () => void;
  onTakeCheck: () => void;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[78%] space-y-2 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      <p className="text-foreground/90 px-1 text-xs font-medium text-pretty">
        {request.prompt}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <Button
          variant="outline"
          onClick={onFresher}
          disabled={busy}
          className="h-auto flex-col gap-1 py-2.5 text-xs"
        >
          <span className="text-brand">
            <GraduationCap className="size-4" />
          </span>
          <span className="font-medium">I&apos;m new to this</span>
          <span className="text-[10px] opacity-70">Skip the check</span>
        </Button>
        <Button
          onClick={onTakeCheck}
          disabled={busy}
          className="h-auto flex-col gap-1 py-2.5 text-xs"
        >
          <span>
            <Sparkles className="size-4" />
          </span>
          <span className="font-medium">Quick skill check</span>
          <span className="text-[10px] opacity-70">4 questions / module</span>
        </Button>
      </div>
    </motion.div>
  );
}
