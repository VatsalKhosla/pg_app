import { describe, expect, it } from "vitest";

import { nearestSnap, nextSnap } from "@/components/search/bottom-sheet";
import { activeFilters } from "@/components/search/filters";
import { around, bboxParam, enclosing, metresBetween, parseBbox } from "@/lib/search/area";
import { priceLabel, shortRupees } from "@/lib/search/labels";
import { loadSearchParams, pinsQuery, searchQuery } from "@/lib/search/params";

/** Search's state as the page reads it from a URL's query. */
function fromUrl(query: string) {
  return loadSearchParams(new URLSearchParams(query));
}

describe("searchQuery", () => {
  it("searches one place: a map area first, then a campus, then a locality", () => {
    const everything = "campus=north-campus&locality=kamla-nagar";

    expect(searchQuery(fromUrl(`bbox=77.1,28.6,77.3,28.7&${everything}`))).toMatchObject({
      bbox: "77.1,28.6,77.3,28.7",
      campus: undefined,
      locality: undefined,
    });
    expect(searchQuery(fromUrl(everything))).toMatchObject({
      campus: "north-campus",
      locality: undefined,
    });
    expect(searchQuery(fromUrl("locality=kamla-nagar"))).toMatchObject({
      locality: "kamla-nagar",
    });
  });

  it("takes a radius only from the steps offered, and only around a campus", () => {
    expect(searchQuery(fromUrl("campus=north-campus&radius_m=2000")).radius_m).toBe(2_000);
    expect(searchQuery(fromUrl("campus=north-campus&radius_m=2500")).radius_m).toBeUndefined();
    expect(searchQuery(fromUrl("locality=kamla-nagar&radius_m=2000")).radius_m).toBeUndefined();
  });

  it("sorts by distance only from a campus", () => {
    expect(searchQuery(fromUrl("sort=distance")).sort).toBeUndefined();
    expect(searchQuery(fromUrl("sort=distance&campus=north-campus")).sort).toBe("distance");
    expect(searchQuery(fromUrl("sort=price_asc")).sort).toBe("price_asc");
  });

  it("leaves out what a hand-edited URL got wrong, so the page still shows something", () => {
    const query = searchQuery(
      fromUrl(
        "campus=Not%20A%20Slug&move_in_month=2026-13&budget_min_paise=-5&budget_max_paise=lots" +
          "&gender=anyone&sort=cheapest&amenities=wifi,Bad!,power-backup&bbox=everywhere",
      ),
    );

    expect(query).toMatchObject({
      campus: undefined,
      move_in_month: undefined,
      budget_min_paise: undefined,
      budget_max_paise: undefined,
      gender: undefined,
      sort: undefined,
      bbox: undefined,
      amenities: ["wifi", "power-backup"],
    });
  });

  it("trims the text, leaves it out when blank, and keeps it within 100 characters", () => {
    expect(searchQuery(fromUrl("q=%20%20asha%20")).q).toBe("asha");
    expect(searchQuery(fromUrl("q=%20%20")).q).toBeUndefined();
    expect(searchQuery(fromUrl(`q=${"a".repeat(150)}`)).q).toHaveLength(100);
  });

  it("asks for a dozen at a time and passes the cursor on", () => {
    const query = searchQuery(fromUrl("move_in_month=2026-11&available=true"), "next-page");

    expect(query).toMatchObject({
      move_in_month: "2026-11",
      available: true,
      cursor: "next-page",
      limit: 12,
    });
  });
});

describe("pinsQuery", () => {
  it("has the list's filters, for the map's area at a whole zoom from 5 to 20", () => {
    const state = fromUrl("gender=girls&ac=true&amenities=wifi&campus=north-campus");
    const area = "77.1,28.6,77.3,28.7";

    const pins = pinsQuery(state, area, 13.6);

    expect(pins).toMatchObject({ gender: "girls", ac: true, amenities: ["wifi"], bbox: area });
    expect(pins.zoom).toBe(14);
    expect(pins).not.toHaveProperty("campus");
    expect(pinsQuery(state, area, 2).zoom).toBe(5);
    expect(pinsQuery(state, area, 22).zoom).toBe(20);
  });
});

