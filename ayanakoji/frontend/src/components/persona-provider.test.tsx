import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PersonaProvider, usePersona } from "@/components/persona-provider";
import type { PersonaSummary } from "@/lib/api";

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

const STORAGE_KEY = "athenaeum.persona";

function Consumer() {
  const { persona, ready, selectPersona, signOut } = usePersona();
  return (
    <div>
      <span data-testid="ready">{String(ready)}</span>
      <span data-testid="persona">{persona?.codename ?? "none"}</span>
      <button onClick={() => selectPersona(SAMPLE)}>select</button>
      <button onClick={signOut}>signout</button>
    </div>
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("PersonaProvider", () => {
  it("starts signed out and becomes ready after hydration", async () => {
    render(
      <PersonaProvider>
        <Consumer />
      </PersonaProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("true"));
    expect(screen.getByTestId("persona")).toHaveTextContent("none");
  });

  it("persists the selected persona and clears it on sign out", async () => {
    render(
      <PersonaProvider>
        <Consumer />
      </PersonaProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("true"));

    fireEvent.click(screen.getByText("select"));
    expect(screen.getByTestId("persona")).toHaveTextContent("Vega");
    expect(window.localStorage.getItem(STORAGE_KEY)).toContain("Vega");

    fireEvent.click(screen.getByText("signout"));
    expect(screen.getByTestId("persona")).toHaveTextContent("none");
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("restores a persona already in storage", async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(SAMPLE));

    render(
      <PersonaProvider>
        <Consumer />
      </PersonaProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("persona")).toHaveTextContent("Vega"));
  });

  it("throws when used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Consumer />)).toThrow(/must be used within a PersonaProvider/);
    spy.mockRestore();
  });
});
