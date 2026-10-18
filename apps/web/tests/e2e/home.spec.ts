import { expect, test, wcagViolations } from "./fixtures";

test("the home page introduces the service", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("YourBrand · Verified PG beds in Delhi NCR");
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
    page.getByRole("banner").getByRole("link", { name: "YourBrand", exact: true }),
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
