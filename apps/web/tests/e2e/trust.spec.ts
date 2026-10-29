import { devices } from "@playwright/test";

import { expect, test, wcagViolations } from "./fixtures";
import { newMobile } from "./sign-in-codes";
import { newStaff, signInAsStaff } from "./staff";

// The trust and legal pages (BUILD_PLAN 3.8): every one linked from the footer, legal texts
// marked as drafts, and a complaint that gets a ticket number, which ops then acknowledge and
// resolve.

const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;

const PAGES = [
  { link: "About us", heading: "About Fix Your Stay", path: "/about" },
  { link: "Contact us", heading: "Contact us", path: "/contact" },
  { link: "Pricing", heading: "Pricing", path: "/pricing" },
  {
    link: "How your token is protected",
    heading: "How your token is protected",
    path: "/token-protection",
  },
  { link: "Terms of use", heading: "Terms of use", path: "/terms", legal: true },
  { link: "Privacy notice", heading: "Privacy notice", path: "/privacy", legal: true },
  {
    link: "Refund and cancellation policy",
    heading: "Refund and cancellation policy",
    path: "/refund-policy",
    legal: true,
  },
  { link: "Grievances", heading: "Grievances", path: "/grievances" },
] as const;

test.describe("the footer", () => {
  for (const { link, heading, path, ...rest } of PAGES) {
    test(`links to ${link}, which meets WCAG 2.2 AA`, async ({ page }) => {
      await page.goto("/");
      await page.getByRole("contentinfo").getByRole("link", { name: link, exact: true }).click();

      await expect(page).toHaveURL(new RegExp(`${path}$`, "u"));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
      if ("legal" in rest) {
        await expect(page.getByRole("note")).toHaveText(/^DRAFT — needs lawyer review/u);
      }
      // Drafts and pages still waiting for the founders' facts stay out of search engines.
      if (path !== "/pricing" && path !== "/token-protection") {
        await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/u);
      }
      expect(await wcagViolations(page)).toEqual([]);
    });
  }
});

test("the pricing and token pages state the API's policies in force", async ({ page, request }) => {
  const policies = (await (await request.get(`${API}/v1/policies`)).json()) as {
    placementFee: { rateBps: number; gstRateBps: number };
    booking: { tokenPaise: number; freeCancelDays: number };
  };
  expect(policies.placementFee.rateBps).toBe(3_000);

  await page.goto("/pricing");
  await expect(page.getByText("30% of one month's listed rent")).toBeVisible();
  await expect(page.getByText("GST at 18% is added to the fee.")).toBeVisible();
  await expect(page.getByText(/refundable token of ₹2,000\./u)).toBeVisible();

  await page.goto("/token-protection");
  await expect(
    page.getByText(
      `Cancel for free up to ${String(policies.booking.freeCancelDays)} days before you move in`,
      { exact: false },
    ),
  ).toBeVisible();
});

test("the privacy notice is the version people consent to", async ({ page, request }) => {
  const { version } = (await (await request.get(`${API}/v1/privacy-notice`)).json()) as {
    version: string;
  };

  await page.goto("/privacy");
  await expect(page.getByText(new RegExp(`^Version ${version},`, "u"))).toBeVisible();
});

test("a complaint gets a ticket number, and ops acknowledge and resolve it", async ({
  page,
  browser,
}, testInfo) => {
  test.skip(testInfo.project.name !== "phone", "one run is enough, and phones are the case");
  test.slow();

  // Someone signed out, on a phone.
  await page.goto("/grievances");
  await page
    .getByLabel("What it's about")
    .selectOption({ label: "A PG's details, photos or price" });
  await page.getByLabel("What happened").fill("The photos showed a window; the room has none.");
  await page.getByLabel("Your name").fill("A Parent");
  await page.getByLabel("Mobile number").fill(newMobile());
  await page.getByRole("button", { name: "Send complaint" }).click();
  const receipt = page.getByRole("status");
  await expect(receipt).toContainText(/Your ticket number is GR-[0-9A-Z]{8}\./u);
  const ticket = /GR-[0-9A-Z]{8}/u.exec((await receipt.textContent()) ?? "")?.[0] ?? "";
  expect(await wcagViolations(page)).toEqual([]);

  // Ops: the queue, then the grievance itself.
  const ops = await newStaff(["ops"]);
  const opsContext = await browser.newContext({ ...devices["Pixel 7"] });
  const opsPage = await opsContext.newPage();
  await opsPage.goto("/ops/grievances");
  await signInAsStaff(opsPage, ops);
  await expect(opsPage.getByRole("heading", { level: 1 })).toHaveText("Grievances");
  await opsPage.goto(`/ops/grievances/${ticket}`);
  await expect(opsPage.getByRole("heading", { level: 1 })).toHaveText(ticket);
  await expect(opsPage.getByText("A Parent · Signed out")).toBeVisible();
  await opsPage.getByLabel("Reply to them").fill("Sorry: our ops lead will call you today.");
  await opsPage.getByRole("button", { name: "Acknowledge" }).click();
  await expect(
    opsPage.getByText("The grievance officer's reply: Sorry: our ops lead will call you today."),
  ).toBeVisible();
  await opsPage.getByLabel("Resolve it").fill("We replaced the listing's photos.");
  await opsPage.getByRole("button", { name: "Resolve" }).click();
  await expect(opsPage.getByText("What we did: We replaced the listing's photos.")).toBeVisible();
  await expect(opsPage.getByRole("button", { name: "Resolve" })).toBeHidden();
  expect(await wcagViolations(opsPage)).toEqual([]);
  await opsContext.close();
});
