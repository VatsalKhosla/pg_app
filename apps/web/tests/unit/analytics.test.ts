// @vitest-environment node
import { afterEach, describe, expect, it } from "vitest";

import {
  type AnalyticsEvent,
  type AnalyticsProperties,
  setAnalyticsTransport,
  track,
} from "@/lib/analytics";

afterEach(() => {
  setAnalyticsTransport(null);
});

describe("track", () => {
  it("keeps the first events for the transport, which may start after them", () => {
    track("pg_viewed", { slug: "sample-pg" });
    const captured: AnalyticsEvent[] = [];
    setAnalyticsTransport({
      capture: (event) => {
        captured.push(event);
      },
    });

    expect(captured).toEqual(["pg_viewed"]);
  });

  it("drops them once told there is no transport", () => {
    track("pg_viewed", { slug: "sample-pg" });
    setAnalyticsTransport(null);
    const captured: AnalyticsEvent[] = [];
    setAnalyticsTransport({
      capture: (event) => {
        captured.push(event);
      },
    });

    expect(captured).toEqual([]);
  });

  it("masks phone numbers before an event reaches the transport", () => {
    const captured: [AnalyticsEvent, AnalyticsProperties][] = [];
    setAnalyticsTransport({
      capture: (event, properties) => {
        captured.push([event, properties]);
      },
    });

    track("visit_requested", { note: "call me on 9876543210", slots: 2, firstVisit: true });

    expect(captured).toEqual([
      ["visit_requested", { note: "call me on ******3210", slots: 2, firstVisit: true }],
    ]);
  });
});
