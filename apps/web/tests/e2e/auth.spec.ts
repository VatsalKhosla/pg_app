import type { Page } from "@playwright/test";

import { expect, test, wcagViolations } from "./fixtures";
import { codeSentTo, logLength, newMobile } from "./sign-in-codes";

// Signing in end to end, against the real API (scripts/e2e-api.sh): BUILD_PLAN 1.6's done
// criterion is login, logout and protected-route redirects on a phone.

/** Ask for a code for `mobile` and type in the one the API "sent". */
async function enterNumberAndCode(page: Page, mobile: string) {
  await page.getByLabel("Mobile number", { exact: true }).fill(mobile);
  const from = await logLength();
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByRole("heading", { name: "Enter the code" })).toBeVisible();
  await page
    .getByLabel("Six-digit code", { exact: true })
    .fill(await codeSentTo(mobile, { after: from }));
  await page.getByRole("button", { name: "Continue" }).click();
}

/** A new person signs up: consent, then their name. Ends on the account page. */
async function signUp(page: Page, mobile: string) {
  await page.goto("/sign-in?next=/account");
  await enterNumberAndCode(page, mobile);
  await expect(page.getByRole("heading", { name: "Before we create your account" })).toBeVisible();
  await page.getByRole("checkbox", { name: /^I agree/ }).check();
  await page.getByRole("button", { name: "Agree and continue" }).click();
  await expect(page.getByRole("heading", { name: "About you" })).toBeVisible();
  await page.getByLabel("Your name", { exact: true }).fill("Asha Test");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page).toHaveURL(/\/account$/);
}

test.describe("signing in", () => {
  // A first sign-in is refused until consent is given (400 CONSENT_REQUIRED), and a new code
  // within 30 seconds of the last is refused too (429 OTP_RESEND_TOO_SOON), both by design; the
  // browser logs any 4xx answer to a fetch.
  // One pattern: test.use reads [value, object] as a value and its fixture options.
  test.use({ expectedConsoleErrors: [/status of (400|429)/] });

  test("a protected page sends people to sign in, and back to it afterwards", async ({ page }) => {
    await page.goto("/account");

    await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
    await expect(page.getByRole("heading", { name: "Sign in or create an account" })).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);
  });

  test("a new person agrees, nothing ticked for them, then signs out", async ({ page }) => {
    await page.goto("/sign-in?next=/account");
    await enterNumberAndCode(page, newMobile());

    await expect(
      page.getByRole("heading", { name: "Before we create your account" }),
    ).toBeVisible();
    await expect(page.getByRole("checkbox", { name: /^I agree/ })).not.toBeChecked();
    await expect(page.getByRole("checkbox", { name: /^Send me offers/ })).not.toBeChecked();
    expect(await wcagViolations(page)).toEqual([]);
    await page.getByRole("checkbox", { name: /^I agree/ }).check();
    await page.getByRole("button", { name: "Agree and continue" }).click();
    await page.getByLabel("Your name", { exact: true }).fill("Asha Test");
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
    await expect(page.getByLabel("Your name", { exact: true })).toHaveValue("Asha Test");
    await expect(
      page.getByRole("banner").getByRole("link", { name: "Your account" }),
    ).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toBeVisible();
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);
  });

  test("someone with an account goes straight back, once the resend wait is over", async ({
    page,
  }) => {
    // The API sends a number a new code at most every 30 seconds, and this waits that out.
    test.slow();
    const mobile = newMobile();
    const firstCode = Date.now();
    await signUp(page, mobile);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/$/);
    await page.goto("/account");
    await expect(page).toHaveURL(/\/sign-in\?next=%2Faccount$/);

    await page.getByLabel("Mobile number", { exact: true }).fill(mobile);
    await page.getByRole("button", { name: "Send code" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toHaveText(
      "Please wait a few seconds before asking for another code.",
    );
    await page.waitForTimeout(Math.max(0, firstCode + 31_000 - Date.now()));
    await enterNumberAndCode(page, mobile);

    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByLabel("Your name", { exact: true })).toHaveValue("Asha Test");
  });
});

test.describe("staff sign-in", () => {
  test("staff pages send everyone without a staff session to the staff sign-in", async ({
    page,
  }) => {
    await page.goto("/staff");

    await expect(page).toHaveURL(/\/staff\/sign-in\?next=%2Fstaff$/);
    await expect(page.getByRole("heading", { name: "Staff sign-in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      /\/v1\/auth\/staff\/google$/,
    );
    expect(await wcagViolations(page)).toEqual([]);
  });

  test("a refused Google account comes back with the reason", async ({ page }) => {
    await page.goto("/staff/sign-in?error=STAFF_ACCOUNT_NOT_ALLOWED");

    // Inside main: Next.js announces route changes in a role="alert" element of its own.
    await expect(page.getByRole("main").getByRole("alert")).toHaveText(
      /That Google account can't sign in to staff tools/,
    );
  });
});
