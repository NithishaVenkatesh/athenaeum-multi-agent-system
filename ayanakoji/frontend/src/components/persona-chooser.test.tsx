import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PersonaChooser } from "@/components/persona-chooser";
import { PersonaProvider } from "@/components/persona-provider";
import { fetchLearners, type PersonaSummary } from "@/lib/api";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, fetchLearners: vi.fn() };
});
const mockFetchLearners = vi.mocked(fetchLearners);

function persona(employee_id: string, codename: string): PersonaSummary {
  return {
    employee_id,
    codename,
    team_id: "TEAM-A",
    vertical: "cloud-backend",
    seniority: "senior",
    role_title: "Senior Backend Engineer",
    certification: "AZ-204",
    is_manager: false,
    preferred_learning_slot: "Morning",
  };
}

function renderChooser() {
  return render(
    <PersonaProvider>
      <PersonaChooser />
    </PersonaProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe("PersonaChooser", () => {
  it("renders the learner roster with codename and account id", async () => {
    mockFetchLearners.mockResolvedValue([
      persona("EMP-001", "Vega"),
      persona("EMP-002", "Mira"),
    ]);

    renderChooser();

    await waitFor(() => expect(screen.getByText("Vega")).toBeInTheDocument());
    expect(screen.getByText("Mira")).toBeInTheDocument();
    expect(screen.getByText("EMP-001")).toBeInTheDocument();
  });

  it("stores the chosen persona and routes to the chat workspace", async () => {
    mockFetchLearners.mockResolvedValue([persona("EMP-001", "Vega")]);

    renderChooser();
    const card = await screen.findByRole("button", { name: /Sign in as Vega/ });
    fireEvent.click(card);

    expect(pushMock).toHaveBeenCalledWith("/chat");
    expect(window.localStorage.getItem("athenaeum.persona")).toContain("Vega");
  });

  it("shows an error when the roster cannot be loaded", async () => {
    mockFetchLearners.mockRejectedValue(new Error("network down"));

    renderChooser();

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
