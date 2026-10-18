/**
 * Product analytics (ARCHITECTURE §3). A stub until PostHog arrives in step 3.9: events go to a
 * transport that drops them. Call sites already use this typed API, so adding the vendor only
 * swaps the transport.
 *
 * Properties are flat primitives and never meant to hold personal data; strings are masked
 * anyway before they reach the transport.
 */
import { maskPii } from "@/lib/pii";

/** The booking funnel: search → PG view → visit request → visit done → reservation (step 3.9). */
export type AnalyticsEvent =
  "search_performed" | "pg_viewed" | "visit_requested" | "visit_completed" | "bed_reserved";

export type AnalyticsProperties = Readonly<Record<string, string | number | boolean | null>>;

export interface AnalyticsTransport {
  capture(event: AnalyticsEvent, properties: AnalyticsProperties): void;
}

const dropEvents: AnalyticsTransport = {
  capture() {
    // Nothing is collected until the analytics vendor is wired up (step 3.9).
  },
};

let transport: AnalyticsTransport = dropEvents;

/** Swap where events go: the vendor's client in step 3.9, a recorder in tests. */
export function setAnalyticsTransport(next: AnalyticsTransport | null): void {
  transport = next ?? dropEvents;
}

export function track(event: AnalyticsEvent, properties: AnalyticsProperties = {}): void {
  transport.capture(event, maskPii(properties));
}
