import { expect, test, wcagViolations } from "./fixtures";
import { newStaff, signInAsStaff } from "./staff";

// The staff dashboard (the console's home): what needs a person now, and twelve weeks of visits,
// tokens and fees, each chart with its numbers as a table too.

test.describe("the staff dashboard", () => {
  // Staff sign in by phone first, refused until consent is given (400).
  test.use({ expectedConsoleErrors: [/status of 400/] });

  test("ops see the business at a glance, and every chart's numbers", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough; staff work at a desk");
    const ops = await newStaff(["ops"]);
    await page.goto("/ops");
    await signInAsStaff(page, ops);

    await expect(page).toHaveURL(/\/ops$/u);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("The business at a glance");
    await expect(page.getByRole("img", { name: "Visits asked for" })).toBeVisible();
    await expect(page.getByRole("img", { name: "Tokens secured" })).toBeVisible();
    await page.getByText("See the numbers").first().click();
    await expect(page.getByRole("columnheader", { name: "Week of" }).first()).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);
  });
});
