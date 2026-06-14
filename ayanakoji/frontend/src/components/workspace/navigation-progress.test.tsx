import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NavProgressBar,
  NavigationProgress,
  useNavigate,
} from "@/components/workspace/navigation-progress";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

afterEach(() => vi.clearAllMocks());

function Consumer() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/chat/x")}>
      go
    </button>
  );
}

describe("NavProgressBar", () => {
  it("renders the bar only while navigating", () => {
    const { container, rerender } = render(<NavProgressBar active={false} />);
    expect(container.querySelector("[data-slot=nav-progress]")).toBeNull();

    rerender(<NavProgressBar active />);
    expect(container.querySelector("[data-slot=nav-progress]")).not.toBeNull();
  });
});

describe("useNavigate", () => {
  it("falls back to a plain router.push when no provider is mounted", () => {
    render(<Consumer />);
    fireEvent.click(screen.getByText("go"));
    expect(pushMock).toHaveBeenCalledWith("/chat/x");
  });

  it("navigates through the provider's transition", () => {
    render(
      <NavigationProgress>
        <Consumer />
      </NavigationProgress>,
    );
    fireEvent.click(screen.getByText("go"));
    expect(pushMock).toHaveBeenCalledWith("/chat/x");
  });
});
