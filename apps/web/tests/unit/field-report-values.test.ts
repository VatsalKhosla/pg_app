// @vitest-environment node
import { describe, expect, it } from "vitest";

import { reportBody, type ReportValues, wholeNumber } from "@/components/field/report-values";

const values: ReportValues = {
  age: "",
  condition: "good",
  cracks: "minor",
  exits: "2",
  fireExtinguishers: "yes",
  cctv: "no",
  warden: "yes",
  womenSafety: ["visitor_log", "secure_entry"],
  licenceNumber: "  ",
  societyPermission: "n/a",
  authorityNotice: "no",
  result: "passed",
  notes: "  Clean and well kept.  ",
  movePin: true,
};

describe("wholeNumber", () => {
  it("reads whole numbers in range and nothing else", () => {
    expect(wholeNumber(" 12 ", 0, 200)).toBe(12);
    expect(wholeNumber("0", 0, 20)).toBe(0);
    for (const text of ["", "-1", "201", "1.5", "two", "1e2"]) {
      expect(wholeNumber(text, 0, 200)).toBeNull();
    }
  });
});

describe("reportBody", () => {
  it("turns the agent's answers into the report the API takes", () => {
    const body = reportBody(
      values,
      { position: { lat: 28.682012345, lng: 77.206098765 }, accuracyM: 8.6 },
      ["photo-1", "photo-2"],
    );

    expect(body).toEqual({
      checklist: {
        buildingAgeYears: null,
        condition: "good",
        cracks: "minor",
        exits: 2,
        fireExtinguishers: true,
        cctv: false,
        warden: true,
        womenSafety: ["secure_entry", "visitor_log"],
        licenceNumber: null,
        societyPermission: "n/a",
        authorityNotice: false,
      },
      result: "passed",
      notes: "Clean and well kept.",
      position: { lat: 28.682012, lng: 77.206099 },
      accuracyM: 9,
      photos: ["photo-1", "photo-2"],
      movePin: true,
    });
  });

  it("keeps a known age and a licence number as given", () => {
    const body = reportBody(
      { ...values, age: "35", licenceNumber: " DL/PG/123 " },
      { position: { lat: 28.68, lng: 77.2 }, accuracyM: 5 },
      ["photo-1"],
    );

    expect(body.checklist.buildingAgeYears).toBe(35);
    expect(body.checklist.licenceNumber).toBe("DL/PG/123");
  });
});
