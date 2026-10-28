import { expect, test, wcagViolations } from "./fixtures";

// Chrome logs every 404 response to the console; that one is expected here.
test.use({ expectedConsoleErrors: [/status of 404/] });

test("an unknown page answers 404, stays out of search and leads home", async ({ page }) => {
  const response = await page.goto("/no-such-page");

  expect(response?.status()).toBe(404);
  await expect(page).toHaveTitle("Page not found · Fix Your Stay");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex");
  expect(await wcagViolations(page)).toEqual([]);

  await page.getByRole("link", { name: "Go to the home page" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Verified PG beds in Delhi NCR");
});
