import { expect, test, wcagViolations } from "./fixtures";

test("the skip link moves focus past the header to the main content", async ({ page }) => {
  await page.goto("/");

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to content" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();
  await page.keyboard.press("Enter");

  await expect(page.getByRole("main")).toBeFocused();
});

test.describe("on a phone", () => {
  test.beforeEach(({ isMobile }) => {
    test.skip(!isMobile, "the menu replaces the header links on small screens");
  });

  test("the menu opens, meets WCAG 2.2 AA and takes you to a section", async ({ page }) => {
    await page.goto("/");
    const banner = page.getByRole("banner");
    await expect(banner.getByRole("navigation", { name: "Main" })).toBeHidden();

    await page.getByRole("button", { name: "Open menu" }).click();
    const menu = page.getByRole("dialog", { name: "Menu" });
    await expect(menu).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);
    await menu.getByRole("link", { name: "PG owners" }).click();

    await expect(menu).toBeHidden();
    await expect(page).toHaveURL(/\/#owners$/);
    const owners = page.locator("#owners");
    await expect(owners).toBeFocused();
    await expect(owners).toBeInViewport();
  });

  test("Escape closes the menu and returns focus to its button", async ({ page }) => {
    await page.goto("/");
    const button = page.getByRole("button", { name: "Open menu" });

    await button.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");

    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(button).toBeFocused();
  });
});

test.describe("on a desktop", () => {
  test.beforeEach(({ isMobile }) => {
    test.skip(isMobile, "the header shows its links on wide screens");
  });

  test("the header links go to their sections", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Open menu" })).toBeHidden();

    await page
      .getByRole("banner")
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Students and parents" })
      .click();

    await expect(page).toHaveURL(/\/#students$/);
    await expect(page.locator("#students")).toBeInViewport();
  });
});
