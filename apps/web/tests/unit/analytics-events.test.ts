// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsBody, posthogBatch } from "@/lib/security/analytics-events";

const posthog = vi.hoisted(() => ({
  current: undefined as { projectKey: string; host: string } | undefined,
}));
vi.mock("@/config/server-env", () => ({
  serverEnv: {
    get posthog() {
      return posthog.current;
    },
  },
}));

const DISTINCT = "0192f0a4-0000-4000-8000-0000000000aa";
const EVENT = {
  uuid: "0192f0a4-0000-4000-8000-000000000001",
  event: "pg_viewed",
  timestamp: "2027-07-14T10:00:00.000Z",
  properties: { slug: "fictional-sample-pg-aster-kamla-nagar" },
} as const;
const BODY = { distinctId: DISTINCT, sentAt: "2027-07-14T10:00:05.000Z", events: [EVENT] };

function post(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://127.0.0.1:3000/api/events", {
    method: "POST",
    headers: { "content-type": "application/json", "sec-fetch-site": "same-origin", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("what the browser may send", () => {
  it("is the funnel's events with a few flat properties and an anonymous id", () => {
    expect(eventsBody.safeParse(BODY).success).toBe(true);
    for (const body of [
      { ...BODY, distinctId: "someone@example.com" },
      { ...BODY, events: [] },
      { ...BODY, events: Array.from({ length: 21 }, () => EVENT) },
      { ...BODY, events: [{ ...EVENT, event: "$identify" }] },
      { ...BODY, events: [{ ...EVENT, properties: { $set: "a person property" } }] },
      { ...BODY, events: [{ ...EVENT, properties: { slug: "x".repeat(201) } }] },
      { ...BODY, events: [{ ...EVENT, properties: { nested: { a: 1 } } }] },
      { ...BODY, events: [{ ...EVENT, more: true }] },
      { ...BODY, more: true },
    ]) {
      expect(eventsBody.safeParse(body).success).toBe(false);
    }
  });

  it("reaches PostHog personless, without GeoIP and with phone numbers masked", () => {
    const parsed = eventsBody.parse({
      ...BODY,
      events: [{ ...EVENT, properties: { note: "call 9876543210" } }],
    });

    expect(posthogBatch(parsed, "phc_fictional")).toEqual({
      api_key: "phc_fictional",
      sent_at: BODY.sentAt,
      batch: [
        {
          uuid: EVENT.uuid,
          event: "pg_viewed",
          distinct_id: DISTINCT,
          timestamp: EVENT.timestamp,
          properties: {
            note: "call ******3210",
            $process_person_profile: false,
            $geoip_disable: true,
            $lib: "web",
          },
        },
      ],
    });
  });
});

describe("POST /api/events", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ status: "Ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    posthog.current = undefined;
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  async function route() {
    return (await import("@/app/api/events/route")).POST;
  }

  it("collects nothing without a PostHog project", async () => {
    const response = await (await route())(post(BODY) as never);

    expect(response.status).toBe(204);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes the batch on from this server, so PostHog never sees the visitor's address", async () => {
    posthog.current = { projectKey: "phc_fictional", host: "https://eu.i.posthog.com" };

    const response = await (
      await route()
    )(post(BODY, { "x-forwarded-for": "203.0.113.7" }) as never);

    expect(response.status).toBe(204);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("https://eu.i.posthog.com/batch/");
    expect(JSON.stringify(init?.headers)).not.toContain("203.0.113.7");
    const sent = JSON.parse(init?.body as string) as { batch: { distinct_id: string }[] };
    expect(sent.batch.map((item) => item.distinct_id)).toEqual([DISTINCT]);
  });

  it("refuses other sites, bad bodies and big ones, and never fails the page", async () => {
    posthog.current = { projectKey: "phc_fictional", host: "https://eu.i.posthog.com" };
    const POST = await route();

    expect((await POST(post(BODY, { "sec-fetch-site": "cross-site" }) as never)).status).toBe(403);
    expect((await POST(post("not json") as never)).status).toBe(400);
    expect((await POST(post("x".repeat(20_000)) as never)).status).toBe(413);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    expect((await POST(post(BODY) as never)).status).toBe(204);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
