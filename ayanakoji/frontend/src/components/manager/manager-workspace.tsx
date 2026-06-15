"use client";

/**
 * Manager section shell: loads aggregate team insights, then renders the
 * dashboard + the "ask about your team" chat. Reuses the global theme and
 * colosseum backdrop (from the root layout), so it matches the rest of the app.
 */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { InsightsDashboard } from "@/components/manager/insights-dashboard";
import { ManagerChat } from "@/components/manager/manager-chat";
import { usePersona } from "@/components/persona-provider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchTeamInsights, type TeamInsights } from "@/lib/manager-api";

// How often the dashboard re-pulls team insights so the live "Platform engagement"
// card reflects new course/assessment activity. Kept deliberately slow, and paused
// when the tab is hidden, so an open dashboard makes at most one request per minute
// (with an immediate refetch when the manager returns to the tab).
const REFRESH_INTERVAL_MS = 60_000;

export function ManagerWorkspace({ employeeId }: { employeeId: string }) {
  const router = useRouter();
  const { signOut } = usePersona();
  const [insights, setInsights] = useState<TeamInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  // One fetch. ``background`` polls keep the last-known dashboard on a transient error
  // (never flip a working view to an error banner); only the first load reports failure.
  const loadInsights = useCallback(
    async (signal: AbortSignal, { background }: { background: boolean }) => {
      try {
        const next = await fetchTeamInsights(employeeId, signal);
        if (!signal.aborted) {
          setInsights(next);
          setError(null);
        }
      } catch (cause: unknown) {
        if (!signal.aborted && !background) {
          setError(cause instanceof Error ? cause.message : "Could not load team insights");
        }
      }
    },
    [employeeId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    // Subscription effect: load from + poll an external system and setState only after
    // the await resolves (no synchronous cascade), so the lint rule is a false positive
    // here — same pattern as the notifications context.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadInsights(controller.signal, { background: false });

    // Poll only while the tab is visible; refetch immediately on regaining focus so
    // switching back after a learner finishes a course shows fresh numbers at once.
    const interval = setInterval(() => {
      if (active && !document.hidden) {
        void loadInsights(controller.signal, { background: true });
      }
    }, REFRESH_INTERVAL_MS);
    const onVisible = () => {
      if (active && !document.hidden) {
        void loadInsights(controller.signal, { background: true });
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      active = false;
      controller.abort();
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [loadInsights]);

  function handleSignOut() {
    signOut();
    router.push("/login");
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-8">
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
        <div className="space-y-6">
          <Skeleton className="h-10 w-72 rounded-xl" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Skeleton className="h-48 rounded-2xl" />
            <Skeleton className="h-48 rounded-2xl" />
            <Skeleton className="h-48 rounded-2xl" />
            <Skeleton className="h-48 rounded-2xl" />
          </div>
          <Skeleton className="mx-auto h-[calc(100dvh-3.5rem)] w-full max-w-3xl rounded-2xl" />
        </div>
      ) : (
        <div className="space-y-6">
          <header>
            <h1 className="font-display text-3xl tracking-tight text-foreground">
              {insights.team_name} · team readiness
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              {insights.manager_codename} · {insights.member_count} engineers · live from real
              course activity
            </p>
          </header>

          {/* Cards as a bento on top, then the chat below at the EXACT learner-chat size:
              centred, ``max-w-3xl`` wide, full viewport-tall column. */}
          <InsightsDashboard insights={insights} />

          <section className="mx-auto h-[calc(100dvh-3.5rem)] w-full max-w-3xl">
            <ManagerChat employeeId={employeeId} />
          </section>
        </div>
      )}
    </main>
  );
}
