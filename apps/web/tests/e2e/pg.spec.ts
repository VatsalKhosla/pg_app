import { formatINR } from "../../src/lib/money";
import { expect, test, wcagViolations } from "./fixtures";
import { manage } from "./staff";

// A PG's page end to end (BUILD_PLAN 3.4), against the real API with its fictional sample PGs
// (python -m app.manage catalog samples): every room's rent, deposit and charges as the API has
// them, nothing hidden, the safety summary, where it is roughly, and the way to book a visit.

const SLUG = "fictional-sample-pg-aster-kamla-nagar";
const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;

interface Charge {
  type: "monthly" | "metered" | "oneTime";
  label: string;
  amountPaise?: number;
  ratePaise?: number;
  unit?: string;
  monthlyEstimatePaise?: number;
}

interface Category {
  label: string;
  baseRentPaise: number;
  securityDepositPaise: number;
  mandatoryCharges: Charge[];
  monthlyChargesPaise: number;
  oneTimeChargesPaise: number;
}

/** How the page words a charge (messages/en-IN.json, Pg.rooms). */
function said(charge: Charge): string {
  switch (charge.type) {
    case "monthly":
      return `${charge.label}: ${formatINR(charge.amountPaise ?? 0)} a month`;
    case "metered":
      return `${charge.label}: ${formatINR(charge.ratePaise ?? 0)} per ${charge.unit ?? ""}, about ${formatINR(charge.monthlyEstimatePaise ?? 0)} a month`;
    case "oneTime":
      return `${charge.label}: ${formatINR(charge.amountPaise ?? 0)}, once`;
  }
}

// A transparent 1×1 PNG for every map tile, as in ops.spec.ts.
const BLANK_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgYGBgAAAABQABeqhXUAAAAABJRU5ErkJggg==",
  "base64",
);

test.describe("PG page", () => {
  test.beforeAll(async () => {
    // Once is enough: a second run finds them there and adds nothing.
    await manage(["catalog", "samples"]);
  });

  test("shows every room's rent, deposit and charges upfront, safety and where it is", async ({
    page,
    request,
  }) => {
    await page.route("https://tile.openstreetmap.org/**", (route) =>
      route.fulfill({ contentType: "image/png", body: BLANK_TILE }),
    );
    const listing = (await (await request.get(`${API}/v1/properties/${SLUG}`)).json()) as {
      name: string;
      categories: Category[];
    };

    await page.goto(`/pg/${SLUG}`);

    await expect(page.getByRole("heading", { name: listing.name, level: 1 })).toBeVisible();
    await expect(page.getByText("Verified by our field agent")).toBeVisible();
    // Public, so search engines may index it (unlike the owner, ops and account pages).
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).toHaveCount(0);
    const rooms = page.getByRole("region", { name: "Rooms and prices" });
    expect(listing.categories.length).toBeGreaterThan(0);
    for (const category of listing.categories) {
      const card = rooms.getByRole("listitem").filter({
        has: page.getByRole("heading", { name: category.label, exact: true }),
      });
      await expect(card.getByText(`${formatINR(category.baseRentPaise)} a month`)).toBeVisible();
      await expect(
        card.getByText(`Security deposit: ${formatINR(category.securityDepositPaise)}`),
      ).toBeVisible();
      for (const charge of category.mandatoryCharges) {
        await expect(card.getByText(said(charge), { exact: true })).toBeVisible();
      }
      await expect(
        card.getByText(
          `Other charges come to about ${formatINR(category.monthlyChargesPaise)} a month, and ${formatINR(category.oneTimeChargesPaise)} once.`,
        ),
      ).toBeVisible();
    }
    await expect(page.getByText(/^Checked by our field agent on /)).toBeVisible();
    const where = page.getByRole("region", { name: "Where it is" });
    await expect(where.getByText(/^In Kamla Nagar, within about 150 m/)).toBeVisible();
    await expect(where.getByRole("heading", { name: "Campuses nearby" })).toBeVisible();
    await where.scrollIntoViewIfNeeded();
    await expect(where.locator(".maplibregl-canvas")).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    // Booking a visit needs signing in first, and comes back to it (step 3.7).
    await page.getByRole("link", { name: "Book a visit" }).first().click();
    await expect(page).toHaveURL(
      new RegExp(`/sign-in\\?next=${encodeURIComponent(`/pg/${SLUG}/visit`)}$`),
    );
  });
});

test.describe("a PG the public can't see", () => {
  // The browser reports the 404 answer as a console error, by design.
  test.use({ expectedConsoleErrors: [/status of 404/] });

  test("isn't there", async ({ page }) => {
    const response = await page.goto("/pg/no-such-pg-anywhere");

    expect(response?.status()).toBe(404);
  });
});
