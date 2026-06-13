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
        catalog_id: "cb-c01",
        title: "Azure Compute & Serverless Foundations",
        cert: "AZ-204",
        pitch: "Build the compute layer.",
        prep_points: ["App Service", "Functions"],
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
    fireEvent.click(screen.getByRole("button", { name: /Pursue this course/i }));
    await waitFor(() => expect(mockAccept).toHaveBeenCalledWith("c1", "cb-c01"));
    await waitFor(() =>
      expect(screen.getByText(/now your course workspace/i)).toBeInTheDocument(),
    );
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
