"use client";

/**
 * Chat ↔ Modules ↔ Assessments switcher for the active course. Pinned to the
 * horizontal center of the viewport (independent of the left/right top-bar
 * content) and shown only once a course exists in the route.
 *
 * The active choice is marked by a single persistent pill that slides
 * **horizontally only** between tabs. We deliberately avoid framer-motion's
 * shared `layoutId` here: across a route change its before/after bounding boxes
 * pick up a vertical delta when the outgoing page was scrolled (or differs in
 * height), making the pill fly in from the bottom. Measuring each tab's offset
 * and animating just `x`/`width` keeps the motion locked to one axis.
 */

import { motion, MotionConfig } from "framer-motion";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useNavigate } from "@/components/workspace/navigation-progress";
import { parseChatRoute, type ChatPage } from "@/lib/chat-route";
import { cn } from "@/lib/utils";

const TABS: { key: ChatPage; label: string }[] = [
  { key: "chat", label: "Chat" },
  { key: "modules", label: "Modules" },
  { key: "assessments", label: "Assessments" },
];

function tabHref(courseId: string, page: ChatPage): string {
  return page === "chat" ? `/chat/${courseId}` : `/chat/${courseId}/${page}`;
}

interface Indicator {
  left: number;
  width: number;
}

// useLayoutEffect warns during SSR; fall back to useEffect on the server.
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

export function PageSwitcher() {
  const pathname = usePathname();
  const navigate = useNavigate();
  const { courseId, page } = parseChatRoute(pathname);

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [indicator, setIndicator] = useState<Indicator | null>(null);
  const activeIndex = TABS.findIndex((tab) => tab.key === page);

  const measure = useCallback(() => {
    const el = tabRefs.current[activeIndex];
    if (!el) return;
    setIndicator({ left: el.offsetLeft, width: el.offsetWidth });
  }, [activeIndex]);

  useIsomorphicLayoutEffect(() => {
    measure();
  }, [measure, courseId]);

  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  if (!courseId) return null;

  return (
    <MotionConfig reducedMotion="user">
      <div
        role="tablist"
        aria-label="Course view"
        className="border-border bg-card/90 absolute top-1/2 left-1/2 z-10 inline-flex -translate-x-1/2 -translate-y-1/2 items-center gap-1 rounded-xl border p-1 shadow-sm backdrop-blur-sm"
      >
        {indicator && (
          <motion.span
            aria-hidden
            className="bg-brand absolute top-1 bottom-1 left-0 rounded-lg"
            initial={false}
            animate={{ x: indicator.left, width: indicator.width }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
          />
        )}
        {TABS.map((tab, index) => {
          const selected = tab.key === page;
          const href = tabHref(courseId, tab.key);
          return (
            <button
              key={tab.key}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              role="tab"
              aria-selected={selected}
              onClick={() => navigate(href)}
              className={cn(
                "relative z-10 rounded-lg px-3.5 py-1 text-sm font-medium transition-colors",
                selected
                  ? "text-brand-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </MotionConfig>
  );
}
