import { expect, type Page } from "@playwright/test";

import { newMobile } from "./sign-in-codes";
import { newStaff, signInAsStaff } from "./staff";

// Setting up what a browser test works on, through the API as an ops person would, so each run
// has a listing of its own and runs and other tests never meet.

export const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8100"}`;

/**
 * A new ops person, signed in, with a listing of their own that has one room type, and with
 * `beds` beds in room 101 when asked. `post` calls the API as them.
 */
export async function opsWithListing(
  page: Page,
  name: string,
  { beds = 0 }: { beds?: number } = {},
) {
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
    return (await response.json()) as { id: string; categories?: { id: string }[] };
  };
  const owner = await post("/v1/ops/owners", {
    phone: newMobile(),
    legalName: "Fictional Pricing Stays Private Limited",
    businessName: "Fictional Pricing Stays",
  });
  const listing = await post("/v1/ops/properties", {
    owner: owner.id,
    locality: "kamla-nagar",
    name,
    addressLine: "House 9, a fictional lane",
    location: { lat: 28.688, lng: 77.21 },
    locationPrecision: "exact",
    genderPolicy: "girls",
    meals: "two",
  });
  const built = await post(`/v1/ops/properties/${listing.id}/room-categories`, {
    occupancy: "double",
    label: "Twin sharing",
    baseRentPaise: 1_000_000,
    securityDepositPaise: 1_000_000,
  });
  const category = built.categories?.[0]?.id;
  if (beds > 0 && category !== undefined) {
    await post(`/v1/ops/room-categories/${category}/rooms`, { label: "101", beds });
  }
  return { listing, post };
}
