import { defineConfig, devices } from "@playwright/test";

// Browser tests against a production build (`make e2e` builds first). They run on a phone and a
// desktop viewport, since the layout and the menu differ.
const port = Number(process.env.E2E_PORT ?? "3100");
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
  webServer: {
    command: `next start --hostname 127.0.0.1 --port ${String(port)}`,
    url: baseURL,
    reuseExistingServer: !isCI,
    timeout: 60_000,
  },
});
