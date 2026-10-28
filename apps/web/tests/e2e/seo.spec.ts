import type { APIRequestContext, Page } from "@playwright/test";

import { formatINR } from "../../src/lib/money";
import { rupeesText } from "../../src/lib/seo/json-ld";
import { expect, test, wcagViolations } from "./fixtures";
import { manage, newStaff, signInAsStaff } from "./staff";

// Landing pages and search engines end to end (BUILD_PLAN 3.6), against the real API with its
// fictional sample PGs: the pages for a campus and a locality, the structured data on them and
// on a PG's page, the sitemap and robots.txt, the pictures links get, and a listing's change
// reaching its page at once through revalidation.

const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;
const ASTER = "fictional-sample-pg-aster-kamla-nagar";

type Thing = Record<string, unknown>;

/** The page's JSON-LD documents, each script's array or object flattened into one list. */
async function structuredData(page: Page): Promise<Thing[]> {
  const texts = await page.locator('script[type="application/ld+json"]').allTextContents();
  return texts.flatMap((text) => {
    const data = JSON.parse(text) as Thing | Thing[];
    return Array.isArray(data) ? data : [data];
  });
}

function ofType(things: Thing[], type: string): Thing {
  const found = things.find((thing) => thing["@type"] === type);
  if (found === undefined) throw new Error(`no ${type} in the page's structured data`);
  return found;
}

interface Place {
  kind: "campus" | "locality";
  slug: string;
  listings: number;
  minRentPaise: number;
  maxRentPaise: number;
}

async function places(request: APIRequestContext): Promise<Place[]> {
  return ((await (await request.get(`${API}/v1/search/places`)).json()) as { items: Place[] })
    .items;
}

async function sitemapSlugs(request: APIRequestContext): Promise<string[]> {
  const slugs: string[] = [];
  let cursor: string | null = null;
  do {
    const response = await request.get(`${API}/v1/search/sitemap`, {
      params: cursor === null ? {} : { cursor },
    });
    const page = (await response.json()) as {
      items: { slug: string }[];
      nextCursor: string | null;
    };
    slugs.push(...page.items.map((item) => item.slug));
    cursor = page.nextCursor;
  } while (cursor !== null);
  return slugs;
}

