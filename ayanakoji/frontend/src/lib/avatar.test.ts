import { describe, expect, it } from "vitest";

import { avatarDataUri } from "@/lib/avatar";

describe("avatarDataUri", () => {
  it("is deterministic for the same seed", () => {
    expect(avatarDataUri("Vega")).toBe(avatarDataUri("Vega"));
  });

  it("produces different avatars for different seeds", () => {
    expect(avatarDataUri("Vega")).not.toBe(avatarDataUri("Mira"));
  });

  it("returns an SVG data URI", () => {
    expect(avatarDataUri("Orion")).toMatch(/^data:image\/svg\+xml/);
  });
});
