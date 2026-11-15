import { getFormatter, getTranslations } from "next-intl/server";

import type { TenantDetails } from "@/lib/agreements/client";

/**
 * A tenant's details as the Delhi Police form asks them (ADR 0070), laid out to read and to copy
 * from: what the student gave, never a full identity number.
 */
export async function TenantDetailsList({ details }: { details: TenantDetails }) {
  const [t, format] = await Promise.all([
    getTranslations("PoliceVerification.form"),
    getFormatter(),
  ]);
  const address = details.permanentAddress;
  const rows: [string, string][] = [
    [t("fullName"), details.fullName],
    [t("parentName"), details.parentName],
    [
      t("dateOfBirth"),
      format.dateTime(new Date(`${details.dateOfBirth}T00:00:00+05:30`), { dateStyle: "long" }),
    ],
    [t("gender"), t(`genders.${details.gender}`)],
    [t("phone"), details.phone],
    [
      t("address"),
      [address.line, address.city, address.district, address.state, address.pinCode].join(", "),
    ],
    ...(address.policeStation === null || address.policeStation === undefined
      ? []
      : ([[t("policeStation"), address.policeStation]] as [string, string][])),
    [t("occupation"), t(`occupations.${details.occupation}`)],
    [t("institution"), details.institution],
    [t("idType"), t("idValue", { type: t(`idTypes.${details.idType}`), last4: details.idLast4 })],
    ...(details.references ?? []).map(
      (reference, index) =>
        [
          t("referenceNumbered", { number: index + 1 }),
          `${reference.name} (${reference.relation}), ${reference.phone}`,
        ] as [string, string],
    ),
  ];
  return (
    <dl className="divide-y divide-border/80 rounded-2xl border border-border/80 bg-surface/50">
      {rows.map(([term, value]) => (
        <div key={term} className="grid gap-1 px-4 py-3 sm:grid-cols-3">
          <dt className="text-sm font-medium text-muted-foreground">{term}</dt>
          <dd className="text-sm font-medium break-words text-foreground sm:col-span-2">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
