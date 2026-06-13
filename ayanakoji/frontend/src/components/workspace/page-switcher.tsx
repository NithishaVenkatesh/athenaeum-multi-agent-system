"use client";

/**
 * Chat ↔ Assessments switcher for the active course. Only rendered once a chat
 * record exists (a course id is in the route); a brand-new chat has no
 * assessments view to switch to.
 */

import { usePathname, useRouter } from "next/navigation";

import { parseChatRoute, type ChatPage } from "@/lib/chat-route";
import { cn } from "@/lib/utils";

export function PageSwitcher() {
  const pathname = usePathname();
  const router = useRouter();
  const { courseId, page } = parseChatRoute(pathname);

  if (!courseId) return null;

  const tabs: { key: ChatPage; label: string; href: string }[] = [
    { key: "chat", label: "Chat", href: `/chat/${courseId}` },
    { key: "assessments", label: "Assessments", href: `/chat/${courseId}/assessments` },
  ];

  return (
    <div
      role="tablist"
      aria-label="Course view"
      className="border-border bg-card inline-flex items-center gap-1 rounded-full border p-1"
    >
      {tabs.map((tab) => {
        const selected = tab.key === page;
        return (
          <button
            key={tab.key}
            role="tab"
            aria-selected={selected}
            onClick={() => router.push(tab.href)}
            className={cn(
              "rounded-full px-3.5 py-1 text-sm font-medium transition-colors",
              selected
                ? "bg-brand text-brand-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
