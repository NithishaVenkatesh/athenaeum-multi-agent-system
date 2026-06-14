/**
 * Per-kind visual language for notifications — the icon and accent each kind
 * carries through the panel and toasts. Colour is semantic here (progress =
 * emerald, celebration = violet, warning = amber, miss = red), never decorative.
 */

import {
  ArrowRight,
  Clock,
  GraduationCap,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import type { NotificationKind } from "@/lib/api";

interface KindVisual {
  Icon: LucideIcon;
  /** Icon + tint for the leading chip. */
  chip: string;
  /** The unread dot colour. */
  dot: string;
}

export const NOTIFICATION_VISUALS: Record<NotificationKind, KindVisual> = {
  next_module: {
    Icon: ArrowRight,
    chip: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400",
    dot: "bg-emerald-500",
  },
  course_complete: {
    Icon: GraduationCap,
    chip: "bg-violet-500/12 text-violet-600 dark:text-violet-400",
    dot: "bg-violet-500",
  },
  deadline_soon: {
    Icon: Clock,
    chip: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    dot: "bg-amber-500",
  },
  deadline_missed: {
    Icon: TriangleAlert,
    chip: "bg-red-500/12 text-red-600 dark:text-red-400",
    dot: "bg-red-500",
  },
};

/** Compact relative time ("just now", "4m", "3h", "2d") for a notification row. */
export function formatRelativeTime(
  iso: string,
  now: number = Date.now(),
): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d`;
  return `${Math.round(days / 7)}w`;
}
