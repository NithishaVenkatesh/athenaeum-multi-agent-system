"use client";

/**
 * "Team lead" entry on the account front page. Mirrors the learner PersonaCard
 * look (same avatar, radius, motion) with a Manager badge, set apart under a
 * quiet divider. Selecting it stores the manager persona (same no-auth mechanism
 * learners use) and opens the manager section at /manager.
 */

import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { usePersona } from "@/components/persona-provider";
import { Badge } from "@/components/ui/badge";
import { avatarDataUri } from "@/lib/avatar";
import { type PersonaSummary } from "@/lib/api";
import { fetchManagers } from "@/lib/manager-api";

const EASE_OUT = [0.16, 1, 0.3, 1] as const;

function ManagerCard({
  persona,
  onSelect,
}: {
  persona: PersonaSummary;
  onSelect: (persona: PersonaSummary) => void;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.button
      type="button"
      onClick={() => onSelect(persona)}
      aria-label={`Open the manager view as ${persona.codename}, ${persona.role_title}`}
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, ease: EASE_OUT }}
      whileHover={reduce ? undefined : { y: -3 }}
      whileTap={reduce ? undefined : { scale: 0.985 }}
      className="group focus-visible:border-brand focus-visible:ring-brand/30 flex w-full items-center gap-4 rounded-2xl border border-border bg-card p-4 text-left outline-none transition-colors hover:bg-accent focus-visible:ring-[3px]"
    >
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
        <p className="text-muted-foreground mt-0.5 truncate text-sm">{persona.role_title}</p>
        <div className="mt-2 flex items-center gap-2">
          <Badge className="bg-brand/15 text-brand border-brand/20 text-[0.65rem]">Manager</Badge>
          <Badge variant="secondary" className="font-mono text-[0.65rem]">
            Team view
          </Badge>
        </div>
      </div>
    </motion.button>
  );
}

export function ManagerEntry() {
  const router = useRouter();
  const { selectPersona } = usePersona();
  const [managers, setManagers] = useState<PersonaSummary[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchManagers(controller.signal)
      .then(setManagers)
      .catch(() => {
        /* The manager entry is optional chrome; stay silent if it can't load. */
      });
    return () => controller.abort();
  }, []);

  if (!managers || managers.length === 0) return null;

  function handleSelect(persona: PersonaSummary) {
    selectPersona(persona);
    router.push("/manager");
  }

  return (
    <section className="mt-10">
      <div className="mb-3 flex items-center gap-3">
        <span className="text-muted-foreground text-xs font-medium uppercase tracking-[0.2em]">
          Team lead
        </span>
        <span className="bg-border h-px flex-1" />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {managers.map((persona) => (
          <ManagerCard key={persona.employee_id} persona={persona} onSelect={handleSelect} />
        ))}
      </div>
    </section>
  );
}
