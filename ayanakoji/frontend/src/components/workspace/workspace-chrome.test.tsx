import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PersonaProvider } from "@/components/persona-provider";
import { WorkspaceChrome } from "@/components/workspace/workspace-chrome";
import { listCourses, type PersonaSummary } from "@/lib/api";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  usePathname: () => "/chat",
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, listCourses: vi.fn(async () => []) };
});

const SAMPLE: PersonaSummary = {
  employee_id: "EMP-001",
  codename: "Vega",
  team_id: "TEAM-A",
  vertical: "cloud-backend",
  seniority: "senior",
  role_title: "Senior Backend Engineer",
  certification: "AZ-204",
  is_manager: false,
  preferred_learning_slot: "Morning",
};

afterEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe("WorkspaceChrome", () => {
  it("redirects to /login when no persona is signed in", async () => {
    render(
      <PersonaProvider>
        <WorkspaceChrome>
          <p>secret content</p>
        </WorkspaceChrome>
      </PersonaProvider>,
    );

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("secret content")).toBeNull();
  });

  it("renders the shell and children when signed in", async () => {
    window.localStorage.setItem("ayanakoji.persona", JSON.stringify(SAMPLE));
    void listCourses; // mocked; keeps the workspace provider from hitting the network

    render(
      <PersonaProvider>
        <WorkspaceChrome>
          <p>course content</p>
        </WorkspaceChrome>
      </PersonaProvider>,
    );

    await waitFor(() => expect(screen.getByText("course content")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });
});
