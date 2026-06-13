import { describe, expect, it } from "vitest";

import { parseChatRoute } from "@/lib/chat-route";

describe("parseChatRoute", () => {
  it("treats bare /chat as a new chat with no course", () => {
    expect(parseChatRoute("/chat")).toEqual({ courseId: null, page: "chat" });
  });

  it("reads the course id from /chat/<id>", () => {
    expect(parseChatRoute("/chat/abc123")).toEqual({ courseId: "abc123", page: "chat" });
  });

  it("reads the assessments sub-page", () => {
    expect(parseChatRoute("/chat/abc123/assessments")).toEqual({
      courseId: "abc123",
      page: "assessments",
    });
  });

  it("falls back to new chat for unrelated paths", () => {
    expect(parseChatRoute("/")).toEqual({ courseId: null, page: "chat" });
  });
});
