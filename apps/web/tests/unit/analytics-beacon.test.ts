import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setAnalyticsTransport, track } from "@/lib/analytics";
import {
  analyticsId,
  EVENTS_PATH,
  type EventsBody,
  startBrowserAnalytics,
  trackingAllowed,
} from "@/lib/analytics-beacon";
import { searchProperties } from "@/lib/search/analytics";

describe("whether a browser is tracked", () => {
  it("isn't when it asks not to be", () => {
    expect(trackingAllowed({ doNotTrack: null })).toBe(true);
    expect(trackingAllowed({ doNotTrack: "1" })).toBe(false);
    expect(trackingAllowed({ doNotTrack: null, globalPrivacyControl: true })).toBe(false);
  });
});

describe("the browser's analytics", () => {
  const fetchMock = vi.fn<typeof fetch>();
  const beacon = vi.fn<(url: string, data: Blob) => boolean>();
  let stop: () => void = () => undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    beacon.mockReturnValue(true);
    Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
  });

  afterEach(() => {
    stop();
    setAnalyticsTransport(null);
    vi.useRealTimers();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    beacon.mockReset();
  });

  function sent(): EventsBody[] {
    return fetchMock.mock.calls.map(([, init]) => JSON.parse(init?.body as string) as EventsBody);
  }

  it("sends what came before it started, once it has", () => {
    track("pg_viewed", { slug: "sample" });
    stop = startBrowserAnalytics();
    vi.advanceTimersByTime(5_000);

    expect(sent()[0]?.events.map((event) => event.event)).toEqual(["pg_viewed"]);
  });

  it("has no id, and sends nothing, until started", () => {
    track("pg_viewed", { slug: "sample" });
    vi.runAllTimers();

    expect(analyticsId()).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a few seconds' events together, under the tab's one anonymous id", () => {
    stop = startBrowserAnalytics();
    const id = analyticsId();
    track("search_performed", { area: "campus", results: 3 });
    track("pg_viewed", { slug: "sample" });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.advanceTimersByTime(5_000);

    expect(id).toMatch(/^[0-9a-f-]{36}$/u);
    expect(analyticsId()).toBe(id);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(EVENTS_PATH);
    const [batch] = sent();
    expect(batch?.distinctId).toBe(id);
    expect(batch?.events.map((event) => event.event)).toEqual(["search_performed", "pg_viewed"]);
  });

  it("sends what's waiting by beacon when the page is hidden", () => {
    stop = startBrowserAnalytics();
    track("visit_requested", { slug: "sample", times: 2 });
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    expect(beacon).toHaveBeenCalledTimes(1);
    expect(beacon.mock.calls[0]?.[0]).toBe(EVENTS_PATH);
    expect(fetchMock).not.toHaveBeenCalled();
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });
});

describe("what a search reports", () => {
  it("is where and how it searched, never the words typed or the map's coordinates", () => {
    expect(
      searchProperties(
        {
          bbox: "77.20,28.68,77.22,28.70",
          q: "near my friend's place",
          gender: "girls",
          amenities: ["wifi"],
          limit: 12,
        },
        4,
      ),
    ).toEqual({ area: "map", place: null, filters: 3, sort: "recommended", results: 4 });
    expect(searchProperties({ campus: "hindu-college", sort: "distance" }, 0)).toEqual({
      area: "campus",
      place: "hindu-college",
      filters: 0,
      sort: "distance",
      results: 0,
    });
  });
});
