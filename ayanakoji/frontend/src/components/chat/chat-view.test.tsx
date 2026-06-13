import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatView } from "@/components/chat/chat-view";
import { createCourse, getCourse, streamMessage, type Course } from "@/lib/api";

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
  };
});

const mockCreate = vi.mocked(createCourse);
const mockGet = vi.mocked(getCourse);
const mockStream = vi.mocked(streamMessage);

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
  it("creates a course on the first message and streams the reply", async () => {
    mockCreate.mockResolvedValue(course({ chat_name: "RAG basics" }));
    mockStream.mockImplementation(async (_id, _text, onToken) => {
      onToken("Hello ");
      onToken("world");
    });

    render(<ChatView />);
    const box = screen.getByRole("textbox", { name: "Message" });
    fireEvent.change(box, { target: { value: "Explain RAG" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith("EMP-001", "Explain RAG"),
    );
    expect(mockStream).toHaveBeenCalledWith("c1", "Explain RAG", expect.any(Function));
    // User turn and streamed assistant reply both render. The title is not shown
    // on the chat page (it lives in the shell's chat switcher).
    expect(screen.getByText("Explain RAG")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Hello world")).toBeInTheDocument());
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
