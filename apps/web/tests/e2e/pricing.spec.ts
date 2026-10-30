import { expect, test, wcagViolations } from "./fixtures";
import { newMobile } from "./sign-in-codes";
import { newStaff, signInAsStaff } from "./staff";

// The pricing editor end to end (BUILD_PLAN 4.6, ADR 0041), against the real API: ops draft a
// rule, see what a student would be quoted and the weeks it moves, and put it in force once
// they confirm. Each run prices a listing of its own, so runs and other tests never meet.

const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;
const SHORT = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
const LONG = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** Today in India and the days after it, as UTC dates (YYYY-MM-DD when printed). */
function daysFromToday(days: number): Date {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const [year, month, day] = today.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(year, month - 1, day + days));
}

function iso(day: Date): string {
  return day.toISOString().slice(0, 10);
}

test.describe("the pricing editor", () => {
  // The first sign-in is refused until consent is given (400 CONSENT_REQUIRED), by design.
  test.use({ expectedConsoleErrors: [/status of 400/] });

  test("drafts a rule, previews a move-in, charts the weeks and puts it in force", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough; pricing is desk work");
    test.slow();
    const ops = await newStaff(["ops"]);
    await page.goto("/ops");
    await signInAsStaff(page, ops);
    await expect(page).toHaveURL(/\/ops\/listings$/u);
    const csrf = (await page.context().cookies(API)).find(
      (cookie) => cookie.name === "__Secure-csrf",
    )?.value;
    if (csrf === undefined) throw new Error("no CSRF cookie after signing in");
    const post = async (path: string, data: object) => {
      const response = await page.request.post(`${API}${path}`, {
        data,
        headers: { "X-CSRF-Token": csrf },
      });
      expect(response.ok(), `${path}: ${String(response.status())}`).toBe(true);
      return (await response.json()) as { id: string };
    };
    const owner = await post("/v1/ops/owners", {
      phone: newMobile(),
      legalName: "Fictional Pricing Stays Private Limited",
      businessName: "Fictional Pricing Stays",
    });
    const listing = await post("/v1/ops/properties", {
      owner: owner.id,
      locality: "kamla-nagar",
      name: `Fictional Priced PG ${String(Date.now())}`,
      addressLine: "House 9, a fictional lane",
      location: { lat: 28.688, lng: 77.21 },
      locationPrecision: "exact",
      genderPolicy: "girls",
      meals: "two",
    });
    await post(`/v1/ops/properties/${listing.id}/room-categories`, {
      occupancy: "double",
      label: "Twin sharing",
      baseRentPaise: 1_000_000,
      securityDepositPaise: 1_000_000,
    });

    // From the listing to its editor, with nothing priced yet.
    await page.goto(`/ops/listings/${listing.id}`);
    await page.getByRole("link", { name: "Open the pricing editor" }).click();
    await expect(page).toHaveURL(new RegExp(`/ops/listings/${listing.id}/pricing$`, "u"));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Pricing");
    await expect(page.getByText(/^No rules yet/u)).toBeVisible();
    const market = page.getByRole("region", { name: "What the rents sit beside" });
    await expect(market.getByText("₹10,000", { exact: true })).toBeVisible();

    // A draft with a two-week peak, four weeks from now.
    await page.getByRole("button", { name: "Start a draft" }).click();
    await expect(page).toHaveURL(/\?version=/u);
    await page.getByRole("button", { name: "Add a rule" }).click();
    const form = page.getByRole("form", { name: "Add a rule" });
    const first = daysFromToday(28);
    const last = daysFromToday(41);
    await form.getByLabel("Kind of rule").selectOption("season");
    await form.getByLabel("What students see").fill("Peak season");
    for (const [name, day] of [
      ["First day", first],
      ["Last day", last],
    ] as const) {
      const group = form.getByRole("group", { name });
      await group.getByLabel("Month").selectOption(String(day.getUTCMonth() + 1));
      await group.getByLabel("Day").fill(String(day.getUTCDate()));
    }
    await form.getByLabel("By, %").fill("15");
    await form.getByRole("button", { name: "Save the rule" }).click();
    const rules = page.getByRole("region", { name: /^Rules/u });
    await expect(
      rules.getByText(
        `+15% for move-ins from ${SHORT.format(first)} to ${SHORT.format(last)}, every year`,
      ),
    ).toBeVisible();
    await expect(page.getByText("Nothing stops it: it can go into force.")).toBeVisible();

    // What a student asking today would be quoted, the owner's fee beside it.
    const preview = page.getByRole("region", { name: "Try a move-in" });
    await preview.getByLabel("Move-in").fill(iso(daysFromToday(30)));
    await expect(preview.getByText("₹11,500 a month, fixed for the whole stay")).toBeVisible();
    await expect(
      preview.getByText("Base ₹10,000 · Peak season +15% = ₹11,500/month, fixed for your stay"),
    ).toBeVisible();
    await expect(preview.getByText(/^Placement fee: ₹3,000 \+ GST ₹540 = ₹3,540/u)).toBeVisible();
    await preview.getByLabel("Move-in").fill(iso(daysFromToday(200)));
    await expect(
      preview.getByText(`Students can quote this move-in from ${LONG.format(daysFromToday(80))}.`),
    ).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    // The weeks: the peak's two at ₹11,500, the rest at the listed rent, in the table too.
    const chart = page.getByRole("region", { name: "Rent by move-in week" });
    await chart.getByText("Show the weeks as a table").click();
    const rows = chart.getByRole("row").filter({ has: page.getByRole("rowheader") });
    await expect(rows).toHaveCount(12);
    const rents = await rows.getByRole("cell").filter({ hasText: /^₹/u }).allTextContents();
    expect(rents).toEqual(
      Array.from({ length: 12 }, (_, week) => (week === 4 || week === 5 ? "₹11,500" : "₹10,000")),
    );
    const plot = chart.getByRole("group", {
      name: "Twin sharing: rent a month for each week's move-in",
    });
    await plot.focus();
    await page.keyboard.press("Home");
    for (let week = 0; week < 4; week += 1) await page.keyboard.press("ArrowRight");
    await expect(chart.getByText(/: ₹11,500 a month\./u)).toHaveCount(1);

    // In force once confirmed; a version that has been in force never changes.
    await page.getByRole("button", { name: "Put in force…" }).click();
    const confirm = page.getByRole("region", { name: "Put version 1 in force?" });
    await expect(confirm.getByRole("heading")).toBeFocused();
    await expect(confirm.getByText(/^It goes into force from now/u)).toBeVisible();
    await confirm.getByLabel("Why it's changing (optional)").fill("A browser test's peak.");
    await confirm.getByRole("button", { name: "Put it in force now" }).click();
    const versions = page.getByRole("list", { name: "Versions of the pricing rules" });
    await expect(versions.getByText(/^In force · since /u)).toBeVisible();
    await expect(page.getByText(/^A version that has been in force never changes/u)).toBeVisible();
    await expect(page.getByRole("button", { name: "Start a draft" })).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);
  });
});
