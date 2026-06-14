import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PracticeCard } from "@/components/chat/practice-card";
import type { Practice } from "@/lib/api";

function practice(): Practice {
  return {
    module_id: "cb-c01-m01",
    title: "Functions",
    questions: [
      { id: "p1", kind: "mcq", prompt: "Q1?", choices: ["a", "b", "c", "d"] },
      { id: "p2", kind: "mcq", prompt: "Q2?", choices: ["a", "b", "c", "d"] },
    ],
  };
}

describe("PracticeCard", () => {
  it("renders questions and submits selections once every question is answered", () => {
    const onSubmit = vi.fn();
    render(<PracticeCard practice={practice()} busy={false} onSubmit={onSubmit} />);

    expect(screen.getByText("Q1?")).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: /submit practice/i });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getAllByLabelText("a")[0]);
    fireEvent.click(screen.getAllByLabelText("b")[1]);
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith({ p1: ["a"], p2: ["b"] });
  });
});
