import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RenameCourseDialog } from "@/components/workspace/rename-course-dialog";
import { patchCourse, type Course, type CourseSummary } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, patchCourse: vi.fn() };
});
const mockPatch = vi.mocked(patchCourse);

const COURSE: CourseSummary = {
  id: "c1",
  persona_id: "EMP-001",
  chat_name: "Functions",
  catalog_id: null,
  status: 0,
  updated_at: "2026-06-13T00:00:00Z",
};

const RENAMED: Course = {
  id: "c1",
  persona_id: "EMP-001",
  chat_name: "Functions deep dive",
  catalog_id: null,
  catalog_title: null,
  status: 0,
  messages: [],
  assessment_ids: [],
  created_at: "",
  updated_at: "",
};

afterEach(() => vi.clearAllMocks());

describe("RenameCourseDialog", () => {
  it("prefills the current name and saves a new one", async () => {
    mockPatch.mockResolvedValue(RENAMED);
    const onOpenChange = vi.fn();
    const onRenamed = vi.fn();
    render(
      <RenameCourseDialog course={COURSE} onOpenChange={onOpenChange} onRenamed={onRenamed} />,
    );

    const input = screen.getByRole("textbox", { name: "Chat name" });
    expect(input).toHaveValue("Functions");
    fireEvent.change(input, { target: { value: "Functions deep dive" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockPatch).toHaveBeenCalledWith("c1", { chat_name: "Functions deep dive" }),
    );
    expect(onRenamed).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("does not patch when the name is unchanged", () => {
    const onOpenChange = vi.fn();
    render(
      <RenameCourseDialog course={COURSE} onOpenChange={onOpenChange} onRenamed={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mockPatch).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders nothing when no course is selected", () => {
    render(
      <RenameCourseDialog course={null} onOpenChange={vi.fn()} onRenamed={vi.fn()} />,
    );
    expect(screen.queryByRole("textbox", { name: "Chat name" })).toBeNull();
  });
});
