import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackendStatus } from "@/components/backend-status";
import { pingBackend } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, pingBackend: vi.fn() };
});

const mockPing = vi.mocked(pingBackend);

describe("BackendStatus", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the connected state when the backend responds", async () => {
    mockPing.mockResolvedValue({
      message: "pong",
      service: "ayanakoji-backend",
      version: "0.1.0",
      timestamp: "2026-01-01T00:00:00+00:00",
    });

    render(<BackendStatus />);

    await waitFor(() =>
      expect(screen.getByText("Backend connected")).toBeInTheDocument(),
    );
    expect(screen.getByText("ayanakoji-backend")).toBeInTheDocument();
  });

  it("renders the unreachable state when the ping fails", async () => {
    mockPing.mockRejectedValue(new Error("network down"));

    render(<BackendStatus />);

    await waitFor(() =>
      expect(screen.getByText("Backend unreachable")).toBeInTheDocument(),
    );
  });
});
