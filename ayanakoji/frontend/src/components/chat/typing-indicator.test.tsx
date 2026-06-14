import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TypingIndicator } from "@/components/chat/typing-indicator";

describe("TypingIndicator", () => {
  it("renders an accessible thinking status with three dots", () => {
    const { container } = render(<TypingIndicator />);

    expect(screen.getByRole("status", { name: /thinking/i })).toBeInTheDocument();
    expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(3);
  });
});
