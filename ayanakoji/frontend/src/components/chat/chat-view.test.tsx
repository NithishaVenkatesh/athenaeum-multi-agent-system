import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/components/chat/chat-view";
import { acceptCourse, createCourse, getCourse, streamMessage, type Course } from "@/lib/api";

vi.mock("@/components/workspace/workspace-context", () => ({
  useWorkspace: () => ({
    personaId: "EMP-001",
    reloadCourses: vi.fn(),
    courses: [],
    loading: false,
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    createCourse: vi.fn(),
    getCourse: vi.fn(),
    streamMessage: vi.fn(),
    acceptCourse: vi.fn(),
  };
});

const mockCreate = vi.mocked(createCourse);
const mockGet = vi.mocked(getCourse);
const mockStream = vi.mocked(streamMessage);
const mockAccept = vi.mocked(acceptCourse);

function course(overrides: Partial<Course> = {}): Course {
  return {
    id: "c1",
    persona_id: "EMP-001",
    chat_name: "Functions",
    catalog_id: null,
    catalog_title: null,
    status: 0,
    messages: [],
    assessment_ids: [],
    created_at: "2026-06-13T00:00:00Z",
    updated_at: "2026-06-13T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => vi.clearAllMocks());

describe("ChatView", () => {
  it("creates a course on the first message and streams the pipeline reply", async () => {
    mockCreate.mockResolvedValue(course({ chat_name: "RAG basics" }));
    mockStream.mockImplementation(async (_id, _text, handlers) => {
      handlers.onPhase?.({
        phase: "injection_gate",
        status: "passed",
        summary: "No injection detected",
        reasoning: "clean",
        provider: null,
        model: "regex-prefilter",
        tier: null,
        latency_ms: null,
        route: null,
        sources: [],
        steps: [],
        confidence: null,
        off_topic: null,
      });
      handlers.onToken?.("Hello ");
      handlers.onToken?.("world");
      handlers.onDone?.({ route: "general", suggested: false });
    });

    render(<ChatView />);
    const box = screen.getByRole("textbox", { name: "Message" });
    fireEvent.change(box, { target: { value: "Explain RAG" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() => expect(mockCreate).toHaveBeenCalledWith("EMP-001", "Explain RAG"));
    expect(mockStream).toHaveBeenCalledWith("c1", "Explain RAG", expect.any(Object));
    // User turn and streamed assistant reply both render.
    expect(screen.getByText("Explain RAG")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Hello world")).toBeInTheDocument());
    // The pipeline trace is shown (inspectable reasoning).
    expect(screen.getByText(/Reasoning & grounding/i)).toBeInTheDocument();
  });

  it("shows a course suggestion and enrolls on accept", async () => {
    mockCreate.mockResolvedValue(course());
    mockAccept.mockResolvedValue(course({ catalog_id: "cb-c01", status: 1 }));
    mockStream.mockImplementation(async (_id, _text, handlers) => {
      handlers.onToken?.("Here is the answer.");
      handlers.onSuggestion?.({
        prompt: "Want to start this course?",
        options: [
          {
            catalog_id: "cb-c01",
            title: "Azure Compute & Serverless Foundations",
            cert: "AZ-204",
            level: "foundational",
            pitch: "Build the compute layer.",
            reason: "Next step in your track.",
            prep_points: ["App Service", "Functions"],
          },
        ],
      });
      handlers.onDone?.({ route: "foundry_iq", suggested: true });
    });

    render(<ChatView />);
    const box = screen.getByRole("textbox", { name: "Message" });
    fireEvent.change(box, { target: { value: "azure functions" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() =>
      expect(
        screen.getByText("Azure Compute & Serverless Foundations"),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Choose$/i }));
    await waitFor(() => expect(mockAccept).toHaveBeenCalledWith("c1", "cb-c01"));
    await waitFor(() =>
      expect(screen.getByText(/now your course workspace/i)).toBeInTheDocument(),
    );
  });

  it("renders a calendar-grounded plan card from a plan event", async () => {
    mockCreate.mockResolvedValue(course());
    mockStream.mockImplementation(async (_id, _text, handlers) => {
      handlers.onToken?.("Here's your plan.");
      handlers.onPlan?.({
        catalog_id: "cb-c01",
        title: "Azure Compute & Serverless Foundations",
        cert: "AZ-204",
        pace: "normal",
        weekly_study_hours: 3,
        total_hours: 12.5,
        total_base_hours: 12.5,
        total_pace_hours: 12.5,
        weeks: 5,
        start_date: "2026-06-15",
        modules: [
          {
            module_id: "cb-c01-m01",
            title: "Hosting web APIs",
            sequence: 1,
            estimated_minutes: 195,
            base_minutes: 195,
            pace_minutes: 195,
            skill_delta: 0,
            complete_before: "2026-06-29",
            scheduled: [{ week: 1, day: "tue", start: "11:00", end: "12:00", minutes: 60 }],
            objectives: [],
          },
        ],
        sessions: [
          {
            day: "tue",
            slot: "Morning",
            start: "11:00",
            end: "12:00",
            duration_minutes: 60,
            source: "Cert study",
          },
        ],
        capacity_reason: "I found 3 h of study time already in your week — Tue 11:00–12:00.",
        balloon_warning: null,
        awaiting_approval: false,
      });
      handlers.onDone?.({ route: "study_plan", suggested: false });
    });

    render(<ChatView />);
    const box = screen.getByRole("textbox", { name: "Message" });
    fireEvent.change(box, { target: { value: "build me a study plan" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() => expect(screen.getByText(/Balanced pace/i)).toBeInTheDocument());
    expect(screen.getByText("Hosting web APIs")).toBeInTheDocument();
    expect(screen.getByText(/already in your week/i)).toBeInTheDocument();
    // The internal over-estimate factor is never surfaced.
    expect(screen.queryByText(/×2|over-estimat/i)).toBeNull();
  });

  it("shows the pace chooser before building a plan", async () => {
    mockCreate.mockResolvedValue(course());
    mockStream.mockImplementation(async (_id, _text, handlers) => {
      handlers.onToken?.("How fast do you want to go?");
      handlers.onPaceRequest?.({
        catalog_id: "cb-c01",
        title: "Azure Compute & Serverless Foundations",
        prompt: "How do you want to pace it?",
        options: ["slower", "normal", "faster"],
      });
      handlers.onDone?.({ route: "study_plan", suggested: false });
    });

    render(<ChatView />);
    const box = screen.getByRole("textbox", { name: "Message" });
    fireEvent.change(box, { target: { value: "build me a study plan" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Normal/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Slower/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Faster/i })).toBeInTheDocument();
  });

  it("loads and renders an existing conversation without a title heading", async () => {
    mockGet.mockResolvedValue(
      course({
        messages: [
          { role: "user", content: "hi" },
          { role: "assistant", content: "hello there" },
        ],
      }),
    );

    render(<ChatView courseId="c1" />);

    await waitFor(() => expect(screen.getByText("hello there")).toBeInTheDocument());
    expect(screen.getByText("hi")).toBeInTheDocument();
    // No in-page title button — the shell owns the title now.
    expect(screen.queryByRole("button", { name: "Functions" })).toBeNull();
  });
});
