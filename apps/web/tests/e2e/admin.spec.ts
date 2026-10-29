import { expect, test, wcagViolations } from "./fixtures";
import { newStaff, signInAsStaff } from "./staff";

// The admin console (BUILD_PLAN 4.1): admins change a policy, each change a new version in force
// from now, and set and end rent bands; other staff can't open it. Written to run again and again
// on the same database: it moves the premium cap between two values and ends the band it sets.

test.describe("the admin console", () => {
  // Staff sign in by phone first, refused until consent is given (400); the token above
  // ₹2,000 is refused too (422).
  test.use({ expectedConsoleErrors: [/status of (400|422)/] });

  test("an admin changes a cap, is refused a token above ₹2,000, and sets and ends a band", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough; admins work at a desk");
    test.slow();
    const admin = await newStaff(["admin"], "Test Admin");
    await page.goto("/admin/policies");
    await signInAsStaff(page, admin);
    await expect(page).toHaveURL(/\/admin\/policies$/u);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Policies");
    expect(await wcagViolations(page)).toEqual([]);

    // The premium cap, applied from now.
    const caps = page.getByRole("region", { name: "Caps on dynamic prices" });
    const premium = caps.getByLabel("Highest premium, % above the listed rent");
    const next = (await premium.inputValue()) === "40" ? "35" : "40";
    await premium.fill(next);
    await caps.getByLabel("Why it's changing (optional)").fill("A browser test's change.");
    await caps.getByRole("button", { name: "Apply from now" }).click();
    await expect(caps.getByRole("status")).toHaveText("Applied: in force from now.");
    await expect(caps.getByText(new RegExp(`^\\+${next}% /`, "u"))).toBeVisible();
    await expect(caps.getByText(/set by Test Admin\.$/u)).toBeVisible();

    // The founders' rule: a token from ₹1,000 to ₹2,000.
    const booking = page.getByRole("region", { name: "Booking terms" });
    await booking.getByLabel("Token, ₹").fill("2500");
    await booking.getByRole("button", { name: "Apply from now" }).click();
    await expect(booking.getByRole("alert")).toContainText(
      "the token must be from ₹1,000 to ₹2,000",
    );

    // A rent band, then no band.
    await page.getByRole("link", { name: "Rent bands" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Rent bands");
    const form = page.getByRole("region", { name: "Set a band" });
    await form.getByLabel("Locality").selectOption({ label: "Kamla Nagar" });
    await form.getByLabel("Occupancy").selectOption({ label: "Single" });
    await form.getByLabel("Lowest monthly rent, ₹").fill("7000");
    await form.getByLabel("Highest monthly rent, ₹").fill("12000");
    await form.getByRole("button", { name: "Set from now" }).click();
    await expect(form.getByRole("status")).toHaveText("Set: in force from now.");
    const band = page.getByRole("listitem").filter({ hasText: "Kamla Nagar, Single" });
    await expect(band).toContainText("₹7,000 to ₹12,000 a month");
    expect(await wcagViolations(page)).toEqual([]);
    await band.getByRole("button", { name: "End this band: Kamla Nagar, Single" }).click();
    await expect(band).toHaveCount(0);
  });

  test("other staff can't open it", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough");
    const ops = await newStaff(["ops"]);
    await page.goto("/admin/policies");
    await signInAsStaff(page, ops);

    await expect(page).toHaveURL(/\/staff$/u);
  });
});
