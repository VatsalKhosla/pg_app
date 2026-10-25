// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  bodyOf,
  type Category,
  type CategoryValues,
  changesOf,
  chargeOf,
  defaultsOf,
  isAmount,
  NEW_CHARGE,
  rowOf,
} from "@/components/ops/category-values";

const category: Category = {
  id: "0192f0c4-0000-7000-8000-000000000001",
  occupancy: "double",
  label: "Two sharing, AC",
  ac: true,
  attachedBath: false,
  balcony: false,
  baseRentPaise: 1_200_000,
  ownerMinRentPaise: 1_000_000,
  ownerMaxRentPaise: null,
  securityDepositPaise: 2_400_000,
  bedsPerRoom: 2,
  mandatoryCharges: [
    {
      type: "metered",
      kind: "electricity",
      label: "Electricity",
      ratePaise: 1_000,
      unit: "kWh",
      monthlyEstimatePaise: 80_000,
    },
    { type: "monthly", kind: "maintenance", label: "Maintenance", amountPaise: 50_000 },
    { type: "oneTime", kind: "registration", label: "Registration", amountPaise: 100_050 },
  ],
  monthlyChargesPaise: 130_000,
  oneTimeChargesPaise: 100_050,
  status: "active",
  rooms: [],
};

function valuesOf(changes: Partial<CategoryValues> = {}): CategoryValues {
  return { ...(defaultsOf(category) as CategoryValues), ...changes };
}

describe("room category values", () => {
  it("shows the API's paise as rupees, and sends them back as the same paise", () => {
    const values = valuesOf();

    expect(values).toMatchObject({ baseRent: "12000", ownerMin: "10000", ownerMax: "" });
    expect(values.charges[2]).toMatchObject({ type: "oneTime", amount: "1000.50" });
    expect(bodyOf(values)).toEqual({
      occupancy: "double",
      label: "Two sharing, AC",
      ac: true,
      attachedBath: false,
      balcony: false,
      baseRentPaise: 1_200_000,
      ownerMinRentPaise: 1_000_000,
      ownerMaxRentPaise: null,
      securityDepositPaise: 2_400_000,
      mandatoryCharges: category.mandatoryCharges,
    });
  });

  it("keeps each kind of charge's own amounts", () => {
    for (const charge of category.mandatoryCharges) {
      expect(chargeOf(rowOf(charge))).toEqual(charge);
    }
    expect(
      chargeOf({
        ...NEW_CHARGE,
        type: "metered",
        label: " Water ",
        rate: "5",
        unit: " kl ",
        estimate: "200",
      }),
    ).toEqual({
      type: "metered",
      kind: "electricity",
      label: "Water",
      ratePaise: 500,
      unit: "kl",
      monthlyEstimatePaise: 20_000,
    });
  });

  it("sends nothing when nothing changed", () => {
    expect(changesOf(category, bodyOf(valuesOf()))).toEqual({});
  });

  it("sends only what changed, a cleared owner's minimum as null", () => {
    const changes = changesOf(
      category,
      bodyOf(valuesOf({ baseRent: "12500", ownerMin: "", balcony: true })),
    );

    expect(changes).toEqual({ baseRentPaise: 1_250_000, ownerMinRentPaise: null, balcony: true });
  });

  it("sends the charges whole when one of them changed", () => {
    const values = valuesOf();
    const charges = values.charges.map((row, index) =>
      index === 1 ? { ...row, amount: "600" } : row,
    );

    expect(changesOf(category, bodyOf({ ...values, charges })).mandatoryCharges).toEqual([
      category.mandatoryCharges[0],
      { type: "monthly", kind: "maintenance", label: "Maintenance", amountPaise: 60_000 },
      category.mandatoryCharges[2],
    ]);
  });

  it("starts a new category with its sharing unchosen", () => {
    expect(defaultsOf(undefined).occupancy).toBeUndefined();
  });

  it("takes zero only where zero makes sense", () => {
    expect(isAmount("0", { zero: true })).toBe(true);
    expect(isAmount("0", { zero: false })).toBe(false);
    expect(isAmount("12000", { zero: false })).toBe(true);
    expect(isAmount("twelve", { zero: true })).toBe(false);
  });
});
