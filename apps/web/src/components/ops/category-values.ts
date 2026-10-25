import type { Schemas } from "@pg-platform/api-client";

import { paiseToRupeesInput, rupeesToPaise } from "@/lib/money";
import type { CategoryCreate, CategoryUpdate } from "@/lib/ops/client";

import type { ChargeKind, ChargeType, Occupancy } from "./choices";

/**
 * A room category as its form holds it (rupees as typed) and as the API takes it (paise). The
 * browser works out no price: it only turns the rupees ops type into paise, exactly
 * (src/lib/money.ts).
 */

export type Category = Schemas["CategoryInfo"];
type Charge = CategoryCreate["mandatoryCharges"][number];

export interface ChargeRow {
  type: ChargeType;
  kind: ChargeKind;
  label: string;
  /** Monthly and one-time charges. */
  amount: string;
  /** Metered charges. */
  rate: string;
  unit: string;
  estimate: string;
}

export interface CategoryValues {
  occupancy: Occupancy;
  label: string;
  ac: boolean;
  attachedBath: boolean;
  balcony: boolean;
  baseRent: string;
  ownerMin: string;
  ownerMax: string;
  deposit: string;
  charges: ChargeRow[];
}

export const NEW_CHARGE: ChargeRow = {
  type: "monthly",
  kind: "electricity",
  label: "",
  amount: "",
  rate: "",
  unit: "",
  estimate: "",
};

/** Rupees as typed: a positive amount, or zero too when `zero` allows it. */
export function isAmount(text: string, { zero }: { zero: boolean }): boolean {
  const paise = rupeesToPaise(text);
  return paise !== null && (zero || paise > 0);
}

export function rowOf(charge: Charge): ChargeRow {
  const row = { ...NEW_CHARGE, type: charge.type, kind: charge.kind, label: charge.label };
  if (charge.type === "metered") {
    return {
      ...row,
      rate: paiseToRupeesInput(charge.ratePaise),
      unit: charge.unit,
      estimate: paiseToRupeesInput(charge.monthlyEstimatePaise),
    };
  }
  return { ...row, amount: paiseToRupeesInput(charge.amountPaise) };
}

/** Rupees the form has already checked, as paise. */
function paise(text: string): number {
  return rupeesToPaise(text) ?? 0;
}

function optionalPaise(text: string): number | null {
  return text.trim() === "" ? null : paise(text);
}

export function chargeOf(row: ChargeRow): Charge {
  const label = row.label.trim();
  switch (row.type) {
    case "metered":
      return {
        type: "metered",
        kind: row.kind,
        label,
        ratePaise: paise(row.rate),
        unit: row.unit.trim(),
        monthlyEstimatePaise: paise(row.estimate),
      };
    case "oneTime":
      return { type: "oneTime", kind: row.kind, label, amountPaise: paise(row.amount) };
    case "monthly":
      return { type: "monthly", kind: row.kind, label, amountPaise: paise(row.amount) };
  }
}

/** The form's starting values: the category's, or a new one's (its sharing unchosen). */
export function defaultsOf(category: Category | undefined): Partial<CategoryValues> {
  if (category === undefined) {
    return {
      label: "",
      ac: false,
      attachedBath: false,
      balcony: false,
      baseRent: "",
      ownerMin: "",
      ownerMax: "",
      deposit: "",
      charges: [],
    };
  }
  return {
    occupancy: category.occupancy,
    label: category.label,
    ac: category.ac,
    attachedBath: category.attachedBath,
    balcony: category.balcony,
    baseRent: paiseToRupeesInput(category.baseRentPaise),
    ownerMin: paiseToRupeesInput(category.ownerMinRentPaise),
    ownerMax: paiseToRupeesInput(category.ownerMaxRentPaise),
    deposit: paiseToRupeesInput(category.securityDepositPaise),
    charges: category.mandatoryCharges.map(rowOf),
  };
}

export function bodyOf(values: CategoryValues): CategoryCreate {
  return {
    occupancy: values.occupancy,
    label: values.label.trim(),
    ac: values.ac,
    attachedBath: values.attachedBath,
    balcony: values.balcony,
    baseRentPaise: paise(values.baseRent),
    ownerMinRentPaise: optionalPaise(values.ownerMin),
    ownerMaxRentPaise: optionalPaise(values.ownerMax),
    securityDepositPaise: paise(values.deposit),
    mandatoryCharges: values.charges.map(chargeOf),
  };
}

/** Everything but the sharing, which is fixed once a category has rooms made for it. */
const CHANGEABLE = [
  "label",
  "ac",
  "attachedBath",
  "balcony",
  "baseRentPaise",
  "ownerMinRentPaise",
  "ownerMaxRentPaise",
  "securityDepositPaise",
  "mandatoryCharges",
] as const satisfies readonly (keyof CategoryUpdate & keyof CategoryCreate)[];

/** What differs from the category as it was: the API records exactly the fields it's sent. */
export function changesOf(category: Category, body: CategoryCreate): CategoryUpdate {
  const before: CategoryCreate = {
    occupancy: category.occupancy,
    label: category.label,
    ac: category.ac,
    attachedBath: category.attachedBath,
    balcony: category.balcony,
    baseRentPaise: category.baseRentPaise,
    ownerMinRentPaise: category.ownerMinRentPaise,
    ownerMaxRentPaise: category.ownerMaxRentPaise,
    securityDepositPaise: category.securityDepositPaise,
    // Through the same steps as the form's, so equal charges compare equal.
    mandatoryCharges: category.mandatoryCharges.map((charge) => chargeOf(rowOf(charge))),
  };
  const changes: CategoryUpdate = {};
  for (const field of CHANGEABLE) {
    if (JSON.stringify(body[field]) !== JSON.stringify(before[field])) {
      Object.assign(changes, { [field]: body[field] });
    }
  }
  return changes;
}

/** The form field an API error points at; the charges' own errors stay with the form. */
export const POINTER_FIELDS = {
  "/label": "label",
  "/baseRentPaise": "baseRent",
  "/ownerMinRentPaise": "ownerMin",
  "/ownerMaxRentPaise": "ownerMax",
  "/securityDepositPaise": "deposit",
} as const;
