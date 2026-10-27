import type { Page } from "@playwright/test";

import { expect, test, wcagViolations } from "./fixtures";
import { codeSentTo, logLength, newMobile } from "./sign-in-codes";
import { newStaff, signInAsStaff } from "./staff";

// Owners and the owner agreement end to end (BUILD_PLAN 2.6), on phones, against the real API: ops
// add an owner; the owner signs in with their phone, reads the agreement and accepts it, with
// nothing ticked for them; ops see the acceptance, with when, from where and in which browser.

/** Sign in by phone: the number, the code the API "sent", and agreeing to the privacy notice. */
async function signInByPhone(page: Page, mobile: string) {
  await page.getByLabel("Mobile number", { exact: true }).fill(mobile);
  const from = await logLength();
  await page.getByRole("button", { name: "Send code" }).click();
  await page
    .getByLabel("Six-digit code", { exact: true })
    .fill(await codeSentTo(mobile, { after: from }));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Before we create your account" })).toBeVisible();
  await page.getByRole("checkbox", { name: /^I agree/ }).check();
  await page.getByRole("button", { name: "Agree and continue" }).click();
}

test.describe("owner agreement", () => {
  // A first sign-in is refused until consent is given (400 CONSENT_REQUIRED), by design.
  test.use({ expectedConsoleErrors: [/status of 400/] });

  test("an owner accepts the agreement they read, and ops see the acceptance", async ({
    page,
    browser,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "phone", "one run is enough, and phones are the hard case");
    // Two sign-ins.
    test.slow();
    const staff = await newStaff(["ops"]);

    await page.goto("/ops/owners");
    await signInAsStaff(page, staff);
    await expect(page).toHaveURL(/\/ops\/owners$/);
    await expect(page.getByRole("heading", { name: "Owners", level: 1 })).toBeVisible();

    // Ops add the owner, who has never signed in.
    const mobile = newMobile();
    await page.getByLabel("Owner's mobile number", { exact: true }).fill(mobile);
    await page.getByLabel("Owner's own name (optional)", { exact: true }).fill("A Fictional Owner");
    await page.getByLabel("Legal name", { exact: true }).fill("Fictional Homes LLP");
    await page.getByLabel("Business name", { exact: true }).fill("Fictional Homes");
    await page.getByRole("button", { name: "Add the owner" }).click();
    await expect(page.getByRole("heading", { name: "Fictional Homes", level: 1 })).toBeVisible();
    await expect(page.getByText(/^Hasn't accepted the owner agreement yet/)).toBeVisible();
    await expect(page.getByText("No acceptances yet.")).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    // The owner, on their own phone: the agreement comes before anything else.
    const phone = await browser.newContext({ ...testInfo.project.use });
    const owner = await phone.newPage();
    await owner.goto("/owner");
    await expect(owner).toHaveURL(/\/sign-in\?next=%2Fowner$/);
    await signInByPhone(owner, mobile);
    await expect(owner).toHaveURL(/\/owner\/agreement$/);
    await expect(owner.getByRole("heading", { name: "Owner agreement", level: 1 })).toBeVisible();
    // The owner area stays out of search engines.
    await expect(owner.locator('meta[name="robots"]')).toHaveAttribute(
      "content",
      "noindex, nofollow",
    );
    await expect(owner.getByText(/^This is a draft for discussion/)).toBeVisible();
    await expect(owner.getByRole("heading", { name: "2. The placement fee" })).toBeVisible();
    const box = owner.getByRole("checkbox", { name: /^I've read this owner agreement/ });
    await expect(box).not.toBeChecked();
    expect(await wcagViolations(owner)).toEqual([]);
    await owner.getByRole("button", { name: "Accept the agreement" }).click();
    await expect(owner.getByText("Tick the box to accept the agreement.")).toBeVisible();
    await box.check();
    await owner.getByRole("button", { name: "Accept the agreement" }).click();
    await expect(owner).toHaveURL(/\/owner$/);
    await expect(owner.getByRole("heading", { name: "Fictional Homes", level: 1 })).toBeVisible();
    await expect(
      owner.getByText("You've accepted version draft-1 of the owner agreement."),
    ).toBeVisible();
    expect(await wcagViolations(owner)).toEqual([]);
    const browserName = await owner.evaluate(() => navigator.userAgent);
    await phone.close();

    // Ops see what was accepted, when, from where and in which browser.
    await page.reload();
    await expect(
      page.getByText("Accepted the current owner agreement (version draft-1)."),
    ).toBeVisible();
    const acceptance = page.getByRole("list", { name: "Acceptances, newest first" });
    await expect(acceptance.getByRole("listitem")).toHaveCount(1);
    await expect(acceptance).toContainText("draft-1");
    await expect(acceptance).toContainText(browserName);
    await expect(acceptance).toContainText(/[0-9a-f]{64}/u);
    expect(await wcagViolations(page)).toEqual([]);
  });
});
