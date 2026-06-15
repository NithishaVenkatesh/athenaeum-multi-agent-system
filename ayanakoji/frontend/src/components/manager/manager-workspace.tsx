"use client";

/**
 * Manager section shell: loads aggregate team insights, then renders the
 * dashboard + the "ask about your team" chat. Reuses the global theme and
 * colosseum backdrop (from the root layout), so it matches the rest of the app.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { InsightsDashboard } from "@/components/manager/insights-dashboard";
import { ManagerChat } from "@/components/manager/manager-chat";
import { usePersona } from "@/components/persona-provider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchTeamInsights, type TeamInsights } from "@/lib/manager-api";

export function ManagerWorkspace({ employeeId }: { employeeId: string }) {
  const router = useRouter();
  const { signOut } = usePersona();
  const [insights, setInsights] = useState<TeamInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchTeamInsights(employeeId, controller.signal)
      .then(setInsights)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "Could not load team insights");
        }
      });
    return () => controller.abort();
  }, [employeeId]);

  function handleSignOut() {
    signOut();
    router.push("/login");
  }

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-8 flex items-center justify-between">
        <Link
          href="/login"
          className="text-brand font-mono text-xs font-medium uppercase tracking-[0.2em]"
        >
          Athenaeum · Manager
        </Link>
        <Button variant="ghost" size="sm" onClick={handleSignOut}>
          Sign out
        </Button>
      </div>

      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}. Is the backend running?
        </p>
      ) : !insights ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-72 rounded-xl" />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Skeleton className="h-36 rounded-2xl" />
            <Skeleton className="h-36 rounded-2xl" />
            <Skeleton className="h-36 rounded-2xl" />
          </div>
          <Skeleton className="h-32 rounded-2xl" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Full-width team header so both columns below align to the same top line. */}
          <header>
            <h1 className="font-display text-3xl tracking-tight text-foreground">
              {insights.team_name} · team readiness
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              {insights.manager_codename} · {insights.member_count} engineers
              {insights.sprint_name ? ` · ${insights.sprint_name}` : ""}
              {insights.sprint_goal ? ` — “${insights.sprint_goal}”` : ""}
            </p>
          </header>

          {/* Columns align at the top; the chat is a FIXED-height side section with its own
              internal scroll, so a long conversation never grows the page or stretches the
              dashboard. Sticky on wide screens so it stays in view while the dashboard scrolls. */}
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
            <div className="min-w-0 flex-1">
              <InsightsDashboard insights={insights} />
            </div>
            <aside className="h-[75dvh] w-full shrink-0 lg:sticky lg:top-6 lg:h-[calc(100dvh-7rem)] lg:w-[400px]">
              <ManagerChat employeeId={employeeId} />
            </aside>
          </div>
        </div>
      )}
    </main>
  );
}
