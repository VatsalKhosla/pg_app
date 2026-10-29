import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";

import { z } from "@/lib/forms/zod";

/**
 * The API's requests to revalidate cached data (ADR 0032; apps/api/src/app/core/web_cache.py):
 * an HMAC-SHA256 of "<unix time>.<body>" in hex, with the shared secret, sent with the time. A
 * request more than five minutes off is refused, so a captured one soon stops working.
 */

export const MAX_AGE_SECONDS = 300;
export const MAX_BODY_BYTES = 4_096;
// The tags the API may name: one listing's, everything that lists them, and the policies'
// pages (ADR 0036).
const TAG = /^(listings|policies|listing:[a-z0-9]+(-[a-z0-9]+)*)$/u;

export const revalidationBody = z
  .object({ tags: z.array(z.string().max(256).regex(TAG)).min(1).max(20) })
  .strict();

export function signature(secret: string, timestamp: string, body: string): string {
  return createHmac("sha256", secret).update(`${timestamp}.${body}`).digest("hex");
}

/** Whether the request is the API's: signed with the shared secret, and recent. */
export function isSignedByTheApi({
  secret,
  timestamp,
  signed,
  body,
  nowMs,
}: {
  secret: string;
  timestamp: string | null;
  signed: string | null;
  body: string;
  nowMs: number;
}): boolean {
  if (timestamp === null || signed === null) return false;
  if (!/^[0-9]{1,12}$/u.test(timestamp) || !/^[0-9a-f]{64}$/u.test(signed)) return false;
  if (Math.abs(nowMs / 1_000 - Number(timestamp)) > MAX_AGE_SECONDS) return false;
  return timingSafeEqual(
    Buffer.from(signature(secret, timestamp, body), "hex"),
    Buffer.from(signed, "hex"),
  );
}
