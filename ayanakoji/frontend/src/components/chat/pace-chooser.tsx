"use client";

/**
 * The pace HITL gate — shown before a study plan is built. The learner picks a
 * pace, which sets it on the course and triggers the (now-unblocked) plan.
 */

import { motion, useReducedMotion } from "framer-motion";
import { Gauge, Rabbit, Turtle } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Pace, PaceRequest } from "@/lib/api";

const PACE_META: Record<Pace, { label: string; hint: string; icon: React.ReactNode }> = {
  slower: { label: "Slower", hint: "Spread it out", icon: <Turtle className="size-4" /> },
  normal: { label: "Normal", hint: "Balanced", icon: <Gauge className="size-4" /> },
  faster: { label: "Faster", hint: "Intensive", icon: <Rabbit className="size-4" /> },
};

export function PaceChooser({
  request,
  chosen,
  busy,
  onChoose,
}: {
  request: PaceRequest;
  chosen: Pace | null;
  busy: boolean;
  onChoose: (pace: Pace) => void;
}) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[78%] space-y-2 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      <p className="text-foreground/90 px-1 text-xs font-medium text-pretty">{request.prompt}</p>
      <div className="grid grid-cols-3 gap-2">
        {request.options.map((pace) => {
          const meta = PACE_META[pace];
          const isChosen = chosen === pace;
          return (
            <Button
              key={pace}
              variant={isChosen ? "default" : "outline"}
              onClick={() => onChoose(pace)}
              disabled={busy}
              className="h-auto flex-col gap-1 py-2.5 text-xs"
            >
              <span className={isChosen ? "" : "text-brand"}>{meta.icon}</span>
              <span className="font-medium">{meta.label}</span>
              <span className="text-[10px] opacity-70">{meta.hint}</span>
            </Button>
          );
        })}
      </div>
    </motion.div>
  );
}
