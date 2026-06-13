"use client";

/**
 * The study-plan card — a workload-aware schedule for the chosen course.
 *
 * Everything shown is computed deterministically by the backend from the
 * learner's Work IQ signals (meeting load, focus windows, preferred days):
 * per-module time is over-estimated 2×, weekly capacity is reduced when meetings
 * are heavy, and sessions land in the learner's focus window.
 */

import { motion, useReducedMotion } from "framer-motion";
import { CalendarClock, Clock, GraduationCap, Layers, TimerReset } from "lucide-react";

import type { StudyPlan } from "@/lib/api";

function fmtMinutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
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

export function StudyPlanCard({ plan }: { plan: StudyPlan }) {
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
          <div className="flex items-center gap-2">
            <span className="bg-brand/10 text-brand inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold">
              <GraduationCap className="size-3" />
              {plan.cert}
            </span>
            <span className="text-muted-foreground text-[11px]">{plan.weeks}-week study plan</span>
          </div>
          <h3 className="font-display text-foreground mt-1 text-base leading-tight tracking-tight">
            {plan.title}
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat
          icon={<Clock className="size-3.5" />}
          label="per week"
          value={`${plan.weekly_study_hours}h`}
        />
        <Stat
          icon={<Layers className="size-3.5" />}
          label="total"
          value={`${plan.total_hours}h`}
        />
        <Stat
          icon={<CalendarClock className="size-3.5" />}
          label="weeks"
          value={`${plan.weeks}`}
        />
        <Stat
          icon={<TimerReset className="size-3.5" />}
          label="time buffer"
          value={`${plan.overestimate_factor}×`}
        />
      </div>

      <p className="text-muted-foreground border-border/50 border-l-2 pl-2.5 text-[11px] leading-relaxed text-pretty">
        {plan.capacity_reason}
      </p>

      {/* Weekly session schedule */}
      <div>
        <h4 className="text-muted-foreground mb-1.5 text-[10px] font-semibold tracking-wide uppercase">
          Weekly sessions
        </h4>
        <div className="flex flex-wrap gap-1.5">
          {plan.sessions.map((s, i) => (
            <span
              key={`${s.day}-${i}`}
              className="border-border/60 bg-background/60 text-foreground/90 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px]"
            >
              <span className="font-medium capitalize">{s.day}</span>
              <span className="text-muted-foreground">
                {s.start}–{s.end}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Week-by-week module schedule */}
      <ol className="space-y-1.5">
        {plan.schedule.map((week) => (
          <li
            key={week.week}
            className="border-border/60 bg-card/40 rounded-lg border px-3 py-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-foreground text-xs font-semibold">Week {week.week}</span>
              <span className="text-muted-foreground text-[10px]">
                {fmtMinutes(week.total_minutes)}
              </span>
            </div>
            <ul className="mt-1 space-y-0.5">
              {week.module_titles.map((title, i) => (
                <li key={title} className="text-foreground/80 flex items-baseline gap-1.5 text-[11px]">
                  <span className="text-brand">•</span>
                  <span className="flex-1">{title}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {fmtMinutes(
                      plan.modules.find((m) => m.module_id === week.module_ids[i])
                        ?.estimated_minutes ?? 0,
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </motion.div>
  );
}
