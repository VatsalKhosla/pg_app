import { ANALYTICS_EVENTS } from "@/lib/analytics";
import { MAX_BATCH } from "@/lib/analytics-beacon";
import { z } from "@/lib/forms/zod";
import { maskPii } from "@/lib/pii";

/**
 * What /api/events takes from a browser (step 3.9, ADR 0035), and what it passes on to PostHog.
 * Only the funnel's own events, a few flat properties each with short names and values, and an
 * anonymous id; anything else is refused whole.
 */

export const MAX_BODY_BYTES = 16_384;
const MAX_PROPERTIES = 12;

const property = z.union([z.string().max(200), z.number(), z.boolean(), z.null()]);

export const eventsBody = z
  .object({
    distinctId: z.uuid(),
    sentAt: z.iso.datetime(),
    events: z
      .array(
        z
          .object({
            uuid: z.uuid(),
            event: z.enum(ANALYTICS_EVENTS),
            timestamp: z.iso.datetime(),
            properties: z
              .record(z.string().regex(/^[a-z][A-Za-z0-9]{0,39}$/u), property)
              .refine((properties) => Object.keys(properties).length <= MAX_PROPERTIES),
          })
          .strict(),
      )
      .min(1)
      .max(MAX_BATCH),
  })
  .strict();

export type EventsBody = z.infer<typeof eventsBody>;

/**
 * PostHog's batch, as its own libraries send it: personless events (no profile is made for the
 * id), GeoIP off, and personal data masked once more. `sent_at` lets PostHog correct the
 * browser's clock.
 */
export function posthogBatch(body: EventsBody, projectKey: string) {
  return {
    api_key: projectKey,
    sent_at: body.sentAt,
    batch: body.events.map((item) => ({
      uuid: item.uuid,
      event: item.event,
      distinct_id: body.distinctId,
      timestamp: item.timestamp,
      properties: {
        ...maskPii(item.properties),
        $process_person_profile: false,
        $geoip_disable: true,
        $lib: "web",
      },
    })),
  };
}
