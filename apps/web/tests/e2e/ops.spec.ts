import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, wcagViolations } from "./fixtures";
import { newMobile } from "./sign-in-codes";
import { newStaff, signInAsStaff } from "./staff";

// The ops console end to end (BUILD_PLAN 2.4): an ops person signs in on a phone, builds a
// listing from nothing (owner, building, pin, rooms, amenities, a photo) and publishes it, against
// the real API and its worker (scripts/e2e-api.sh).

interface Places {
  localities: { name: string; center: { lat: number; lng: number } }[];
}

// Where the phone is: a locality's centre, from the verified geo data the API loads.
const places = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "../api/src/app/modules/geo/data/places.json"), "utf8"),
) as Places;
const locality = places.localities.find((place) => place.name === "Kamla Nagar");
if (locality === undefined) throw new Error("Kamla Nagar is missing from places.json");
const here = locality.center;

// A transparent 1×1 PNG for every map tile: OpenStreetMap's tile servers aren't for tests (their tile
// usage policy).
const BLANK_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgYGBgAAAABQABeqhXUAAAAABJRU5ErkJggg==",
  "base64",
);

test.describe("ops console", () => {
  test.use({
    geolocation: { latitude: here.lat, longitude: here.lng, accuracy: 12 },
    permissions: ["geolocation"],
    // The first sign-in is refused until consent is given (400 CONSENT_REQUIRED), by design.
    expectedConsoleErrors: [/status of 400/],
  });

  test("ops build a listing on a phone and publish it", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "phone", "one run is enough, and phones are the hard case");
    // Signing in, then the worker preparing the photo.
    test.slow();
    await page.route("https://tile.openstreetmap.org/**", (route) =>
      route.fulfill({ contentType: "image/png", body: BLANK_TILE }),
    );
    const staff = await newStaff(["ops"]);

    await page.goto("/ops");
    await expect(page).toHaveURL(/\/staff\/sign-in\?next=%2Fops$/);
    await signInAsStaff(page, staff);
    await expect(page).toHaveURL(/\/ops\/listings$/);
    await expect(page.getByRole("heading", { name: "Listings", level: 1 })).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    // The owner, new to the platform.
    const nav = page.getByRole("navigation", { name: "Ops console" });
    await nav.getByRole("link", { name: "New listing" }).click();
    await expect(page.getByRole("heading", { name: "New listing", level: 1 })).toBeVisible();
    const owner = newMobile();
    await page.getByLabel("Find the owner by phone number or business name").fill(owner);
    await page.getByRole("button", { name: "Find", exact: true }).click();
    await expect(page.getByText("No owner found. Add them below.")).toBeVisible();
    await page.getByLabel("Owner's mobile number", { exact: true }).fill(owner);
    await page.getByLabel("Legal name", { exact: true }).fill("Fictional Stays LLP");
    await page.getByLabel("Business name", { exact: true }).fill("Fictional Stays");
    await page.getByRole("button", { name: "Add the owner" }).click();
    await expect(page.getByText(/^Owner: Fictional Stays, \+91/)).toBeVisible();

    // The building, pinned where the phone is.
    const name = `Fictional Residency ${owner.slice(-4)}`;
    await page.getByLabel("Locality").selectOption({ label: "Kamla Nagar" });
    await page.getByLabel("PG name").fill(name);
    await page.getByLabel("Address", { exact: true }).fill("House 1, Fictional Lane");
    await page.getByRole("button", { name: "Use my location" }).click();
    await expect(page.getByText(/^Pin set to your location/)).toBeVisible();
    await expect(page.getByLabel("Latitude")).toHaveValue(here.lat.toFixed(6));
    await expect(page.getByLabel("Longitude")).toHaveValue(here.lng.toFixed(6));
    await page.getByLabel("Exact: the pin is on the building").check();
    await page.getByLabel("Girls").check();
    await page.getByLabel("Two meals a day").check();
    expect(await wcagViolations(page)).toEqual([]);
    await page.getByRole("button", { name: "Create the draft" }).click();

    await expect(page).toHaveURL(/\/ops\/listings\/[0-9a-f-]{36}/);
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
    const status = page.getByRole("region", { name: "Status" });
    await expect(status.getByText("Status: Draft")).toBeVisible();
    await expect(status.getByRole("button", { name: "Publish" })).toBeDisabled();

    // What it sells: a room category with its charges, and a room of two beds.
    const rooms = page.getByRole("region", { name: "Rooms and beds" });
    await rooms.getByRole("button", { name: "Add a room category" }).click();
    await rooms.getByLabel("Two sharing").check();
    await rooms.getByLabel("Name students see").fill("Two sharing, AC");
    await rooms.getByLabel("AC", { exact: true }).check();
    await rooms.getByLabel("Listed rent per bed, per month (₹)").fill("12000");
    await rooms.getByLabel("Security deposit (₹)").fill("24000");
    await rooms.getByRole("button", { name: "Add a charge" }).click();
    await rooms.getByLabel("What for").selectOption({ label: "Maintenance" });
    await rooms.getByLabel("Label", { exact: true }).fill("Maintenance");
    await rooms.getByLabel("Amount (₹)").fill("500");
    await rooms.getByRole("button", { name: "Save the category" }).click();
    await expect(rooms.getByRole("heading", { name: "Two sharing, AC" })).toBeVisible();
    await expect(rooms.getByText("₹12,000 a month · deposit ₹24,000")).toBeVisible();
    await expect(rooms.getByText(/^Plus about ₹500 a month in charges/)).toBeVisible();
    await rooms.getByLabel("Room number or name").fill("101");
    await rooms.getByLabel("Floor (optional)").fill("1");
    await rooms.getByRole("button", { name: "Add the room" }).click();
    await expect(rooms.getByText("Bed A: in use")).toBeVisible();
    await expect(rooms.getByText("Bed B: in use")).toBeVisible();

    const amenities = page.getByRole("region", { name: "Amenities" });
    await amenities.getByLabel("Wi-Fi").check();
    await amenities.getByRole("button", { name: "Save amenities" }).click();
    await expect(amenities.getByText("Saved.")).toBeVisible();

    // A photo, straight to storage; it joins the listing once the worker has prepared it.
    const media = page.getByRole("region", { name: "Photos and videos" });
    await media
      .getByLabel("Add photos or videos")
      .setInputFiles(path.resolve(process.cwd(), "tests/e2e/files/room.jpg"));
    await expect(media.getByRole("img", { name: "Photo 1" })).toBeVisible({ timeout: 60_000 });
    await expect(media.getByText("Cover", { exact: true })).toBeVisible();

    await expect(status.getByRole("button", { name: "Publish" })).toBeEnabled();
    await status.getByRole("button", { name: "Publish" }).click();
    await expect(status.getByText("Status: Published")).toBeVisible();
    await expect(status.getByRole("button", { name: "Pause" })).toBeVisible();
    const history = page.getByRole("region", { name: "History" });
    await expect(history.getByText("Draft to Published")).toBeVisible();
    expect(await wcagViolations(page)).toEqual([]);

    await nav.getByRole("link", { name: "Listings" }).click();
    await expect(page.getByRole("link", { name: new RegExp(name) })).toBeVisible();
  });
});
