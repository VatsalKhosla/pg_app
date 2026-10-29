/**
 * Product analytics (ARCHITECTURE §3; step 3.9, ADR 0035). Call sites use this typed API; where
 * events go is a transport: the site's own /api/events from the browser (lib/analytics-beacon),
 * a recorder in tests, and nowhere until one is set.
 *
 * Properties are flat primitives and never meant to hold personal data; strings are masked
 * anyway before they reach the transport, and again on the server.
 */
import { maskPii } from "@/lib/pii";

/**
 * The booking funnel, search → PG view → visit request → visit done → reservation, and the
 * pages' web vitals. "visit_completed" comes from the API, which knows when a field agent
 * finished the visit; "bed_reserved" arrives with booking (Phase 5).
 */
export const ANALYTICS_EVENTS = [
  "search_performed",
  "pg_viewed",
  "visit_requested",
  "visit_completed",
  "bed_reserved",
  "web_vital",
] as const;

export type AnalyticsEvent = (typeof ANALYTICS_EVENTS)[number];

export type AnalyticsProperties = Readonly<Record<string, string | number | boolean | null>>;

export interface AnalyticsTransport {
  capture(event: AnalyticsEvent, properties: AnalyticsProperties): void;
}

// A page's first events can come before its transport starts (effects run page first, layout
// last): the first few wait for it, and go once it does.
const MAX_WAITING = 20;
let waiting: [AnalyticsEvent, AnalyticsProperties][] = [];

const holdEvents: AnalyticsTransport = {
  capture(event, properties) {
    if (waiting.length < MAX_WAITING) waiting.push([event, properties]);
  },
};

const dropEvents: AnalyticsTransport = {
  capture() {
    // Stopped, or the browser asked not to be tracked.
  },
};

let transport: AnalyticsTransport = holdEvents;

/**
 * Where events go from now: the site's /api/events in the browser, a recorder in tests, or
 * nowhere (null). A transport gets the events that were waiting for one; null drops them.
 */
export function setAnalyticsTransport(next: AnalyticsTransport | null): void {
  transport = next ?? dropEvents;
  const held = waiting;
  waiting = [];
  if (next !== null) for (const [event, properties] of held) next.capture(event, properties);
}

export function track(event: AnalyticsEvent, properties: AnalyticsProperties = {}): void {
  transport.capture(event, maskPii(properties));
}
