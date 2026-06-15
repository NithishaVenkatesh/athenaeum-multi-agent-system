"use client";

/**
 * The manager insights dashboard — a "team readiness dossier" in the app's
 * scholarly-atelier aesthetic. Source 1 (Work IQ aggregates) fills the headline
 * cards; Source 2 (real platform activity) fills the engagement card with an
 * honest empty state. Everything shown is aggregate, team-level only.
 */

import { motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  CalendarClock,
  GraduationCap,
  Target,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RiskSeverity, TeamInsights } from "@/lib/manager-api";

const EASE_OUT = [0.16, 1, 0.3, 1] as const;

function Card({
  title,
  icon,
  className,
  children,
}: {
  title?: string;
  icon?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "border-border bg-card/80 rounded-2xl border p-5 backdrop-blur-sm",
        className,
      )}
    >
      {title && (
        <div className="text-muted-foreground mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.15em]">
          {icon}
          {title}
        </div>
      )}
      {children}
    </div>
  );
}

function ReadinessCard({ insights }: { insights: TeamInsights }) {
  const { go, conditional, not_yet, total } = insights.readiness;
  const safeTotal = Math.max(total, 1);
  const segs = [
    { n: go, cls: "bg-chart-2", label: "GO" },
    { n: conditional, cls: "bg-chart-4", label: "Conditional" },
    { n: not_yet, cls: "bg-destructive", label: "Not yet" },
  ];
  return (
    <Card title="Exam readiness" icon={<GraduationCap className="size-3.5" />}>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-4xl text-foreground">{go}</span>
        <span className="text-muted-foreground text-sm">of {total} ready (GO)</span>
      </div>
      <div className="mt-3 flex h-2.5 overflow-hidden rounded-full">
        {segs.map((s) => (
          <div
            key={s.label}
            className={cn(s.cls, s.n === 0 && "hidden")}
            style={{ width: `${(s.n / safeTotal) * 100}%` }}
          />
        ))}
      </div>
      <div className="text-muted-foreground mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {segs.map((s) => (
          <span key={s.label} className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", s.cls)} />
            {s.n} {s.label}
          </span>
        ))}
      </div>
    </Card>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="font-display text-2xl text-foreground">{value}</div>
      <div className="text-muted-foreground text-xs">{label}</div>
    </div>
  );
}

function CapacityCard({ insights }: { insights: TeamInsights }) {
  const c = insights.capacity;
  return (
    <Card title="Capacity" icon={<CalendarClock className="size-3.5" />}>
      <div className="flex items-end justify-between gap-4">
        <Stat value={`${c.avg_focus_hours_per_week}h`} label="avg focus / week" />
        <Stat value={`${c.avg_meeting_hours_per_week}h`} label="avg meetings / week" />
      </div>
      {c.high_meeting_load_count > 0 ? (
        <p className="text-foreground/80 mt-3 flex items-center gap-1.5 text-xs">
          <TriangleAlert className="text-chart-4 size-3.5" />
          {c.high_meeting_load_count} of {c.member_count} over{" "}
          {Math.floor(c.heavy_meeting_threshold_hours)}h meetings/week
        </p>
      ) : (
        <p className="text-muted-foreground mt-3 text-xs">Meeting load within healthy range.</p>
      )}
      {c.constrained && (
        <Badge className="bg-chart-4/15 text-chart-4 border-chart-4/20 mt-3 text-[0.65rem]">
          Capacity-constrained
        </Badge>
      )}
    </Card>
  );
}

function CertTargetsCard({ insights }: { insights: TeamInsights }) {
  if (insights.cert_targets.length === 0) return null;
  return (
    <Card title="Certification targets" icon={<Target className="size-3.5" />}>
      <ul className="space-y-3">
        {insights.cert_targets.map((t) => {
          const pct = t.member_count > 0 ? (t.ready_count / t.member_count) * 100 : 0;
          return (
            <li key={`${t.vertical}-${t.cert}`}>
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-mono text-foreground">{t.cert}</span>
                <span className="text-muted-foreground text-xs">
                  {t.ready_count}/{t.member_count} ready · {t.target_quarter}
                </span>
              </div>
              <div className="bg-muted mt-1.5 h-1.5 overflow-hidden rounded-full">
                <div className="bg-chart-3 h-full rounded-full" style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

const SEVERITY_STYLE: Record<RiskSeverity, string> = {
  high: "text-destructive",
  medium: "text-chart-4",
  low: "text-muted-foreground",
};

function RiskCard({ insights }: { insights: TeamInsights }) {
  return (
    <Card title="Needs attention" icon={<AlertTriangle className="size-3.5" />}>
      {insights.risks.length === 0 ? (
        <p className="text-muted-foreground text-sm">No risks flagged. The team is on track.</p>
      ) : (
        <ul className="space-y-3">
          {insights.risks.map((r, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  r.severity === "high"
                    ? "bg-destructive"
                    : r.severity === "medium"
                      ? "bg-chart-4"
                      : "bg-muted-foreground",
                )}
              />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-foreground text-sm font-medium">{r.title}</span>
                  <span
                    className={cn(
                      "text-[0.65rem] font-medium uppercase tracking-wide",
                      SEVERITY_STYLE[r.severity],
                    )}
                  >
                    {r.severity}
                  </span>
                </div>
                <p className="text-muted-foreground text-xs leading-snug">{r.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function EngagementCard({ insights }: { insights: TeamInsights }) {
  const e = insights.engagement;
  return (
    <Card title="Platform engagement" icon={<GraduationCap className="size-3.5" />}>
      {e.has_activity ? (
        <div className="grid grid-cols-3 gap-4">
          <Stat value={`${e.members_active}/${e.members_total}`} label="active" />
          <Stat
            value={e.pass_rate != null ? `${Math.round(e.pass_rate * 100)}%` : "—"}
            label="pass rate"
          />
          <Stat value={`${e.assessments_passed}/${e.assessments_attempted}`} label="passed" />
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">
          No team members have taken an assessment in the platform yet.
        </p>
      )}
    </Card>
  );
}

function OkrCard({ insights }: { insights: TeamInsights }) {
  if (insights.okrs.length === 0) return null;
  return (
    <Card title="Team OKRs" icon={<Target className="size-3.5" />}>
      <ul className="space-y-3">
        {insights.okrs.map((o) => (
          <li key={o.id}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-foreground truncate">{o.objective}</span>
              <span className="text-muted-foreground text-xs">{Math.round(o.progress * 100)}%</span>
            </div>
            <div className="bg-muted mt-1.5 h-1.5 overflow-hidden rounded-full">
              <div
                className="bg-chart-5 h-full rounded-full"
                style={{ width: `${o.progress * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function InsightsDashboard({ insights }: { insights: TeamInsights }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE_OUT }}
      className="space-y-4"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ReadinessCard insights={insights} />
        <CapacityCard insights={insights} />
        <CertTargetsCard insights={insights} />
      </div>

      <RiskCard insights={insights} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <EngagementCard insights={insights} />
        <OkrCard insights={insights} />
      </div>
    </motion.div>
  );
}
