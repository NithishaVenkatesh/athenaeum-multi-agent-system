"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { pingBackend, type PingResponse } from "@/lib/api";

type Status = "loading" | "online" | "offline";

const DOT_COLOR: Record<Status, string> = {
  loading: "bg-amber-400",
  online: "bg-emerald-500",
  offline: "bg-red-500",
};

const LABEL: Record<Status, string> = {
  loading: "Checking backend…",
  online: "Backend connected",
  offline: "Backend unreachable",
};

/**
 * Live connectivity indicator. Pings the FastAPI backend and animates the
 * result — the visible proof that frontend and backend are wired together.
 */
export function BackendStatus() {
  const [status, setStatus] = useState<Status>("loading");
  const [detail, setDetail] = useState<PingResponse | null>(null);

  // State updates live in deferred .then/.catch callbacks, never synchronously
  // in the effect body — keeps the React Compiler's set-state-in-effect rule happy.
  const runCheck = useCallback((signal?: AbortSignal) => {
    pingBackend(signal)
      .then((result) => {
        setDetail(result);
        setStatus("online");
      })
      .catch(() => {
        if (signal?.aborted) return;
        setDetail(null);
        setStatus("offline");
      });
  }, []);

  const handleRecheck = useCallback(() => {
    setStatus("loading");
    setDetail(null);
    runCheck();
  }, [runCheck]);

  useEffect(() => {
    const controller = new AbortController();
    runCheck(controller.signal);
    return () => controller.abort();
  }, [runCheck]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="flex flex-col items-center gap-4 rounded-xl border border-neutral-200 bg-white/60 p-6 shadow-sm dark:border-neutral-800 dark:bg-neutral-900/60"
    >
      <div className="flex items-center gap-3" role="status" aria-live="polite">
        <motion.span
          className={`size-3 rounded-full ${DOT_COLOR[status]}`}
          animate={
            status === "loading"
              ? { scale: [1, 1.3, 1], opacity: [1, 0.5, 1] }
              : { scale: 1, opacity: 1 }
          }
          transition={
            status === "loading"
              ? { repeat: Infinity, duration: 1 }
              : { duration: 0.2 }
          }
        />
        <span className="text-sm font-medium">{LABEL[status]}</span>
      </div>

      <AnimatePresence mode="wait">
        {detail && (
          <motion.dl
            key={detail.timestamp}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-neutral-500 dark:text-neutral-400"
          >
            <dt>service</dt>
            <dd className="font-mono">{detail.service}</dd>
            <dt>version</dt>
            <dd className="font-mono">{detail.version}</dd>
            <dt>message</dt>
            <dd className="font-mono">{detail.message}</dd>
          </motion.dl>
        )}
      </AnimatePresence>

      <Button variant="outline" size="sm" onClick={handleRecheck}>
        Re-check
      </Button>
    </motion.div>
  );
}
