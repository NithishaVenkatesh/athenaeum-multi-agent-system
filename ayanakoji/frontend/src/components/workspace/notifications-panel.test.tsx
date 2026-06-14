import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationsPanel } from "@/components/workspace/notifications-panel";
import type { NotificationItem, StreakSummary } from "@/lib/api";

const { useNotificationsMock } = vi.hoisted(() => ({
  useNotificationsMock: vi.fn(),
}));

vi.mock("@/components/workspace/notifications-context", () => ({
  useNotifications: () => useNotificationsMock(),
}));

const STREAK: StreakSummary = {
  persona_id: "EMP1",
  points: 30,
  on_time_streak: 3,
  miss_streak: 0,
};

function note(over: Partial<NotificationItem>): NotificationItem {
  return {
    id: "n1",
    course_id: "c1",
    module_id: "m2",
    kind: "next_module",
    title: "Module complete",
    body: "Get started with Networking next.",
    link: "/chat/c1/modules/m2",
    read: false,
    toasted: true,
    created_at: new Date().toISOString(),
    ...over,
  };
}

function setContext(over: Record<string, unknown> = {}) {
  const value = {
    notifications: [note({})],
    unreadCount: 1,
    streak: STREAK,
    openNotification: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    refresh: vi.fn(),
    ...over,
  };
  useNotificationsMock.mockReturnValue(value);
  return value;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("NotificationsPanel", () => {
  it("shows the streak summary and a notification row", () => {
    setContext();
    render(<NotificationsPanel onClose={vi.fn()} />);
    expect(screen.getByText("Module complete")).toBeInTheDocument();
    expect(screen.getByText("30")).toBeInTheDocument(); // points
    expect(screen.getByText("3")).toBeInTheDocument(); // on-time streak
  });

  it("opens a notification and closes the panel on click", () => {
    const ctx = setContext();
    const onClose = vi.fn();
    render(<NotificationsPanel onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: /module complete/i }));
    expect(ctx.openNotification).toHaveBeenCalledWith(
      expect.objectContaining({ id: "n1" }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("marks all read from the header action", () => {
    const ctx = setContext();
    render(<NotificationsPanel onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /mark all read/i }));
    expect(ctx.markAllRead).toHaveBeenCalled();
  });

  it("hides mark-all-read when nothing is unread", () => {
    setContext({ unreadCount: 0, notifications: [note({ read: true })] });
    render(<NotificationsPanel onClose={vi.fn()} />);
    expect(
      screen.queryByRole("button", { name: /mark all read/i }),
    ).not.toBeInTheDocument();
  });

  it("renders an empty state when there are no notifications", () => {
    setContext({ notifications: [], unreadCount: 0 });
    render(<NotificationsPanel onClose={vi.fn()} />);
    expect(screen.getByText(/all caught up/i)).toBeInTheDocument();
  });
});
