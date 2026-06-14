import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NotificationsProvider,
  useNotifications,
} from "@/components/workspace/notifications-context";
import type { NotificationFeed, NotificationItem } from "@/lib/api";

const {
  fetchMock,
  toastMock,
  pushMock,
  routerMock,
  toastedMock,
  readMock,
  allReadMock,
} = vi.hoisted(() => {
  const pushMock = vi.fn();
  return {
    fetchMock: vi.fn<(personaId: string) => Promise<NotificationFeed>>(),
    toastMock: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
    pushMock,
    // Stable router object (Next's useRouter is stable across renders); an
    // unstable mock would churn the provider's effect deps and reset its state.
    routerMock: { push: pushMock },
    toastedMock: vi.fn((ids: string[]) => Promise.resolve({ changed: ids.length })),
    readMock: vi.fn((id: string) => Promise.resolve({ id })),
    allReadMock: vi.fn((personaId: string) =>
      Promise.resolve({ changed: personaId.length }),
    ),
  };
});

vi.mock("@/lib/api", () => ({
  fetchNotifications: (personaId: string) => fetchMock(personaId),
  markNotificationsToasted: (ids: string[]) => toastedMock(ids),
  markNotificationRead: (id: string) => readMock(id),
  markAllNotificationsRead: (personaId: string) => allReadMock(personaId),
}));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("next/navigation", () => ({ useRouter: () => routerMock }));

function note(over: Partial<NotificationItem>): NotificationItem {
  return {
    id: "n1",
    course_id: "c1",
    module_id: "m2",
    kind: "next_module",
    title: "Module complete",
    body: "Start the next one.",
    link: "/chat/c1/modules/m2",
    read: false,
    toasted: false,
    created_at: "2026-06-14T00:00:00+00:00",
    ...over,
  };
}

function feed(
  notifications: NotificationItem[],
  points = 10,
): NotificationFeed {
  return {
    notifications,
    unread_count: notifications.filter((n) => !n.read).length,
    streak: { persona_id: "EMP1", points, on_time_streak: 1, miss_streak: 0 },
  };
}

function Consumer() {
  const {
    notifications,
    unreadCount,
    streak,
    refresh,
    markAllRead,
    openNotification,
  } = useNotifications();
  return (
    <div>
      <span data-testid="count">{unreadCount}</span>
      <span data-testid="points">{streak.points}</span>
      <span data-testid="len">{notifications.length}</span>
      <button onClick={() => refresh()}>refresh</button>
      <button onClick={() => markAllRead()}>all</button>
      {notifications[0] && (
        <button onClick={() => openNotification(notifications[0])}>
          open0
        </button>
      )}
    </div>
  );
}

function renderProvider() {
  return render(
    <NotificationsProvider personaId="EMP1">
      <Consumer />
    </NotificationsProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("NotificationsProvider", () => {
  it("hydrates the feed and derives the unread count", async () => {
    fetchMock.mockResolvedValue(feed([note({})]));
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId("len").textContent).toBe("1"),
    );
    expect(screen.getByTestId("count").textContent).toBe("1");
    expect(screen.getByTestId("points").textContent).toBe("10");
  });

  it("does not toast the backlog on first load, but marks it toasted", async () => {
    fetchMock.mockResolvedValue(feed([note({})]));
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId("len").textContent).toBe("1"),
    );
    expect(toastMock.success).not.toHaveBeenCalled();
    expect(toastedMock).toHaveBeenCalledWith(["n1"]);
  });

  it("toasts a notification that newly appears on a later poll", async () => {
    fetchMock.mockResolvedValueOnce(feed([note({ id: "n1", toasted: false })]));
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId("len").textContent).toBe("1"),
    );

    // Next poll: n1 is now toasted, and a brand-new n2 appears.
    fetchMock.mockResolvedValueOnce(
      feed([
        note({ id: "n1", toasted: true }),
        note({
          id: "n2",
          kind: "deadline_missed",
          title: "Deadline missed",
          toasted: false,
        }),
      ]),
    );
    fireEvent.click(screen.getByText("refresh"));

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledTimes(1));
    expect(toastMock.error).toHaveBeenCalledWith(
      "Deadline missed",
      expect.objectContaining({ description: expect.any(String) }),
    );
    expect(toastedMock).toHaveBeenLastCalledWith(["n2"]);
  });

  it("openNotification navigates and clears the unread badge", async () => {
    fetchMock.mockResolvedValue(feed([note({})]));
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId("count").textContent).toBe("1"),
    );

    fireEvent.click(screen.getByText("open0"));
    expect(pushMock).toHaveBeenCalledWith("/chat/c1/modules/m2");
    expect(readMock).toHaveBeenCalledWith("n1");
    await waitFor(() =>
      expect(screen.getByTestId("count").textContent).toBe("0"),
    );
  });

  it("markAllRead zeroes the unread count", async () => {
    fetchMock.mockResolvedValue(feed([note({ id: "a" }), note({ id: "b" })]));
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId("count").textContent).toBe("2"),
    );

    fireEvent.click(screen.getByText("all"));
    expect(allReadMock).toHaveBeenCalledWith("EMP1");
    await waitFor(() =>
      expect(screen.getByTestId("count").textContent).toBe("0"),
    );
  });
});
