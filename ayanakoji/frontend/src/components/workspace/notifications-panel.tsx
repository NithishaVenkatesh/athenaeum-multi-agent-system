"use client";

/**
 * The notifications panel shown inside the streak button's popover: a streak
 * summary strip, a mark-all-read affordance, and the scrollable list of
 * notifications. Each row is a real button — clicking it deep-links to the
 * module/course and clears the unread badge.
 */

import { BellOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useNotifications } from "@/components/workspace/notifications-context";
import {
  formatRelativeTime,
  NOTIFICATION_VISUALS,
} from "@/components/workspace/notification-visuals";
import type { NotificationItem } from "@/lib/api";
import { cn } from "@/lib/utils";

export function NotificationsPanel({ onClose }: { onClose: () => void }) {
  const { notifications, unreadCount, streak, openNotification, markAllRead } =
    useNotifications();

  function handleOpen(notification: NotificationItem) {
    openNotification(notification);
    onClose();
  }

  return (
    <div className="flex max-h-[26rem] w-80 flex-col">
      <header className="flex items-start justify-between gap-2 px-3.5 pt-3 pb-2.5">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Notifications
          </h2>
          <p className="text-muted-foreground mt-0.5 text-xs">
            <span className="text-foreground font-medium tabular-nums">
              {streak.points}
            </span>{" "}
            pts
            <span className="text-border mx-1.5">·</span>
            <span className="text-foreground font-medium tabular-nums">
              {streak.on_time_streak}
            </span>{" "}
            on-time streak
          </p>
        </div>
        {unreadCount > 0 && (
          <Button variant="ghost" size="xs" onClick={markAllRead}>
            Mark all read
          </Button>
        )}
      </header>

      <div className="bg-border/70 h-px" />

      {notifications.length === 0 ? (
        <div className="text-muted-foreground flex flex-col items-center gap-2 px-6 py-10 text-center">
          <BellOff className="size-5 opacity-60" />
          <p className="text-sm">You&rsquo;re all caught up.</p>
        </div>
      ) : (
        <ul className="overflow-y-auto py-1.5">
          {notifications.map((notification, index) => {
            const visual = NOTIFICATION_VISUALS[notification.kind];
            const Icon = visual.Icon;
            return (
              <li key={notification.id}>
                <button
                  type="button"
                  onClick={() => handleOpen(notification)}
                  style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
                  className={cn(
                    "group/notif relative flex w-full gap-3 px-3.5 py-2.5 text-left transition-colors",
                    "animate-in fade-in-0 slide-in-from-top-1 fill-mode-both duration-200 motion-reduce:animate-none",
                    "hover:bg-muted/60 focus-visible:bg-muted/60 outline-none",
                    !notification.read && "bg-amber-500/[0.04]",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg",
                      visual.chip,
                    )}
                  >
                    <Icon className="size-3.5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-medium">
                        {notification.title}
                      </span>
                      {!notification.read && (
                        <span
                          aria-label="Unread"
                          className={cn(
                            "size-1.5 shrink-0 rounded-full",
                            visual.dot,
                          )}
                        />
                      )}
                    </span>
                    <span className="text-muted-foreground mt-0.5 line-clamp-2 block text-xs leading-snug">
                      {notification.body}
                    </span>
                  </span>
                  <time className="text-muted-foreground shrink-0 text-[0.7rem] tabular-nums">
                    {formatRelativeTime(notification.created_at)}
                  </time>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