describe("activeFilters", () => {
  it("counts the sheet's filters, a place once, and not the text or the order", () => {
    expect(activeFilters(searchQuery(fromUrl("")))).toBe(0);
    expect(activeFilters(searchQuery(fromUrl("q=asha&sort=newest")))).toBe(0);
    expect(
      activeFilters(
        searchQuery(fromUrl("campus=north-campus&radius_m=2000&gender=girls&amenities=wifi,ac")),
      ),
    ).toBe(3);
  });
});

describe("price labels", () => {
  it.each([
    [95_000, "₹950"],
    [99_999, "₹1k"],
    [800_000, "₹8k"],
    [1_250_000, "₹12.5k"],
    [1_249_900, "₹12.5k"],
  ])("says %d paise as %s", (paise, said) => {
    expect(shortRupees(paise)).toBe(said);
  });

  it("gives a range, or one price when both ends say the same", () => {
    expect(priceLabel(800_000, 1_200_000)).toBe("₹8k–12k");
    expect(priceLabel(800_000, 820_000)).toBe("₹8k–8.2k");
    expect(priceLabel(800_000, 800_400)).toBe("₹8k");
  });
});

describe("map areas", () => {
  const middle = { lat: 28.6838, lng: 77.2112 };

  it("goes the radius out on each side, wider in longitude away from the equator", () => {
    const box = around(middle, 1_000);

    expect((box.north - middle.lat) * 111_320).toBeCloseTo(1_000, 6);
    expect(middle.lat - box.south).toBeCloseTo(box.north - middle.lat, 12);
    expect(box.east - middle.lng).toBeGreaterThan(box.north - middle.lat);
  });

  it("encloses every point with room to spare, and nothing without points", () => {
    const other = { lat: 28.55, lng: 77.3 };
    const box = enclosing([middle, other], 500);

    expect(enclosing([], 500)).toBeNull();
    expect(box).not.toBeNull();
    expect(box?.south).toBeLessThan(other.lat);
    expect(box?.north).toBeGreaterThan(middle.lat);
    expect(box?.west).toBeLessThan(middle.lng);
    expect(box?.east).toBeGreaterThan(other.lng);
  });

  it("writes the API's west,south,east,north to five places, and reads it back", () => {
    const bounds = { south: 28.612345678, west: 77.1, north: 28.7, east: 77.312345678 };
    const text = bboxParam(bounds);

    expect(text).toBe("77.10000,28.61235,77.31235,28.70000");
    expect(parseBbox(text)).toEqual({ south: 28.61235, west: 77.1, north: 28.7, east: 77.31235 });
    expect(searchQuery(fromUrl(`bbox=${text}`)).bbox).toBe(text);
  });

  it("measures along the ground between two points", () => {
    expect(metresBetween(middle, middle)).toBe(0);
    // A thousandth of a degree of latitude is about 111 m anywhere.
    expect(metresBetween(middle, { lat: middle.lat + 0.001, lng: middle.lng })).toBeCloseTo(
      111.2,
      0,
    );
    const far = { lat: 28.55, lng: 77.3 };
    expect(metresBetween(middle, far)).toBeCloseTo(metresBetween(far, middle), 6);
  });

  it.each([undefined, null, "77.1,28.6,77.3", "77.3,28.6,77.1,28.7", "a,b,c,d"])(
    "reads %s as no area",
    (text) => {
      expect(parseBbox(text)).toBeNull();
    },
  );
});

describe("the phone's list sheet", () => {
  it("settles at the height nearest where it was let go", () => {
    expect(nearestSnap(150, 800)).toBe("peek");
    expect(nearestSnap(380, 800)).toBe("half");
    expect(nearestSnap(700, 800)).toBe("full");
  });

  it("steps up from a peek to nearly all the screen, then back down", () => {
    expect(nextSnap("peek")).toBe("half");
    expect(nextSnap("half")).toBe("full");
    expect(nextSnap("full")).toBe("peek");
  });
});
