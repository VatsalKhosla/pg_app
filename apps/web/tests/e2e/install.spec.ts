import { expect, test } from "./fixtures";

// The site installs as an app (BUILD_PLAN 3.9): Chrome itself says whether the page meets its
// install criteria, the check Android Chrome makes before offering to install it.
test("Chrome finds nothing stopping the site being installed", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "only Chromium says why a page can't be installed");
  await page.goto("/");
  const cdp = await page.context().newCDPSession(page);

  await expect
    .poll(async () => {
      const { installabilityErrors } = await cdp.send("Page.getInstallabilityErrors");
      return installabilityErrors.map((error) => error.errorId);
    })
    .toEqual([]);
  const { url, errors } = await cdp.send("Page.getAppManifest");
  expect(url).toMatch(/\/manifest\.webmanifest$/u);
  expect(errors).toEqual([]);
});
