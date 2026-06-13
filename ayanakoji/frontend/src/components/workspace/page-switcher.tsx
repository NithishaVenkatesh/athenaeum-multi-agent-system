"use client";

/**
 * Chat ↔ Assessments switcher for the active course. Pinned to the horizontal
 * center of the viewport (independent of the left/right top-bar content) and
 * shown only once a course exists in the route. The active choice is marked by a
 * single box that springs across to whichever tab is clicked (shared layoutId).
 */

import { MotionConfig, motion } from "framer-motion";
import { usePathname, useRouter } from "next/navigation";

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

export function PageSwitcher() {
  const pathname = usePathname();
  const router = useRouter();
  const { courseId, page } = parseChatRoute(pathname);

  if (!courseId) return null;

  return (
    <MotionConfig reducedMotion="user">
      <div
        role="tablist"
        aria-label="Course view"
        className="border-border bg-card/90 absolute top-1/2 left-1/2 z-10 inline-flex -translate-x-1/2 -translate-y-1/2 items-center gap-1 rounded-xl border p-1 shadow-sm backdrop-blur-sm"
      >
        {TABS.map((tab) => {
          const selected = tab.key === page;
          const href = tabHref(courseId, tab.key);
          return (
            <button
              key={tab.key}
              role="tab"
              aria-selected={selected}
              onClick={() => router.push(href)}
              className={cn(
                "relative rounded-lg px-3.5 py-1 text-sm font-medium transition-colors",
                selected
                  ? "text-brand-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {selected && (
                <motion.span
                  layoutId="page-switcher-active"
                  initial={false}
                  className="bg-brand absolute inset-0 rounded-lg"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <span className="relative z-10">{tab.label}</span>
            </button>
          );
        })}
      </div>
    </MotionConfig>
  );
}
