import { expect, test, wcagViolations } from "./fixtures";
import { newMobile } from "./sign-in-codes";
import { newStaff, signInAsStaff } from "./staff";

// Importing owners and their PGs from the template (ADR 0072), against the real API: ops download
// the template, check a file (which makes nothing), import it, and find the draft it made. Every
// name and number is fictional.

test.describe("importing owners and PGs", () => {
  test("ops check a file, import it, and open the draft it made", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough: a desktop task");
    const staff = await newStaff(["ops"]);
    await page.goto("/ops/listings/import");
    await signInAsStaff(page, staff);
    await expect(
      page.getByRole("heading", { name: "Import owners and PGs", level: 1 }),
    ).toBeVisible();

    // The template, with its fictional PG made unique to this run.
    const download = await page.request.get("/ops/listings/import/template");
    expect(download.headers()["content-type"]).toContain("text/csv");
    const mobile = newMobile();
    const name = `Fictional Import House ${mobile.slice(-4)}`;
    const file = (await download.text())
      .replaceAll("98765 43210", mobile)
      .replaceAll("Fictional Sample House", name);
    await page.getByLabel("Or paste it here").fill(file);

    await page.getByRole("button", { name: "Check the file" }).click();
    await expect(page.getByRole("heading", { name: "What an import would make" })).toBeVisible();
    await expect(page.getByText("New owner")).toBeVisible();
    await expect(page.getByText("Draft listing, 2 room types")).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    await page.getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByRole("heading", { name: "What the import made" })).toBeVisible();
    await page.getByRole("link", { name }).click();
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  });
});
