import { afterEach, describe, expect, it, vi } from "vitest";

import { pingBackend } from "@/lib/api";

const PAYLOAD = {
  message: "pong",
  service: "athenaeum-backend",
  version: "0.1.0",
  timestamp: "2026-01-01T00:00:00+00:00",
};

describe("pingBackend", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the parsed payload on a 2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(PAYLOAD), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );

    const result = await pingBackend();

    expect(result).toEqual(PAYLOAD);
  });

  it("throws with the status code on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 503 })),
    );

    await expect(pingBackend()).rejects.toThrow(/503/);
  });
});
