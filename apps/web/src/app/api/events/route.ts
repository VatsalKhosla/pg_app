import type { NextRequest } from "next/server";

import { publicEnv } from "@/config/env";
import { serverEnv } from "@/config/server-env";
import { eventsBody, MAX_BODY_BYTES, posthogBatch } from "@/lib/security/analytics-events";

// PostHog gets a few seconds; a slow answer isn't worth keeping a request open for.
const POSTHOG_TIMEOUT_MS = 3_000;

/**
 * The browser's analytics, passed on to PostHog (step 3.9, ADR 0035). The request to PostHog
 * comes from this server, so it never learns the visitor's IP address. Only this site's pages
 * may send here, within limits; without a PostHog project, nothing is collected. The answer is
 * always quick and empty: analytics never hold a page up.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const posthog = serverEnv.posthog;
  if (posthog === undefined) return new Response(null, { status: 204 });
  const fromThisSite =
    request.headers.get("sec-fetch-site") === "same-origin" ||
    request.headers.get("origin") === publicEnv.siteUrl.origin;
  if (!fromThisSite) return new Response(null, { status: 403 });
  if (Number(request.headers.get("content-length") ?? "0") > MAX_BODY_BYTES) {
    return new Response(null, { status: 413 });
  }
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return new Response(null, { status: 413 });
  const parsed = eventsBody.safeParse(parseJson(text));
  if (!parsed.success) return new Response(null, { status: 400 });
  try {
    const answer = await fetch(`${posthog.host}/batch/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(posthogBatch(parsed.data, posthog.projectKey)),
      signal: AbortSignal.timeout(POSTHOG_TIMEOUT_MS),
      cache: "no-store",
    });
    if (!answer.ok) console.warn(`analytics: PostHog answered ${String(answer.status)}`);
  } catch {
    console.warn("analytics: PostHog couldn't be reached");
  }
  return new Response(null, { status: 204 });
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
