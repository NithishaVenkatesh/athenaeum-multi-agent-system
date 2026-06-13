import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatComposer } from "@/components/chat/chat-composer";

describe("ChatComposer", () => {
  it("sends a trimmed message on Enter and clears the field", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} busy={false} />);
    const box = screen.getByRole("textbox", { name: "Message" });

    fireEvent.change(box, { target: { value: "  Explain RAG  " } });
    fireEvent.keyDown(box, { key: "Enter" });

    expect(onSend).toHaveBeenCalledWith("Explain RAG");
    expect((box as HTMLTextAreaElement).value).toBe("");
  });

  it("does not send on Shift+Enter (newline)", () => {
    const onSend = vi.fn();
    render(<ChatComposer onSend={onSend} busy={false} />);
    const box = screen.getByRole("textbox", { name: "Message" });

    fireEvent.change(box, { target: { value: "line one" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables the send button while busy", () => {
    render(<ChatComposer onSend={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });
});