test.describe("search engines", () => {
  test.beforeAll(async ({ request }) => {
    // Once is enough: a second run waits for the first, then adds nothing.
    await manage(["catalog", "samples"]);
    await expect
      .poll(async () => (await places(request)).some((place) => place.slug === "hindu-college"), {
        timeout: 30_000,
      })
      .toBe(true);
  });

  test("a campus's page lists its PGs nearest first, with what they cost and its questions", async ({
    page,
    request,
  }) => {
    const near = (await places(request)).find(
      (place) => place.kind === "campus" && place.slug === "hindu-college",
    );
    if (near === undefined) throw new Error("no PGs near Hindu College");

    await page.goto("/pg-near/hindu-college");

    await expect(
      page.getByRole("heading", { level: 1, name: "PGs near Hindu College" }),
    ).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      /\/pg-near\/hindu-college$/,
    );
    await expect(page.locator('meta[name="robots"][content*="noindex"]')).toHaveCount(0);
    // The numbers in words are the API's.
    await expect(
      page.getByText(
        new RegExp(
          `^${String(near.listings)} verified PGs? within 3 km of Hindu College, from ${formatINR(near.minRentPaise)} to ${formatINR(near.maxRentPaise)} a month per bed`,
        ),
      ),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: /Fictional Sample PG Aster/ })).toBeVisible();
    const data = await structuredData(page);
    const list = ofType(data, "ItemList");
    expect(list.itemListElement).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ url: expect.stringMatching(new RegExp(`/pg/${ASTER}$`)) }),
      ]),
    );
    expect(ofType(data, "BreadcrumbList").itemListElement).toHaveLength(3);
    expect(ofType(data, "FAQPage").mainEntity).toHaveLength(4);
    await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
      "content",
      /\/pg-near\/hindu-college\/opengraph-image/,
    );
    expect(await wcagViolations(page)).toEqual([]);

    await page.getByRole("link", { name: "See them on the map" }).click();
    await expect(page).toHaveURL(/\/search\?campus=hindu-college$/);
  });

  test("a locality's page lists its PGs and the campuses within reach", async ({
    page,
    request,
  }) => {
    const there = (await places(request)).find(
      (place) => place.kind === "locality" && place.slug === "kamla-nagar",
    );
    if (there === undefined) throw new Error("no PGs in Kamla Nagar");

    await page.goto("/pg-in/kamla-nagar");

    await expect(page.getByRole("heading", { level: 1, name: "PGs in Kamla Nagar" })).toBeVisible();
    await expect(
      page.getByText(new RegExp(`^${String(there.listings)} verified PGs? in Kamla Nagar`)),
    ).toBeVisible();
    const cards = page.getByRole("region", { name: "The PGs" }).getByRole("listitem");
    expect(await cards.count()).toBe(Math.min(there.listings, 12));
    const nearby = page.getByRole("region", { name: "Campuses nearby" });
    await expect(nearby.getByRole("link", { name: /^Hindu College: \d+ PGs?$/ })).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);
  });

  test("a PG's page says what it offers to search engines, but not where it is exactly", async ({
    page,
    request,
  }) => {
    const listing = (await (await request.get(`${API}/v1/properties/${ASTER}`)).json()) as {
      name: string;
      categories: { label: string; baseRentPaise: number }[];
    };

    await page.goto(`/pg/${ASTER}`);

    const business = ofType(await structuredData(page), "LodgingBusiness");
    expect(business).toMatchObject({
      name: listing.name,
      address: { addressLocality: "Kamla Nagar", addressCountry: "IN" },
    });
    expect(business.makesOffer).toEqual(
      listing.categories.map((category) =>
        expect.objectContaining({
          name: category.label,
          priceSpecification: expect.objectContaining({
            price: rupeesText(category.baseRentPaise),
            priceCurrency: "INR",
          }),
        }),
      ),
    );
    expect(JSON.stringify(business)).not.toMatch(/streetAddress|telephone/u);
    // Its picture for links, made from the same data.
    const image = await page.locator('meta[property="og:image"]').getAttribute("content");
    expect(image).toMatch(new RegExp(`/pg/${ASTER}/opengraph-image`));
    const picture = await request.get(image ?? "");
    expect(picture.status()).toBe(200);
    expect(picture.headers()["content-type"]).toBe("image/png");
    await expect(page.getByRole("link", { name: "Kamla Nagar" })).toHaveAttribute(
      "href",
      "/pg-in/kamla-nagar",
    );
  });

  test("robots.txt names the sitemap, which lists every PG the public may see", async ({
    request,
  }) => {
    const robots = await (await request.get("/robots.txt")).text();
    expect(robots).toMatch(/^Sitemap: http:\/\/127\.0\.0\.1:\d+\/sitemap\.xml$/m);

    // Each listing's change revalidates the sitemap, so it soon agrees with the API.
    await expect
      .poll(
        async () => {
          const xml = await (await request.get("/sitemap.xml")).text();
          const listed = new Set(
            [...xml.matchAll(/<loc>[^<]*\/pg\/([a-z0-9-]+)<\/loc>/gu)].map((match) => match[1]),
          );
          return (await sitemapSlugs(request)).filter((slug) => !listed.has(slug));
        },
        { timeout: 20_000 },
      )
      .toEqual([]);
    const xml = await (await request.get("/sitemap.xml")).text();
    expect(xml).toContain("/pg-near/hindu-college</loc>");
    expect(xml).toContain("/pg-in/kamla-nagar</loc>");
    expect(xml).toMatch(new RegExp(`/pg/${ASTER}</loc>\\s*<lastmod>`));
    expect(xml).not.toMatch(/\/(ops|owner|account|staff)\b/u);
  });
});

test.describe("a change to a listing", () => {
  // The first sign-in is refused until consent is given (400 CONSENT_REQUIRED), by design.
  test.use({ expectedConsoleErrors: [/status of 400/] });

  test("reaches its page at once, though the page's data was cached", async ({
    page,
  }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one run is enough");
    test.slow();
    const staff = await newStaff(["ops"]);
    await page.goto("/ops");
    await signInAsStaff(page, staff);
    await expect(page).toHaveURL(/\/ops\/listings$/);
    const csrf = (await page.context().cookies(API)).find(
      (cookie) => cookie.name === "__Secure-csrf",
    )?.value;
    if (csrf === undefined) throw new Error("no CSRF cookie after signing in");
    const found = (await (
      await page.request.get(`${API}/v1/ops/properties`, {
        params: { q: "Fictional Sample PG Aster" },
      })
    ).json()) as { items: { id: string; slug: string }[] };
    const aster = found.items.find((item) => item.slug === ASTER);
    if (aster === undefined) throw new Error("ops can't find the sample PG Aster");
    const listing = (await (
      await page.request.get(`${API}/v1/ops/properties/${aster.id}`)
    ).json()) as { description: string };

    // The page as it is now, which the web server keeps for a minute.
    await page.goto(`/pg/${ASTER}`);
    await expect(page.getByText(listing.description)).toBeVisible();
    const edited = `${listing.description} Edited by a browser test, run ${String(Date.now())}.`;
    const patch = (description: string) =>
      page.request.patch(`${API}/v1/ops/properties/${aster.id}`, {
        data: { description },
        headers: { "X-CSRF-Token": csrf },
      });
    expect((await patch(edited)).status()).toBe(200);
    try {
      // Well within the minute: the API's worker told the web server, which fetched it again.
      await expect(async () => {
        await page.goto(`/pg/${ASTER}`);
        await expect(page.getByText(edited)).toBeVisible({ timeout: 1_000 });
      }).toPass({ timeout: 20_000 });
    } finally {
      await patch(listing.description);
    }
  });
});
