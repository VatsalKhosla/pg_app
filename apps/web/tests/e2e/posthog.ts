// What reached PostHog's stand-in (tests/e2e/fake-posthog.mjs) in the browser tests.

export const POSTHOG_PORT = Number(process.env.E2E_POSTHOG_PORT ?? "8200");
export const POSTHOG_URL = `http://127.0.0.1:${String(POSTHOG_PORT)}`;
// The stand-in's project key; the web server and the API are given it too.
export const POSTHOG_KEY = "phc_e2e";

export interface CapturedEvent {
  uuid: string;
  event: string;
  distinct_id: string;
  timestamp: string;
  properties: Record<string, unknown>;
}

/** Every event sent under `distinctId`, oldest first. */
export async function eventsOf(distinctId: string): Promise<CapturedEvent[]> {
  const response = await fetch(`${POSTHOG_URL}/events`);
  const events = (await response.json()) as CapturedEvent[];
  return events
    .filter((event) => event.distinct_id === distinctId)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}
