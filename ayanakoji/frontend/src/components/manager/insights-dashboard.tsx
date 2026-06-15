"use client";

/**
 * The manager insights dashboard — a "team readiness dossier" in the app's
 * scholarly-atelier aesthetic. Source 1 (Work IQ aggregates) fills the headline
 * cards; Source 2 (real platform activity) fills the engagement card with an
 * honest empty state. Everything shown is aggregate, team-level only.
 */

import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, GraduationCap, Target } from "lucide-react";

import { cn } from "@/lib/utils";
import type { RiskSeverity, TeamInsights } from "@/lib/manager-api";

const EASE_OUT = [0.16, 1, 0.3, 1] as const;

// The two data origins are visually distinct so "GO readiness" (static org
// records) is never confused with "active" (real platform activity).
type CardSource = "org" | "platform";

const SOURCE_LABEL: Record<CardSource, string> = {
  org: "Team plan",
  platform: "Live activity",
};

function Card({
  title,
  icon,
  source,
  className,
  children,
}: {
  title?: string;
  icon?: React.ReactNode;
  source?: CardSource;
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
          {source && (
            <span className="text-muted-foreground/70 ml-auto text-[0.6rem] font-medium normal-case tracking-normal">
              {SOURCE_LABEL[source]}
            </span>
          )}
        </div>
      )}
      {children}
    </div>
  );
}

function ReadinessCard({
  insights,
  className,
}: {
  insights: TeamInsights;
  className?: string;
}) {
  const { go, conditional, not_yet, total } = insights.readiness;
  const safeTotal = Math.max(total, 1);
  const segs = [
    { n: go, cls: "bg-chart-2", label: "GO" },
    { n: conditional, cls: "bg-chart-4", label: "Conditional" },
    { n: not_yet, cls: "bg-destructive", label: "Not yet" },
  ];
  return (
    <Card
      title="Exam readiness"
      icon={<GraduationCap className="size-3.5" />}
      source="platform"
      className={className}
    >
      <div className="flex items-baseline gap-2">
        <span className="font-display text-4xl text-foreground">{go}</span>
        <span className="text-muted-foreground text-sm">of {total} ready (GO)</span>
      </div>
      <p className="text-muted-foreground/80 mt-1 text-xs">
        GO = finished a course in their certification path · Conditional = in progress · Not yet =
        no activity
      </p>
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
      {insights.by_seniority.length > 1 && (
        <div className="border-border/60 mt-3 space-y-2 border-t pt-3">
          <div className="text-muted-foreground text-[10px] font-medium uppercase tracking-wider">
            By seniority
          </div>
          {insights.by_seniority.map((c) => {
            const t = Math.max(c.total, 1);
            const bands = [
              { n: c.go, cls: "bg-chart-2" },
              { n: c.conditional, cls: "bg-chart-4" },
              { n: c.not_yet, cls: "bg-destructive" },
            ];
            return (
              <div key={c.label} className="flex items-center gap-2 text-xs">
                <span className="text-foreground w-16 shrink-0">{c.label}</span>
                <div className="flex h-1.5 flex-1 overflow-hidden rounded-full">
                  {bands.map((b, i) => (
                    <div
                      key={i}
                      className={cn(b.cls, b.n === 0 && "hidden")}
                      style={{ width: `${(b.n / t) * 100}%` }}
                    />
                  ))}
                </div>
                <span className="text-muted-foreground w-12 shrink-0 text-right">
                  {c.go}/{c.total} GO
                </span>
              </div>
            );
          })}
        </div>
      )}
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

function CertTargetsCard({
  insights,
  className,
}: {
  insights: TeamInsights;
  className?: string;
}) {
  if (insights.cert_targets.length === 0) {
    return (
      <Card
        title="Certification targets"
        icon={<Target className="size-3.5" />}
        source="platform"
        className={className}
      >
        <p className="text-muted-foreground text-sm">No certification targets set for this team.</p>
      </Card>
    );
  }
  return (
    <Card
      title="Certification targets"
      icon={<Target className="size-3.5" />}
      source="platform"
      className={className}
    >
      <ul className="space-y-3">
        {insights.cert_targets.map((t) => {
          const pct = t.member_count > 0 ? (t.ready_count / t.member_count) * 100 : 0;
          return (
            <li key={`${t.vertical}-${t.cert}`}>
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-mono text-foreground">{t.cert}</span>
                <span className="text-muted-foreground text-xs">
                  {t.ready_count}/{t.member_count} GO · {t.target_quarter}
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
    <Card
      title="Needs attention"
      icon={<AlertTriangle className="size-3.5" />}
    >
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
    <Card
      title="Platform engagement"
      icon={<GraduationCap className="size-3.5" />}
      source="platform"
    >
      {e.has_activity ? (
        <div className="grid grid-cols-3 gap-4">
          <Stat value={`${e.members_active}/${e.members_total}`} label="active" />
          <Stat
            value={e.pass_rate != null ? `${Math.round(e.pass_rate * 100)}%` : "—"}
            label="pass rate"
          />
          <Stat value={`${e.modules_completed}`} label="modules done" />
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">
          No team members have taken an assessment in the platform yet.
        </p>
      )}
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
      // Cards-only bento (the chat lives separately, below). On wide screens it is a 3x2
      // board: Readiness is a tall tile (spans both rows), Cert targets is a wide tile
      // (spans two columns), and Engagement + Needs-attention fill the remaining two
      // cells. Rows size to their content (no fixed board height), so tiles stay just
      // tall enough for what's in them instead of showing large empty space. Below lg it
      // stacks 1- then 2-up.
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
    >
      <ReadinessCard insights={insights} className="lg:row-span-2" />
      <CertTargetsCard insights={insights} className="lg:col-span-2" />
      <EngagementCard insights={insights} />
      <RiskCard insights={insights} />
    </motion.div>
  );
}
