import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchNotifications,
  markNotificationRead,
  markNotificationsToasted,
  pingBackend,
  type NotificationFeed,
} from "@/lib/api";

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

const FEED: NotificationFeed = {
  notifications: [
    {
      id: "n1",
      course_id: "c1",
      module_id: "m2",
      kind: "next_module",
      title: "Module complete",
      body: "Start the next one.",
      link: "/chat/c1/modules/m2",
      read: false,
      toasted: false,
      created_at: "2026-06-14T00:00:00+00:00",
    },
  ],
  unread_count: 1,
  streak: { persona_id: "EMP1", points: 10, on_time_streak: 1, miss_streak: 0 },
};

describe("notifications client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // mock.calls infers a 0-length tuple; cast the captured fetch args for assertions.
  const firstCall = (mock: ReturnType<typeof vi.fn>): [string, RequestInit?] =>
    mock.mock.calls[0] as unknown as [string, RequestInit?];

  it("fetchNotifications encodes the persona and parses the feed", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify(FEED), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchNotifications("EMP 1");

    expect(result).toEqual(FEED);
    expect(firstCall(fetchMock)[0]).toContain(
      "/api/notifications?persona_id=EMP%201",
    );
  });

  it("markNotificationRead POSTs to the read endpoint", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ ...FEED.notifications[0], read: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await markNotificationRead("n1");

    expect(result.read).toBe(true);
    const [url, init] = firstCall(fetchMock);
    expect(url).toContain("/api/notifications/n1/read");
    expect(init?.method).toBe("POST");
  });

  it("markNotificationsToasted sends the ids as a JSON body", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ changed: 2 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await markNotificationsToasted(["n1", "n2"]);

    expect(result.changed).toBe(2);
    expect(firstCall(fetchMock)[1]?.body).toBe(
      JSON.stringify({ ids: ["n1", "n2"] }),
    );
  });
});
