import { defineConfig, devices } from "@playwright/test";

import { API_LOG } from "./tests/e2e/api-log";
import { POSTHOG_KEY, POSTHOG_PORT, POSTHOG_URL } from "./tests/e2e/posthog";

// Browser tests against a production build (`make e2e` builds first) and the real API, started
// by scripts/e2e-api.sh on its own database, so signing in runs end to end. They run on a phone
// and a desktop viewport, since the layout and the menu differ.
const port = Number(process.env.E2E_PORT ?? "3100");
const apiPort = Number(process.env.E2E_API_PORT ?? "8100");
const baseURL = `http://127.0.0.1:${String(port)}`;
// The API signs revalidation requests with it and the web server checks them (ADR 0032).
const revalidateSecret = "e2e-only-revalidate-secret-0123456789ab";
const isCI = process.env.CI !== undefined;

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "phone", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "../../scripts/e2e-api.sh",
      url: `http://127.0.0.1:${String(apiPort)}/healthz`,
      reuseExistingServer: !isCI,
      // The first run builds the database image and migrates.
      timeout: 300_000,
      env: {
        E2E_PORT: String(port),
        E2E_API_PORT: String(apiPort),
        E2E_API_LOG: API_LOG,
        E2E_REVALIDATE_SECRET: revalidateSecret,
        E2E_POSTHOG_PORT: String(POSTHOG_PORT),
      },
    },
    {
      // PostHog's stand-in: where the web server and the API's worker send the funnel (ADR 0035).
      command: "node tests/e2e/fake-posthog.mjs",
      url: `${POSTHOG_URL}/healthz`,
      env: { E2E_POSTHOG_PORT: String(POSTHOG_PORT) },
      reuseExistingServer: !isCI,
    },
    {
      command: `next start --hostname 127.0.0.1 --port ${String(port)}`,
      url: baseURL,
      env: {
        REVALIDATE_SECRET: revalidateSecret,
        POSTHOG_PROJECT_KEY: POSTHOG_KEY,
        POSTHOG_HOST: POSTHOG_URL,
      },
      reuseExistingServer: !isCI,
      timeout: 60_000,
    },
  ],
});
