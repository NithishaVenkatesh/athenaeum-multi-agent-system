import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SkillAssessmentCard } from "./skill-assessment-card";
import type { SkillCheck } from "@/lib/api";

const CHECK: SkillCheck = {
  catalog_id: "de-c01",
  title: "Data Eng",
  modules: [
    {
      module_id: "m1",
      title: "Module One",
      questions: [{ id: "q1", prompt: "Pick one", kind: "mcq", choices: ["A", "B"] }],
    },
  ],
};

const TWO_MODULES: SkillCheck = {
  catalog_id: "de-c01",
  title: "Data Eng",
  modules: [
    {
      module_id: "m1",
      title: "Module One",
      questions: [{ id: "q1", prompt: "Question one", kind: "mcq", choices: ["A", "B"] }],
    },
    {
      module_id: "m2",
      title: "Module Two",
      questions: [{ id: "q2", prompt: "Question two", kind: "mcq", choices: ["A", "B"] }],
    },
  ],
};

describe("SkillAssessmentCard", () => {
  it("steps module-by-module: Next until the last module, then Submit", () => {
    const onSubmit = vi.fn();
    render(<SkillAssessmentCard check={TWO_MODULES} busy={false} onSubmit={onSubmit} />);

    // First module: advance with "Next module"; Submit is not offered yet.
    expect(screen.getByText("Question one")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next module/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit skill check/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /next module/i }));

    // Last module: its questions show, Submit appears, Next is gone.
    expect(screen.getByText("Question two")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit skill check/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next module/i })).toBeNull();
  });

  it("disables submit until every question is answered, then submits answers", () => {
    const onSubmit = vi.fn();
    render(<SkillAssessmentCard check={CHECK} busy={false} onSubmit={onSubmit} />);

    const submit = screen.getByRole("button", { name: /submit/i });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByLabelText("A"));
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith([
      { module_id: "m1", question_id: "q1", selections: ["A"] },
    ]);
  });
});
