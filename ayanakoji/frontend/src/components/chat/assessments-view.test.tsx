import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssessmentsView } from "@/components/chat/assessments-view";
import { listAssessments } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listAssessments: vi.fn() };
});
const mockList = vi.mocked(listAssessments);

afterEach(() => vi.clearAllMocks());

describe("AssessmentsView", () => {
  it("shows a designed empty state when there are no assessments", async () => {
    mockList.mockResolvedValue([]);
    render(<AssessmentsView courseId="c1" />);
    await waitFor(() =>
      expect(screen.getByText("No assessments yet")).toBeInTheDocument(),
    );
  });

  it("lists assessments with their practice/evaluation mode", async () => {
    mockList.mockResolvedValue([
      { id: "a1", type: "choices", is_practice: true, created_at: "" },
      { id: "a2", type: "llm", is_practice: false, created_at: "" },
    ]);
    render(<AssessmentsView courseId="c1" />);

    await waitFor(() =>
      expect(screen.getByText(/choices assessment/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("Practice")).toBeInTheDocument();
    expect(screen.getByText("Evaluation")).toBeInTheDocument();
  });
});
