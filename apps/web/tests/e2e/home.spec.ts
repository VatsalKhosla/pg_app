import { expect, test, wcagViolations } from "./fixtures";

test("the home page introduces the service", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("Fix Your Stay · Verified PG beds in Delhi NCR");
  await expect(page.locator("html")).toHaveAttribute("lang", "en-IN");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Verified PG beds in Delhi NCR");
  await expect(page.getByText("Coming soon")).toBeVisible();
  await expect(page.getByRole("heading", { name: "How it works" })).toBeVisible();
  await expect(page.locator('meta[name="description"]')).toHaveAttribute(
    "content",
    /verified PG bed/,
  );
});

test("the page has a banner, main content and a footer", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("contentinfo")).toBeVisible();
  await expect(
    page.getByRole("banner").getByRole("link", { name: "Fix Your Stay", exact: true }),
  ).toHaveAttribute("href", "/");
});

test("the home page meets WCAG 2.2 AA", async ({ page }) => {
  await page.goto("/");

  expect(await wcagViolations(page)).toEqual([]);
});

test.describe("in dark mode", () => {
  test.use({ colorScheme: "dark" });

  test("the home page meets WCAG 2.2 AA", async ({ page }) => {
    await page.goto("/");

    expect(await wcagViolations(page)).toEqual([]);
  });
});

test("the home page streams in the API's status, asked through the typed client", async ({
  page,
}) => {
  await page.goto("/");

  // Browser tests run without the API unless one happens to be up locally.
  await expect(page.getByText(/^Service status: (Online|Unavailable)$/)).toBeVisible();
});

test("the search over the hero goes to search with what was chosen, and nothing else", async ({
  page,
}) => {
  await page.goto("/");

  await page.getByLabel("Budget").selectOption({ label: "Up to ₹10,000" });
  await page.getByRole("button", { name: "Find PGs" }).click();

  await expect(page).toHaveURL(/\/search\?budget_max_paise=1000000$/);
});

test.describe("for someone who has asked for less motion", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("the evening scene holds still", async ({ page }) => {
    await page.goto("/");

    const moving = await page
      .locator(".dusk-scene")
      .evaluate((scene) => scene.getAnimations({ subtree: true }).length);
    expect(moving).toBe(0);
  });
});
