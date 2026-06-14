import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseSwitcher } from "@/components/workspace/course-switcher";
import { WorkspaceProvider } from "@/components/workspace/workspace-context";
import { listCourses, type CourseSummary } from "@/lib/api";

const { pushMock, pathnameRef } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  pathnameRef: { current: "/chat/abc" },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => pathnameRef.current,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listCourses: vi.fn() };
});
const mockListCourses = vi.mocked(listCourses);

const COURSE: CourseSummary = {
  id: "abc",
  persona_id: "EMP-001",
  chat_name: "Functions deep dive",
  catalog_id: null,
  updated_at: "2026-06-13T00:00:00Z",
};

function renderSwitcher() {
  return render(
    <WorkspaceProvider personaId="EMP-001">
      <CourseSwitcher />
    </WorkspaceProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  pathnameRef.current = "/chat/abc";
});

describe("CourseSwitcher", () => {
  it("labels the trigger with the active course name", async () => {
    mockListCourses.mockResolvedValue([COURSE]);
    renderSwitcher();
    await waitFor(() =>
      expect(screen.getByText("Functions deep dive")).toBeInTheDocument(),
    );
  });

  it("labels the trigger 'New chat' when no course is active", async () => {
    pathnameRef.current = "/chat";
    mockListCourses.mockResolvedValue([COURSE]);
    renderSwitcher();
    await waitFor(() =>
      expect(screen.getByText("New chat")).toBeInTheDocument(),
    );
  });
});
