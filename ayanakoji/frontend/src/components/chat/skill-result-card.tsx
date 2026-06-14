"use client";

/**
 * The skill-check result: per-module score bars + overall, plus an optional
 * deadline picker. "Continue" persists the deadline (or none) and advances to the
 * pace step. Re-rendered from the persisted skill_result meta on reload.
 */

import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { SkillResult } from "@/lib/api";

export function SkillResultCard({
  result,
  done,
  busy,
  onContinue,
}: {
  result: SkillResult;
  done: boolean;
  busy: boolean;
  onContinue: (deadline: string | null) => void;
}) {
  const reduce = useReducedMotion();
  const [deadline, setDeadline] = useState<string>("");

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[82%] space-y-3 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      {!result.fresher && (
        <>
          <div className="flex items-baseline justify-between">
            <span className="text-foreground text-xs font-semibold">Skill check</span>
            <span className="text-brand text-sm font-bold tabular-nums">
              {Math.round(result.overall_fraction * 100)}%
            </span>
          </div>
          <ul className="space-y-1.5">
            {result.modules.map((m) => (
              <li key={m.module_id} className="space-y-0.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-foreground/90 max-w-56 truncate">{m.title}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {m.correct}/{m.total}
                  </span>
                </div>
                <div className="bg-border/50 h-1.5 overflow-hidden rounded-full">
                  <div
                    className="bg-brand h-full rounded-full"
                    style={{ width: `${Math.round(m.fraction * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="space-y-1.5">
        <label className="text-foreground/90 text-[11px] font-medium">
          Target deadline (optional)
        </label>
        <input
          type="date"
          value={deadline}
          disabled={done || busy}
          onChange={(e) => setDeadline(e.target.value)}
          className="border-border/60 bg-background w-full rounded-lg border px-2.5 py-1.5 text-xs"
        />
      </div>

      <Button
        size="sm"
        disabled={done || busy}
        onClick={() => onContinue(deadline || null)}
        className="text-xs"
      >
        {done ? "Continuing…" : "Continue to pace"}
      </Button>
    </motion.div>
  );
}
