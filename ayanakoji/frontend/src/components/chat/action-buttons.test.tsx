import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ActionButtons } from "@/components/chat/action-buttons";
import type { Action } from "@/lib/api";

describe("ActionButtons", () => {
  it("links 'take evaluation' to the module assessment", () => {
    const actions: Action[] = [
      { kind: "take_evaluation", label: "Take the evaluation", module_id: "cb-c01-m01" },
    ];
    render(<ActionButtons actions={actions} courseId="c1" onPracticeAgain={vi.fn()} />);
    const link = screen.getByRole("link", { name: /take the evaluation/i });
    expect(link).toHaveAttribute(
      "href",
      "/chat/c1/modules/cb-c01-m01/assessment/choices",
    );
  });

  it("links 'go to module' to the module page", () => {
    const actions: Action[] = [
      { kind: "go_to_module", label: "Go to the module", module_id: "cb-c01-m01" },
    ];
    render(<ActionButtons actions={actions} courseId="c1" onPracticeAgain={vi.fn()} />);
    expect(screen.getByRole("link", { name: /go to the module/i })).toHaveAttribute(
      "href",
      "/chat/c1/modules/cb-c01-m01",
    );
  });

  it("fires the practice-again callback as a button", () => {
    const onAgain = vi.fn();
    const actions: Action[] = [
      { kind: "practice_again", label: "Practise again", module_id: "cb-c01-m01" },
    ];
    render(<ActionButtons actions={actions} courseId="c1" onPracticeAgain={onAgain} />);
    fireEvent.click(screen.getByRole("button", { name: /practise again/i }));
    expect(onAgain).toHaveBeenCalled();
  });
});
