import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountButton } from "@/components/workspace/account-button";
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

describe("AccountButton", () => {
  it("shows the signed-in persona and signs out", async () => {
    window.localStorage.setItem("athenaeum.persona", JSON.stringify(SAMPLE));

    render(
      <PersonaProvider>
        <AccountButton />
      </PersonaProvider>,
    );

    await waitFor(() => expect(screen.getByText("Vega")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(window.localStorage.getItem("athenaeum.persona")).toBeNull();
  });
});
