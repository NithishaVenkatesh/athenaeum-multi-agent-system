import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PageSwitcher } from "@/components/workspace/page-switcher";

const { pushMock, pathnameRef } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  pathnameRef: { current: "/chat" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => pathnameRef.current,
}));

afterEach(() => {
  vi.clearAllMocks();
  pathnameRef.current = "/chat";
});

describe("PageSwitcher", () => {
  it("renders nothing for a brand-new chat (no course id)", () => {
    pathnameRef.current = "/chat";
    render(<PageSwitcher />);
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  it("marks Chat active on a course's chat route", () => {
    pathnameRef.current = "/chat/abc";
    render(<PageSwitcher />);
    expect(screen.getByRole("tab", { name: "Chat" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Evaluations" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("marks Evaluations active and navigates between views", () => {
    pathnameRef.current = "/chat/abc/assessments";
    render(<PageSwitcher />);
    expect(screen.getByRole("tab", { name: "Evaluations" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.click(screen.getByRole("tab", { name: "Chat" }));
    expect(pushMock).toHaveBeenCalledWith("/chat/abc");
  });
});
