import type { APIRequestContext, Page } from "@playwright/test";

import { formatINR } from "../../src/lib/money";
import { priceLabel } from "../../src/lib/search/labels";
import { expect, test, wcagViolations } from "./fixtures";
import { manage } from "./staff";

// Search and its map end to end (BUILD_PLAN 3.5), on a phone and a desktop, against the real API
// with its fictional sample PGs: filter, move the map, pick a pin and open the PG's page. On a
// phone the map's code isn't even fetched until the map is asked for.

const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;
const ASTER = "fictional-sample-pg-aster-kamla-nagar";

// A transparent 1×1 PNG for every map tile, as in ops.spec.ts.
const BLANK_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgYGBgAAAABQABeqhXUAAAAABJRU5ErkJggg==",
  "base64",
);

interface Card {
  id: string;
  slug: string;
  name: string;
  minRentPaise: number;
  maxRentPaise: number;
}

/** Aster, as search finds it among girls' PGs near Hindu College, once the worker has it. */
async function findAster(request: APIRequestContext): Promise<Card | undefined> {
  const response = await request.get(`${API}/v1/search/properties`, {
    params: { gender: "girls", campus: "hindu-college" },
  });
  const page = (await response.json()) as { items: Card[] };
  return page.items.find((card) => card.slug === ASTER);
}

/** The scripts the page fetched that are MapLibre's: its class names are in no other code. */
function mapScripts(page: Page): { found: string[]; settled: () => Promise<unknown> } {
  const found: string[] = [];
  const reading: Promise<unknown>[] = [];
  page.on("response", (response) => {
    if (response.request().resourceType() !== "script") return;
    reading.push(
      response
        .text()
        .then((body) => {
          if (body.includes("maplibregl-canvas")) found.push(response.url());
        })
        .catch(() => undefined),
    );
  });
  return { found, settled: () => Promise.all(reading) };
}

test.describe("search", () => {
  let aster: Card;

  test.beforeAll(async ({ request }) => {
    // Once is enough: a second run waits for the first, then adds nothing.
    await manage(["catalog", "samples"]);
    // Search's read model follows the catalog through the worker, within moments.
    await expect.poll(() => findAster(request), { timeout: 30_000 }).toBeDefined();
    const found = await findAster(request);
    if (found === undefined) throw new Error("search doesn't find the sample PG Aster");
    aster = found;
  });

  test("filter, move the map, pick a pin and open its PG", async ({ page, isMobile }) => {
    await page.route("https://tile.openstreetmap.org/**", (route) =>
      route.fulfill({ contentType: "image/png", body: BLANK_TILE }),
    );
    const scripts = mapScripts(page);

    await page.goto("/search");
    // Public, so search engines may index it.
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).toHaveCount(0);
    await expect(page.locator('a[href^="/pg/"]').first()).toBeVisible();

    // Filter: girls' PGs near Hindu College. Each choice goes into the URL.
    await page.getByRole("button", { name: "Filters" }).first().click();
    const filters = page.getByRole("dialog", { name: "Filters" });
    await filters.getByLabel("Near a campus").selectOption({ label: "Hindu College" });
    await filters.getByLabel("Who it's for").selectOption({ label: "Girls" });
    await filters.getByRole("button", { name: "Show PGs" }).click();
    await expect(filters).toBeHidden();
    await expect(page).toHaveURL(/campus=hindu-college/);
    await expect(page).toHaveURL(/gender=girls/);
    const asterCard = page.getByRole("link", { name: /Fictional Sample PG Aster/ });
    await expect(asterCard).toBeVisible();
    await expect(asterCard.getByText(/from the campus$/)).toBeVisible();
    // A girls' PG near another campus is gone, and so are the boys' PGs nearby.
    await expect(page.getByRole("link", { name: /Fictional Sample PG Deodar/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Fictional Sample PG Banyan/ })).toHaveCount(0);
    expect(await wcagViolations(page)).toEqual([]);

    if (isMobile) {
      // The list comes first on a phone, and the map's code waits until the map is opened.
      await page.waitForLoadState("networkidle");
      await scripts.settled();
      expect(scripts.found).toEqual([]);
      await page.getByRole("button", { name: "Show the map" }).click();
      await expect(page).toHaveURL(/view=map/);
    }
    const map = page.locator(".maplibregl-canvas");
    await expect(map).toBeVisible();
    await expect.poll(() => scripts.found.length).toBeGreaterThan(0);
    const pin = page.locator(`[data-pin-id="${aster.id}"]`);
    await expect(pin).toBeVisible();
    // Named by what it shows first, then the full prices and who it's for.
    await expect(pin).toHaveAccessibleName(
      `${priceLabel(aster.minRentPaise, aster.maxRentPaise)}, ${formatINR(aster.minRentPaise)} to ${formatINR(aster.maxRentPaise)} a month, Girls, verified`,
    );

    if (!isMobile) {
      // A card and its pin light up together.
      await asterCard.hover();
      await expect(pin).toHaveAttribute("data-state", "active");
    }

    // Move the map: the search follows it, as its area instead of the campus.
    if (isMobile) {
      // One finger scrolls the page past the map, so here the arrow keys move it.
      await map.focus();
      await page.keyboard.press("ArrowRight");
    } else {
      const box = await map.boundingBox();
      if (box === null) throw new Error("the map has no box");
      await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.7);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.65, { steps: 8 });
      await page.mouse.up();
    }
    await expect(page).toHaveURL(/bbox=/);
    await expect(page).not.toHaveURL(/campus=/);
    await expect(page).toHaveURL(/gender=girls/);
    if (isMobile) {
      // The list sits in a sheet over the map; its handle opens it without dragging.
      await page.getByRole("button", { name: "Show more of the list" }).click();
      await expect(page.getByRole("link", { name: /Fictional Sample PG Aster/ })).toBeVisible();
      await page.getByRole("button", { name: "Show more of the list" }).click();
      await page.getByRole("button", { name: "Show less of the list" }).click();
    } else {
      await expect(page.getByText("Searching the map's area")).toBeVisible();
    }

    // Pick the pin: its PG comes up over the map, and leads to its page.
    await pin.click();
    await expect(pin).toHaveAttribute("aria-pressed", "true");
    const preview = page.getByRole("region", { name: "Fictional Sample PG Aster" });
    await expect(preview).toBeFocused();
    await expect(
      preview.getByText(
        `${formatINR(aster.minRentPaise)} to ${formatINR(aster.maxRentPaise)} a month`,
      ),
    ).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);
    await preview.getByRole("link", { name: "See the PG" }).click();

    await expect(
      page.getByRole("heading", { level: 1, name: "Fictional Sample PG Aster" }),
    ).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/pg/${ASTER}$`));
  });

  test("a shared link shows the same search", async ({ page }) => {
    const response = await page.goto("/search?gender=girls&campus=hindu-college&sort=price_asc");

    expect(response?.status()).toBe(200);
    // The first page of results is in the HTML, before any script has run.
    expect(await response?.text()).toContain("Fictional Sample PG Aster");
    await expect(page.getByRole("link", { name: /Fictional Sample PG Aster/ })).toBeVisible();
    await expect(page.getByLabel("Sort by")).toHaveValue("price_asc");
  });

  test("says when nothing matches, and clears the filters", async ({ page }) => {
    await page.goto("/search?q=no-such-pg-anywhere-at-all");

    await expect(page.getByText("No PG matches all of that yet.")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();

    await expect(page.locator('a[href^="/pg/"]').first()).toBeVisible();
    await expect(page.getByText("No PG matches all of that yet.")).toBeHidden();
    await expect(page).not.toHaveURL(/q=/);
  });
});
