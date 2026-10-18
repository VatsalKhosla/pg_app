import { publicEnv } from "@/config/env";

/** Send an error that an error boundary caught to Sentry, when error reporting is on. */
export function captureError(error: unknown): void {
  if (publicEnv.sentryDsn === undefined) {
    return;
  }
  void import("@sentry/nextjs").then((Sentry) => {
    Sentry.captureException(error);
  });
}
