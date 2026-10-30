import { expect, test, wcagViolations } from "./fixtures";
import { opsWithListing } from "./ops-api";

// A PG's beds over time (BUILD_PLAN 5.1, ADR 0044), against the real API: ops hold a bed for
// maintenance, see it taken from the free count, then end it. Each run has a listing of its own.

/** Today in India, YYYY-MM-DD, and days after it. */
function day(offset = 0): string {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const [year, month, date] = today.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(year, month - 1, date + offset)).toISOString().slice(0, 10);
}

test.describe("a PG's beds", () => {
  // The first sign-in is refused until consent is given (400 CONSENT_REQUIRED), by design.
  test.use({ expectedConsoleErrors: [/status of 400/] });

  test("ops hold a bed for maintenance and end it", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough; inventory is desk work");
    test.slow();
    const { listing } = await opsWithListing(page, `Fictional Beds PG ${String(Date.now())}`, {
      beds: 2,
    });

    await page.goto(`/ops/listings/${listing.id}`);
    await page.getByRole("link", { name: "Open the beds" }).click();
    await expect(page).toHaveURL(new RegExp(`/ops/listings/${listing.id}/beds$`, "u"));
    const room = page.getByRole("region", { name: "Twin sharing" });
    await expect(room.getByText(/^2 of 2 beds free for all of /u)).toBeVisible();

    const hold = page.getByRole("form", { name: "Hold a bed" });
    await hold.getByLabel("Bed", { exact: true }).selectOption({ index: 1 });
    await hold.getByLabel("Maintenance").check();
    await hold.getByLabel("From", { exact: true }).fill(day());
    await hold.getByLabel("Free again from (optional)").fill(day(5));
    await hold.getByLabel("Note (optional)").fill("Repainting.");
    await hold.getByRole("button", { name: "Hold the bed" }).click();
    await expect(hold.getByRole("status")).toHaveText("Held.");
    await expect(room.getByText(/^1 of 2 beds free for all of /u)).toBeVisible();
    await expect(room.getByText(/ · Repainting\.$/u)).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    // Ending it on its first day cancels it: both beds free again.
    const end = room.getByRole("form", { name: /^End: Maintenance, bed / });
    await end.getByLabel("Free from").fill(day());
    await end.getByRole("button", { name: "End" }).click();
    await expect(room.getByText(/^2 of 2 beds free for all of /u)).toBeVisible();
    await expect(room.getByText(/ · Repainting\.$/u)).toHaveCount(0);
  });
});
