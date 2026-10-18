import { publicEnv } from "@/config/env";

// Runs in the browser before the app starts. Error reporting stays off until a DSN is set; the
// SDK then loads as a separate chunk, outside the initial bundle.
const dsn = publicEnv.sentryDsn;
if (dsn !== undefined) {
  void import("@/lib/monitoring/sentry").then(({ initSentry }) => {
    initSentry(dsn);
  });
}
