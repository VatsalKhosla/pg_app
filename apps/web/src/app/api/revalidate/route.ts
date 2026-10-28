import { revalidateTag } from "next/cache";
import type { NextRequest } from "next/server";

import { serverEnv } from "@/config/server-env";
import { isSignedByTheApi, MAX_BODY_BYTES, revalidationBody } from "@/lib/security/revalidation";

/**
 * The API's word that listings changed (ADR 0032): it names the cache tags of the data that's
 * out of date, and the next visit to a page made from it fetches it again, rather than serving
 * the old data once more. Without the shared secret there is no such route.
 */
export async function POST(request: NextRequest): Promise<Response> {
  const secret = serverEnv.revalidateSecret;
  if (secret === undefined) return new Response(null, { status: 404 });
  if (Number(request.headers.get("content-length") ?? "0") > MAX_BODY_BYTES) {
    return new Response(null, { status: 413 });
  }
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) return new Response(null, { status: 413 });
  const signed = isSignedByTheApi({
    secret,
    timestamp: request.headers.get("x-revalidate-timestamp"),
    signed: request.headers.get("x-revalidate-signature"),
    body,
    nowMs: Date.now(),
  });
  if (!signed) return new Response(null, { status: 401 });
  const parsed = revalidationBody.safeParse(parseJson(body));
  if (!parsed.success) return new Response(null, { status: 400 });
  for (const tag of parsed.data.tags) {
    // Gone at once: a listing just paused shouldn't be served again even once.
    revalidateTag(tag, { expire: 0 });
  }
  return Response.json({ revalidated: parsed.data.tags });
}

function parseJson(body: string): unknown {
  try {
    return JSON.parse(body);
  } catch {
    return undefined;
  }
}
