import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createCourse,
  fetchLearners,
  getCourse,
  patchCourse,
  streamMessage,
} from "@/lib/api";

afterEach(() => {
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("fetchLearners", () => {
  it("requests the learners-only roster", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([{ codename: "Vega" }]));
    vi.stubGlobal("fetch", fetchMock);

    const learners = await fetchLearners();

    expect(learners).toEqual([{ codename: "Vega" }]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/workiq/personas?learners_only=true"),
      expect.any(Object),
    );
  });
});

describe("createCourse", () => {
  it("POSTs persona_id and content", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      jsonResponse({ id: "c1", chat_name: "X" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const course = await createCourse("EMP-001", "Explain blob storage");

    expect(course.id).toBe("c1");
    const [, init] = fetchMock.mock.calls[0];
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      persona_id: "EMP-001",
      content: "Explain blob storage",
    });
  });
});

describe("patchCourse", () => {
  it("PATCHes the provided fields", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      jsonResponse({ id: "c1", chat_name: "New" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await patchCourse("c1", { chat_name: "New" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/courses/c1");
    expect(init).toMatchObject({ method: "PATCH" });
  });
});

describe("getCourse", () => {
  it("throws with the status code on a non-2xx response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    await expect(getCourse("missing")).rejects.toThrow(/404/);
  });
});

/** A Response-free fake reader so the test never depends on stream support. */
function sseFetch(chunks: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  return vi.fn(async () => ({
    ok: true,
    body: {
      getReader() {
        return {
          read: async () =>
            index < chunks.length
              ? { done: false, value: encoder.encode(chunks[index++]) }
              : { done: true, value: undefined },
        };
      },
    },
  }));
}

describe("streamMessage", () => {
  it("emits a token per SSE event, even across chunk boundaries", async () => {
    // The second event is deliberately split across two network chunks.
    vi.stubGlobal(
      "fetch",
      sseFetch([
        'data: {"token": "Hello"}\n\n',
        'data: {"to',
        'ken": " world"}\n\ndata: {"done": true}\n\n',
      ]),
    );

    const tokens: string[] = [];
    await streamMessage("c1", "hi", (token) => tokens.push(token));

    expect(tokens).toEqual(["Hello", " world"]);
  });

  it("throws when the response is not ok", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, body: null })));
    await expect(streamMessage("c1", "hi", () => {})).rejects.toThrow(/500/);
  });
});
