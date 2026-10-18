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
  it("drops events until a transport is set", () => {
    expect(() => {
      track("pg_viewed", { slug: "sample-pg" });
    }).not.toThrow();
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
