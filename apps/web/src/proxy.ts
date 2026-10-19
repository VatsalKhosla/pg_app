import { NextResponse, type NextRequest } from "next/server";

import { publicEnv } from "@/config/env";
import { sentryEndpoints } from "@/lib/monitoring/sentry-dsn";
import { buildContentSecurityPolicy, newNonce, reportingEndpoints } from "@/lib/security/csp";

const sentry =
  publicEnv.sentryDsn === undefined
    ? undefined
    : sentryEndpoints(publicEnv.sentryDsn, publicEnv.appEnv);

const connectOrigins = [publicEnv.apiUrl.origin, ...(sentry === undefined ? [] : [sentry.origin])];

/**
 * Runs before every page (Next.js 16's name for middleware): gives the request a fresh nonce and
 * the matching Content Security Policy. Next.js reads the policy from the request headers and puts
 * the nonce on its scripts; the browser gets the same policy in the response. Pages therefore
 * render per request (the root layout opts in), since a static page can't carry a fresh nonce.
 *
 * It also gives the request an id, which the server's API calls pass on (src/lib/api/server.ts)
 * so the API's log lines match the page request. Ids from the browser are never trusted.
 */
export function proxy(request: NextRequest): NextResponse {
  const nonce = newNonce();
  const requestId = crypto.randomUUID();
  const policy = buildContentSecurityPolicy({
    nonce,
    isDevelopment: process.env.NODE_ENV === "development",
    upgradeInsecureRequests: publicEnv.siteUrl.protocol === "https:",
    connectOrigins,
    reportUrl: sentry?.securityReportUrl,
  });

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("x-request-id", requestId);
  requestHeaders.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  response.headers.set("X-Request-ID", requestId);
  if (sentry !== undefined) {
    response.headers.set("Reporting-Endpoints", reportingEndpoints(sentry.securityReportUrl));
  }
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: not static files, image optimisation, icons, the manifest or robots.txt.
      // Whole names only, so a page such as /icons-guide still gets its policy.
      source:
        "/((?!_next/static/|_next/image|favicon\\.ico$|icon(?:/|$)|apple-icon$|manifest\\.webmanifest$|robots\\.txt$).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
