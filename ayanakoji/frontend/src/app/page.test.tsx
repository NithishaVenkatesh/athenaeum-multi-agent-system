import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";
import { PersonaProvider } from "@/components/persona-provider";
import type { PersonaSummary } from "@/lib/api";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: replaceMock }) }));

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

describe("Home", () => {
  it("redirects to /login when signed out", async () => {
    render(
      <PersonaProvider>
        <Home />
      </PersonaProvider>,
    );
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("redirects to /chat when a persona is signed in", async () => {
    window.localStorage.setItem("athenaeum.persona", JSON.stringify(SAMPLE));
    render(
      <PersonaProvider>
        <Home />
      </PersonaProvider>,
    );
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/chat"));
  });
});
