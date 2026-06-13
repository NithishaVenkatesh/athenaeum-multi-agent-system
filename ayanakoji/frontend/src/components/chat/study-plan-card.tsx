"use client";

/**
 * The study-plan card — a calendar-grounded, module-level completion plan.
 *
 * Every figure is computed by the backend from the learner's *real* weekly
 * calendar: study time comes from slots already in their week, modules are done
 * in order, and each carries a complete-by date. The card links into the Modules
 * tab where the content is read and progress is tracked.
 */

import { motion, useReducedMotion } from "framer-motion";
import {
  CalendarClock,
  CalendarDays,
  CircleCheck,
  Clock,
  GaugeCircle,
  GraduationCap,
} from "lucide-react";
import Link from "next/link";

import type { Pace, StudyPlan } from "@/lib/api";

const PACE_LABEL: Record<Pace, string> = {
  slower: "Relaxed pace",
  normal: "Balanced pace",
  faster: "Intensive pace",
};

function fmtMinutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="border-border/60 bg-card/50 flex items-center gap-2 rounded-lg border px-2.5 py-1.5">
      <span className="text-brand">{icon}</span>
      <div className="leading-tight">
        <div className="text-foreground text-xs font-semibold">{value}</div>
        <div className="text-muted-foreground text-[10px]">{label}</div>
      </div>
    </div>
  );
}

export function StudyPlanCard({ plan, courseId }: { plan: StudyPlan; courseId?: string }) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 from-card to-brand/5 max-w-[85%] space-y-3 rounded-2xl rounded-bl-md border bg-gradient-to-br p-4 shadow-sm"
    >
      <div className="flex items-start gap-2">
        <span className="bg-brand/10 text-brand mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl">
          <CalendarClock className="size-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="bg-brand/10 text-brand inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold">
              <GraduationCap className="size-3" />
              {plan.cert}
            </span>
            <span className="text-muted-foreground inline-flex items-center gap-1 text-[11px]">
              <GaugeCircle className="size-3" />
              {PACE_LABEL[plan.pace]}
            </span>
          </div>
          <h3 className="font-display text-foreground mt-1 text-base leading-tight tracking-tight">
            {plan.title}
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Stat icon={<Clock className="size-3.5" />} label="per week" value={`${plan.weekly_study_hours}h`} />
        <Stat icon={<CalendarDays className="size-3.5" />} label="over" value={`${plan.weeks} wks`} />
        <Stat icon={<CircleCheck className="size-3.5" />} label="modules" value={`${plan.modules.length}`} />
      </div>

      <p className="text-muted-foreground border-brand/40 border-l-2 pl-2.5 text-[11px] leading-relaxed text-pretty">
        {plan.capacity_reason}
      </p>

      {/* Module-level completion plan: sequential, each with a deadline */}
      <ol className="space-y-1.5">
        {plan.modules.map((m) => (
          <li
            key={m.module_id}
            className="border-border/60 bg-card/40 flex items-start gap-2.5 rounded-lg border px-3 py-2"
          >
            <span className="bg-brand/10 text-brand mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold">
              {m.sequence}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-foreground text-xs font-medium">{m.title}</div>
              <div className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 text-[10px]">
                <span>{fmtMinutes(m.estimated_minutes)}</span>
                <span aria-hidden>·</span>
                <span className="inline-flex items-center gap-1">
                  <CalendarClock className="size-3" />
                  by {fmtDate(m.complete_before)}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ol>

      {courseId && (
        <Link
          href={`/chat/${courseId}/modules`}
          className="bg-brand text-brand-foreground hover:bg-brand/90 inline-flex h-8 items-center rounded-lg px-3 text-xs font-medium transition-colors"
        >
          Open the Modules tab →
        </Link>
      )}
    </motion.div>
  );
}
