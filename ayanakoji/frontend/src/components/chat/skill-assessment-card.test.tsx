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

describe("SkillAssessmentCard", () => {
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
