"use client";

/**
 * Notifications + streak state for the workspace chrome. Polls the backend (which
 * ticks the cron lazily on read) on an interval, surfaces genuinely-new
 * notifications as live sonner toasts, and exposes the feed + actions to the
 * streak button and panel.
 *
 * Toast policy: the first load never toasts a backlog (offline-created
 * notifications just light the red badge); only items that newly appear while the
 * app is open toast, so a learner who returns to an open tab when the cron fires
 * gets a single macOS-style toast.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  markNotificationsToasted,
  type NotificationFeed,
  type NotificationItem,
  type StreakSummary,
} from "@/lib/api";

const POLL_INTERVAL_MS = 30_000;

const EMPTY_STREAK: StreakSummary = {
  persona_id: "",
  points: 0,
  on_time_streak: 0,
  miss_streak: 0,
};

interface NotificationsContextValue {
  notifications: NotificationItem[];
  unreadCount: number;
  streak: StreakSummary;
  /** Navigate to a notification's target and mark it read. */
  openNotification: (notification: NotificationItem) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  refresh: () => Promise<void>;
}

const NotificationsContext = createContext<NotificationsContextValue | null>(
  null,
);

function emitToast(
  notification: NotificationItem,
  open: (n: NotificationItem) => void,
): void {
  const options = {
    description: notification.body,
    action: { label: "Open", onClick: () => open(notification) },
  };
  switch (notification.kind) {
    case "deadline_missed":
      toast.error(notification.title, options);
      break;
    case "deadline_soon":
      toast.warning(notification.title, options);
      break;
    default:
      toast.success(notification.title, options);
      break;
  }
}

export function NotificationsProvider({
  personaId,
  children,
}: {
  personaId: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [streak, setStreak] = useState<StreakSummary>(EMPTY_STREAK);

  // Ids we've already accounted for, and whether we've completed the first load
  // (so a backlog of offline-created notifications never toasts en masse).
  const knownIdsRef = useRef<Set<string>>(new Set());
  const firstLoadRef = useRef(true);

  const openNotification = useCallback(
    (notification: NotificationItem) => {
      setNotifications((prev) =>
        prev.map((n) => (n.id === notification.id ? { ...n, read: true } : n)),
      );
      markNotificationRead(notification.id).catch(() => {
        // Non-fatal: the next poll reconciles read state.
      });
      router.push(notification.link);
    },
    [router],
  );

  const applyFeed = useCallback(
    (feed: NotificationFeed) => {
      setNotifications(feed.notifications);
      setStreak(feed.streak);

      const fresh = feed.notifications.filter(
        (n) => !n.toasted && !knownIdsRef.current.has(n.id),
      );
      feed.notifications.forEach((n) => knownIdsRef.current.add(n.id));

      if (fresh.length === 0) {
        firstLoadRef.current = false;
        return;
      }
      // First load only lights the badge; later polls toast genuinely-new items.
      if (!firstLoadRef.current) {
        fresh.forEach((n) => emitToast(n, openNotification));
      }
      firstLoadRef.current = false;
      markNotificationsToasted(fresh.map((n) => n.id)).catch(() => {
        // Non-fatal: server `toasted` is a best-effort de-dupe.
      });
    },
    [openNotification],
  );

  const refresh = useCallback(async () => {
    try {
      applyFeed(await fetchNotifications(personaId));
    } catch {
      // Keep the last-known feed on a transient error.
    }
  }, [personaId, applyFeed]);

  useEffect(() => {
    let active = true;
    knownIdsRef.current = new Set();
    firstLoadRef.current = true;
    // Subscription effect: poll an external system and setState in its callback —
    // exactly the pattern effects exist for. refresh() sets state only after its
    // await resolves, so there is no synchronous cascade.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();

    const interval = setInterval(() => {
      if (active && !document.hidden) void refresh();
    }, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (!document.hidden) void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      active = false;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  const markRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    );
    markNotificationRead(id).catch(() => {});
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    markAllNotificationsRead(personaId).catch(() => {});
  }, [personaId]);

  const unreadCount = useMemo(
    () => notifications.filter((n) => !n.read).length,
    [notifications],
  );

  const value = useMemo(
    () => ({
      notifications,
      unreadCount,
      streak,
      openNotification,
      markRead,
      markAllRead,
      refresh,
    }),
    [
      notifications,
      unreadCount,
      streak,
      openNotification,
      markRead,
      markAllRead,
      refresh,
    ],
  );

  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsContextValue {
  const context = useContext(NotificationsContext);
  if (!context) {
    throw new Error(
      "useNotifications must be used within a NotificationsProvider",
    );
  }
  return context;
}
