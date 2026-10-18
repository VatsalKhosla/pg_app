import * as Sentry from "@sentry/nextjs";

import { publicEnv } from "@/config/env";
import { maskPii } from "@/lib/pii";

/**
 * Error reporting, the same in the browser and on the server (the package resolves to the right
 * SDK for each). src/instrumentation-client.ts and src/instrumentation.ts load this module only
 * when a DSN is set, so the SDK never weighs on the initial bundle.
 *
 * Errors only for now: no tracing or replays. The SDK collects as little as still explains an
 * error (DPDP: collect the minimum), and phone numbers are masked in whatever it sends.
 */
export function initSentry(dsn: string): void {
  Sentry.init({
    dsn,
    environment: publicEnv.appEnv,
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      stackFrameVariables: false,
      databaseQueryData: false,
      queues: false,
      genAI: { inputs: false, outputs: false },
    },
    beforeSend: (event) => maskPii(event),
    beforeBreadcrumb: (breadcrumb) => maskPii(breadcrumb),
  });
}
