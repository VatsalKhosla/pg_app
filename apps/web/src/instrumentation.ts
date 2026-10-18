import type { Instrumentation } from "next";

// Server error reporting, off until SENTRY_DSN is set. Read at start-up, so one build can run in
// any environment.
const dsn = process.env.SENTRY_DSN ?? "";

export async function register(): Promise<void> {
  if (dsn === "") {
    return;
  }
  const { initSentry } = await import("@/lib/monitoring/sentry");
  initSentry(dsn);
}

export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (dsn === "") {
    return;
  }
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
};
