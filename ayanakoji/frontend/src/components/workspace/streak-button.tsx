"use client";

/**
 * The streak fire button in the top bar. The flame carries the learner's running
 * points; a red badge counts unread notifications; clicking opens the
 * notifications panel. One control, three jobs (the spec's "counter in red about
 * the button").
 */

import { useState } from "react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useNotifications } from "@/components/workspace/notifications-context";
import { NotificationsPanel } from "@/components/workspace/notifications-panel";
import { cn } from "@/lib/utils";

export function StreakButton() {
  const [open, setOpen] = useState(false);
  const { unreadCount, streak } = useNotifications();
  const badge = unreadCount > 9 ? "9+" : String(unreadCount);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button
            type="button"
            aria-label={`Streak ${streak.points} points, ${unreadCount} unread notifications`}
            className={cn(
              "relative inline-flex items-center gap-1.5 rounded-xl border py-1 pr-2.5 pl-1.5 transition-[transform,border-color,background-color] duration-150 ease-out",
              "border-border bg-card hover:border-amber-500/45 hover:bg-amber-500/[0.06]",
              "active:scale-[0.97] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 outline-none",
              "aria-expanded:border-amber-500/55 aria-expanded:bg-amber-500/[0.08]",
            )}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/streak-flame.png"
              alt=""
              width={26}
              height={26}
              className="size-[26px] object-contain drop-shadow-[0_1px_4px_oklch(70%_0.19_45/0.45)]"
            />
            <span
              className={cn(
                "font-mono text-sm font-semibold tabular-nums",
                streak.points < 0
                  ? "text-red-600 dark:text-red-400"
                  : "text-foreground",
              )}
            >
              {streak.points}
            </span>
            {unreadCount > 0 && (
              <span
                aria-hidden
                className="absolute -top-1.5 -right-1.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[0.65rem] font-bold text-white ring-2 ring-background"
              >
                {badge}
              </span>
            )}
          </button>
        }
      />
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-80 overflow-hidden p-0"
      >
        <NotificationsPanel onClose={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}
