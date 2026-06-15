"use client";

/**
 * Account chooser, framed as sign-in. Picking a learner persona is the session.
 * Personas are pulled live from the backend (learners only — managers excluded
 * there), shown with deterministic DiceBear avatars.
 */

import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ManagerEntry } from "@/components/manager/manager-entry";
import { usePersona } from "@/components/persona-provider";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { avatarDataUri } from "@/lib/avatar";
import { fetchLearners, type PersonaSummary } from "@/lib/api";

const EASE_OUT = [0.16, 1, 0.3, 1] as const;

function PersonaCard({
  persona,
  index,
  onSelect,
}: {
  persona: PersonaSummary;
  index: number;
  onSelect: (persona: PersonaSummary) => void;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.button
      type="button"
      onClick={() => onSelect(persona)}
      aria-label={`Sign in as ${persona.codename}, ${persona.role_title}`}
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, delay: index * 0.04, ease: EASE_OUT }}
      whileHover={reduce ? undefined : { y: -3 }}
      whileTap={reduce ? undefined : { scale: 0.985 }}
      className="group focus-visible:border-brand focus-visible:ring-brand/30 flex items-center gap-4 rounded-2xl border border-border bg-card p-4 text-left outline-none transition-colors hover:bg-accent focus-visible:ring-[3px]"
    >
      {/* Inline DiceBear data-URI SVG — next/image optimization does not apply. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={avatarDataUri(persona.codename)}
        alt=""
        width={56}
        height={56}
        className="size-14 shrink-0 rounded-lg ring-1 ring-border"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-display truncate text-lg leading-tight text-foreground">
            {persona.codename}
          </span>
          <span className="text-muted-foreground font-mono text-[0.7rem]">
            {persona.employee_id}
          </span>
        </div>
        <p className="text-muted-foreground mt-0.5 truncate text-sm">
          {persona.role_title}
        </p>
        <Badge variant="secondary" className="mt-2 font-mono text-[0.65rem]">
          {persona.certification}
        </Badge>
      </div>
    </motion.button>
  );
}

export function PersonaChooser() {
  const router = useRouter();
  const { selectPersona } = usePersona();
  const [learners, setLearners] = useState<PersonaSummary[] | null>(null);
  const [status, setStatus] = useState<"loading" | "waking" | "error">("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // The backend may be a spun-down free instance. After a short wait with no
    // response, tell the user it's waking instead of showing a bare skeleton.
    const wakeTimer = setTimeout(() => {
      setStatus((current) => (current === "loading" ? "waking" : current));
    }, 3500);

    fetchLearners(controller.signal)
      .then((data) => setLearners(data))
      .catch(() => {
        if (!controller.signal.aborted) {
          setStatus("error");
        }
      })
      .finally(() => clearTimeout(wakeTimer));

    return () => {
      controller.abort();
      clearTimeout(wakeTimer);
    };
  }, [attempt]);

  function handleSelect(persona: PersonaSummary) {
    selectPersona(persona);
    router.push("/chat");
  }

  // Re-run the fetch effect from a clean slate (used by the "Try again" button).
  function handleRetry() {
    setLearners(null);
    setStatus("loading");
    setAttempt((n) => n + 1);
  }

  return (
    <MotionConfig reducedMotion="user">
      <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col justify-center px-6 py-16">
        <header className="mb-10">
          <p className="text-brand font-mono text-xs font-medium uppercase tracking-[0.2em]">
            Athenaeum
          </p>
          <h1 className="font-display mt-3 text-4xl tracking-tight text-foreground sm:text-5xl">
            Sign in to your account
          </h1>
          <p className="text-muted-foreground mt-3 max-w-md text-pretty">
            Choose a learner to continue. Your account holds your courses and the
            conversations behind them.
          </p>
        </header>

        {status === "error" ? (
          <div role="alert" className="flex flex-col items-start gap-3">
            <p className="text-destructive text-sm">
              Couldn’t reach the server. A free instance may be waking up — give it a
              moment and try again.
            </p>
            <button
              type="button"
              onClick={handleRetry}
              className="focus-visible:ring-brand/30 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground outline-none transition-colors hover:bg-accent focus-visible:ring-[3px]"
            >
              Try again
            </button>
          </div>
        ) : (
          <>
            {status === "waking" && !learners ? (
              <p className="text-muted-foreground mb-4 text-sm">
                Waking the server… the free tier spins down when idle, so this first
                load can take up to a minute.
              </p>
            ) : null}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {learners
                ? learners.map((persona, index) => (
                    <PersonaCard
                      key={persona.employee_id}
                      persona={persona}
                      index={index}
                      onSelect={handleSelect}
                    />
                  ))
                : Array.from({ length: 6 }).map((_, index) => (
                    <Skeleton key={index} className="h-22 rounded-2xl" />
                  ))}
            </div>
          </>
        )}

        {/* Additive: managers (e.g. Polaris) open the aggregate team view instead. */}
        <ManagerEntry />
      </main>
    </MotionConfig>
  );
}
