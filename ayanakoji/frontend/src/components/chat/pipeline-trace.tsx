"use client";

/**
 * The pipeline trace — Athenaeum's "inspectable reasoning" surface.
 *
 * Every turn passes through an injection gate, a router, and an answer agent;
 * each emits PII-safe telemetry (reasoning + the model tier that answered + the
 * grounding sources it cited). This panel renders that as a compact timeline so
 * the learner can see *why* an answer is what it is — grounding shown, not hidden.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  BookOpen,
  Briefcase,
  ChevronDown,
  MessageCircle,
  ShieldAlert,
  ShieldCheck,
  Split,
} from "lucide-react";
import { useState } from "react";

import type { PhaseTelemetry, Route } from "@/lib/api";
import { cn } from "@/lib/utils";

const ROUTE_LABEL: Record<Route, string> = {
  foundry_iq: "Foundry IQ · course content",
  work_iq: "Work IQ · your schedule",
  general: "General",
};

const ROUTE_DOT: Record<Route, string> = {
  foundry_iq: "bg-[var(--chart-3)]",
  work_iq: "bg-[var(--chart-2)]",
  general: "bg-muted-foreground",
};

function PhaseIcon({ phase }: { phase: PhaseTelemetry }) {
  const cls = "size-3.5";
  if (phase.phase === "injection_gate") {
    return phase.status === "blocked" ? (
      <ShieldAlert className={cn(cls, "text-destructive")} />
    ) : (
      <ShieldCheck className={cn(cls, "text-[var(--chart-2)]")} />
    );
  }
  if (phase.phase === "router") return <Split className={cn(cls, "text-brand")} />;
  if (phase.route === "foundry_iq") return <BookOpen className={cn(cls, "text-[var(--chart-3)]")} />;
  if (phase.route === "work_iq") return <Briefcase className={cn(cls, "text-[var(--chart-2)]")} />;
  return <MessageCircle className={cn(cls, "text-muted-foreground")} />;
}

function MetaChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="bg-muted/70 text-muted-foreground rounded-md px-1.5 py-0.5 font-mono text-[10px] leading-none">
      {children}
    </span>
  );
}

function PhaseRow({ phase }: { phase: PhaseTelemetry }) {
  const reduce = useReducedMotion();
  return (
    <motion.li
      initial={reduce ? false : { opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="relative pl-6"
    >
      <span className="bg-card border-border absolute left-0 top-0.5 flex size-5 items-center justify-center rounded-full border">
        <PhaseIcon phase={phase} />
      </span>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-foreground text-xs font-medium">{phase.summary}</span>
        {phase.route && (
          <span className="text-muted-foreground inline-flex items-center gap-1 text-[10px]">
            <span className={cn("size-1.5 rounded-full", ROUTE_DOT[phase.route])} />
            {ROUTE_LABEL[phase.route]}
          </span>
        )}
      </div>
      {phase.reasoning && (
        <p className="text-muted-foreground mt-0.5 text-[11px] leading-snug">{phase.reasoning}</p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {phase.model && (
          <MetaChip>
            {phase.model}
            {phase.tier ? ` · tier ${phase.tier}` : ""}
          </MetaChip>
        )}
        {phase.provider && <MetaChip>{phase.provider}</MetaChip>}
      </div>
      {phase.sources.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {phase.sources.map((s) => (
            <li
              key={s.ref}
              className="border-border/70 bg-background/60 rounded-md border px-2 py-1 text-[11px]"
            >
              <span className="text-brand font-mono text-[10px]">[{s.ref}]</span>{" "}
              <span className="text-foreground font-medium">{s.title}</span>
              <span className="text-muted-foreground"> — {s.snippet}</span>
            </li>
          ))}
        </ul>
      )}
    </motion.li>
  );
}

export function PipelineTrace({
  phases,
  defaultOpen = true,
}: {
  phases: PhaseTelemetry[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (phases.length === 0) return null;

  return (
    <div className="border-border/80 bg-card/60 max-w-[78%] rounded-2xl rounded-bl-md border backdrop-blur-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-muted-foreground hover:text-foreground flex w-full items-center justify-between gap-2 px-3 py-2 text-[11px] font-medium tracking-wide uppercase transition-colors"
      >
        <span>Reasoning &amp; grounding</span>
        <ChevronDown
          className={cn("size-3.5 transition-transform duration-200", open && "rotate-180")}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <ol className="border-border/60 ml-2 space-y-3 border-l py-1 pr-3 pl-3">
              {phases.map((phase, index) => (
                <PhaseRow key={`${phase.phase}-${index}`} phase={phase} />
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
