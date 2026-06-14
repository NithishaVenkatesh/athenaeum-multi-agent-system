import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssessmentsView } from "@/components/chat/assessments-view";
import { listEvaluations, type Evaluation } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listEvaluations: vi.fn() };
});
const mockList = vi.mocked(listEvaluations);

function evaluation(over: Partial<Evaluation>): Evaluation {
  return {
    module_id: "m1",
    module_title: "Module One",
    sequence: 1,
    type: "choices",
    locked: false,
    completed: false,
    attempted: false,
    score: null,
    passed: null,
    attempts_to_pass: null,
    review_assessment_id: null,
    attempts: 0,
    ...over,
  };
}

afterEach(() => vi.clearAllMocks());

describe("AssessmentsView", () => {
  it("shows a designed empty state when there are no evaluations", async () => {
    mockList.mockResolvedValue([]);
    render(<AssessmentsView courseId="c1" />);
    await waitFor(() =>
      expect(screen.getByText("No evaluations yet")).toBeInTheDocument(),
    );
  });

  it("groups evaluations by module and surfaces score, lock, and progress", async () => {
    mockList.mockResolvedValue([
      evaluation({
        type: "choices",
        completed: true,
        attempted: true,
        passed: true,
        score: 8,
        attempts_to_pass: 1,
        review_assessment_id: "a1",
        attempts: 1,
      }),
      evaluation({ type: "llm", locked: true }),
    ]);
    render(<AssessmentsView courseId="c1" />);

    await waitFor(() => expect(screen.getByText("Module One")).toBeInTheDocument());
    // The passed quiz shows its score and a review link; the oral is locked.
    expect(screen.getByText("8/10")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("Locked")).toBeInTheDocument();
    expect(screen.getByText("1/2 passed")).toBeInTheDocument();
  });
});
