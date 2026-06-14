"use client";

/**
 * App-wide page-switch feedback. Route changes triggered via router.push give no
 * visual signal while the next segment's server payload is fetched, so a switch
 * can feel unresponsive. This wraps navigation in a React transition and shows a
 * thin top progress bar for as long as that transition is pending.
 *
 * Components navigate through useNavigate() rather than router.push directly. The
 * hook falls back to a plain push when no provider is mounted, so a component
 * (and its tests) work standalone — they just don't drive the global bar.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useTransition,
} from "react";

const NavigateContext = createContext<((href: string) => void) | null>(null);

/** Navigate to a route, driving the global progress bar when a provider exists. */
export function useNavigate(): (href: string) => void {
  const router = useRouter();
  const navigate = useContext(NavigateContext);
  return useMemo(
    () => navigate ?? ((href: string) => router.push(href)),
    [navigate, router],
  );
}

/** The thin top bar — an indeterminate sweep shown only while navigating. */
export function NavProgressBar({ active }: { active: boolean }) {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence>
      {active && (
        <motion.div
          data-slot="nav-progress"
          aria-hidden
          className="pointer-events-none fixed inset-x-0 top-0 z-[60] h-0.5 overflow-hidden"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.span
            className="bg-brand block h-full w-2/5 rounded-full"
            initial={{ x: "-100%" }}
            animate={reduce ? { x: "150%" } : { x: ["-110%", "260%"] }}
            transition={{ duration: 1.1, ease: "easeInOut", repeat: Infinity }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function NavigationProgress({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const navigate = useCallback(
    (href: string) => {
      // Keeping router.push inside the transition holds `pending` true until the
      // destination segment is ready, so the bar spans the whole switch.
      startTransition(() => {
        router.push(href);
      });
    },
    [router],
  );

  return (
    <NavigateContext.Provider value={navigate}>
      <NavProgressBar active={pending} />
      {children}
    </NavigateContext.Provider>
  );
}
