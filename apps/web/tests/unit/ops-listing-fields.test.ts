// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  changedDetails,
  type DetailsValues,
  detailsBody,
  detailsDefaults,
  detailsFieldFor,
  rulesOf,
} from "@/components/ops/listing-fields";
import { formatCoordinate, parseCoordinate, pinOf } from "@/components/ops/pin-field";
import type { Listing } from "@/lib/ops/client";

const values: DetailsValues = {
  locality: "kamla-nagar",
  name: "Fictional Residency",
  addressLine: "House 1, Fictional Lane",
  lat: "28.682000",
  lng: "77.206000",
  locationPrecision: "exact",
  genderPolicy: "girls",
  meals: "two",
  description: "  Quiet rooms.  ",
  houseRules: "No smoking\n\n  Gate closes at 10 pm  \n",
  licenceStatus: "unknown",
  licenceNumber: "  ",
  societyPermission: "n/a",
  instantConfirm: false,
};

describe("coordinates", () => {
  it("reads decimal degrees and nothing else", () => {
    expect(parseCoordinate(" 28.6838 ")).toBe(28.6838);
    expect(parseCoordinate("-12.5")).toBe(-12.5);
    for (const text of ["", "28,68", "28.68N", "1e2", "abc", "28."]) {
      expect(parseCoordinate(text)).toBeNull();
    }
  });

  it("puts a pin only inside Delhi NCR", () => {
    expect(pinOf("28.682", "77.206")).toEqual({ lat: 28.682, lng: 77.206 });
    expect(pinOf("19.07", "72.87")).toBeNull();
    expect(pinOf("28.682", "")).toBeNull();
  });

  it("writes six decimal places", () => {
    expect(formatCoordinate(28.68)).toBe("28.680000");
    expect(formatCoordinate(77.20612345)).toBe("77.206123");
  });
});

describe("listing details", () => {
  it("drops blank house rules and trims the rest", () => {
    expect(rulesOf(values.houseRules)).toEqual(["No smoking", "Gate closes at 10 pm"]);
  });

  it("sends the API what it takes, with an empty licence number as none", () => {
    expect(detailsBody(values)).toEqual({
      name: "Fictional Residency",
      addressLine: "House 1, Fictional Lane",
      location: { lat: 28.682, lng: 77.206 },
      locationPrecision: "exact",
      genderPolicy: "girls",
      meals: "two",
      description: "Quiet rooms.",
      houseRules: ["No smoking", "Gate closes at 10 pm"],
      licenceStatus: "unknown",
      licenceNumber: null,
      societyPermission: "n/a",
      instantConfirm: false,
    });
  });

  it("sends only what changed, the pin as one field", () => {
    expect(changedDetails(values, {})).toEqual({});
    expect(changedDetails(values, { name: true, lng: true })).toEqual({
      name: "Fictional Residency",
      location: { lat: 28.682, lng: 77.206 },
    });
    expect(changedDetails(values, { locality: true, meals: false })).toEqual({});
  });

  it("starts a new listing with who it's for, meals and the pin's accuracy unchosen", () => {
    const defaults = detailsDefaults();

    expect(defaults.genderPolicy).toBeUndefined();
    expect(defaults.meals).toBeUndefined();
    expect(defaults.locationPrecision).toBeUndefined();
    expect(defaults.instantConfirm).toBe(false);
  });

  it("starts an existing listing from what it has", () => {
    const listing = {
      locality: { slug: "kamla-nagar", name: "Kamla Nagar" },
      name: "Fictional Residency",
      addressLine: "House 1",
      location: { lat: 28.682, lng: 77.206 },
      locationPrecision: "approximate",
      genderPolicy: "coed",
      meals: "none",
      description: "",
      houseRules: ["No smoking", "Gate closes at 10 pm"],
      licenceStatus: "licensed",
      licenceNumber: null,
      societyPermission: "on_file",
      instantConfirm: true,
    } as unknown as Listing;

    expect(detailsDefaults(listing)).toMatchObject({
      locality: "kamla-nagar",
      lat: "28.682000",
      lng: "77.206000",
      houseRules: "No smoking\nGate closes at 10 pm",
      licenceNumber: "",
    });
  });

  it("puts the API's field errors next to the right fields", () => {
    expect(detailsFieldFor("/name")).toBe("name");
    expect(detailsFieldFor("/location/lat")).toBe("lat");
    expect(detailsFieldFor("/location/lng")).toBe("lng");
    expect(detailsFieldFor("/location")).toBe("lat");
    expect(detailsFieldFor("/houseRules/3")).toBe("houseRules");
    expect(detailsFieldFor("/locality")).toBe("locality");
    expect(detailsFieldFor("/owner")).toBeUndefined();
  });
});
