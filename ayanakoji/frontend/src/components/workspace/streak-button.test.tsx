import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StreakButton } from "@/components/workspace/streak-button";
import type { StreakSummary } from "@/lib/api";

const { useNotificationsMock } = vi.hoisted(() => ({
  useNotificationsMock: vi.fn(),
}));

vi.mock("@/components/workspace/notifications-context", () => ({
  useNotifications: () => useNotificationsMock(),
}));

vi.mock("@/components/workspace/notifications-panel", () => ({
  NotificationsPanel: () => <div data-testid="panel" />,
}));

function setContext(unreadCount: number, streak: Partial<StreakSummary> = {}) {
  useNotificationsMock.mockReturnValue({
    notifications: [],
    unreadCount,
    streak: {
      persona_id: "EMP1",
      points: 40,
      on_time_streak: 4,
      miss_streak: 0,
      ...streak,
    },
    openNotification: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    refresh: vi.fn(),
  });
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("StreakButton", () => {
  it("renders the streak points and an accessible label", () => {
    setContext(2);
    render(<StreakButton />);
    const button = screen.getByRole("button", { name: /streak 40 points/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("40");
  });

  it("shows a red unread badge with the count", () => {
    setContext(3);
    render(<StreakButton />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("caps the badge at 9+", () => {
    setContext(12);
    render(<StreakButton />);
    expect(screen.getByText("9+")).toBeInTheDocument();
  });

  it("hides the badge when there are no unread notifications", () => {
    setContext(0);
    render(<StreakButton />);
    // Only the points "40" should be present; no badge number.
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
