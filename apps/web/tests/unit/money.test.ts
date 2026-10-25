// @vitest-environment node
import { describe, expect, it } from "vitest";

import { formatINR, paiseToRupeesInput, rupeesToPaise } from "@/lib/money";

describe("formatINR", () => {
  it("shows whole rupees without paise, in Indian grouping", () => {
    expect(formatINR(1_200_000)).toBe("₹12,000");
    expect(formatINR(1_234_567_800)).toBe("₹1,23,45,678");
    expect(formatINR(0)).toBe("₹0");
  });

  it("shows the paise when there are any", () => {
    expect(formatINR(1_200_050)).toBe("₹12,000.50");
    expect(formatINR(1)).toBe("₹0.01");
  });
});

describe("rupeesToPaise", () => {
  it.each([
    ["12000", 1_200_000],
    ["12,000", 1_200_000],
    ["₹12,000", 1_200_000],
    [" 12000.5 ", 1_200_050],
    ["12000.05", 1_200_005],
    ["0", 0],
    ["999999999.99", 99_999_999_999],
  ])("turns %j into %d paise without floating point", (input, paise) => {
    expect(rupeesToPaise(input)).toBe(paise);
  });

  it.each(["", "abc", "-5", "1.234", "1e3", "12 000", "1000000000", ".5", "5."])(
    "refuses %j",
    (input) => {
      expect(rupeesToPaise(input)).toBeNull();
    },
  );
});

describe("paiseToRupeesInput", () => {
  it("gives the rupees as a form shows them, and back", () => {
    for (const paise of [0, 5, 50, 1_200_000, 1_200_050, 99_999_999_999]) {
      expect(rupeesToPaise(paiseToRupeesInput(paise))).toBe(paise);
    }
    expect(paiseToRupeesInput(1_200_050)).toBe("12000.50");
    expect(paiseToRupeesInput(1_200_000)).toBe("12000");
  });

  it("leaves the field empty when there's no amount", () => {
    expect(paiseToRupeesInput(null)).toBe("");
    expect(paiseToRupeesInput(undefined)).toBe("");
  });
});
