import { defineConfig, devices } from "@playwright/test";

import { API_LOG } from "./tests/e2e/api-log";

// Browser tests against a production build (`make e2e` builds first) and the real API, started
// by scripts/e2e-api.sh on its own database, so signing in runs end to end. They run on a phone
// and a desktop viewport, since the layout and the menu differ.
const port = Number(process.env.E2E_PORT ?? "3100");
const apiPort = Number(process.env.E2E_API_PORT ?? "8100");
const baseURL = `http://127.0.0.1:${String(port)}`;
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
      env: { E2E_PORT: String(port), E2E_API_PORT: String(apiPort), E2E_API_LOG: API_LOG },
    },
    {
      command: `next start --hostname 127.0.0.1 --port ${String(port)}`,
      url: baseURL,
      reuseExistingServer: !isCI,
      timeout: 60_000,
    },
  ],
});
