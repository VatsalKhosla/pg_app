import "server-only";

import { getTranslations } from "next-intl/server";

import { brand } from "@/config/brand";
import { company } from "@/config/company";
import type { PublicPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";

/**
 * What a legal text's {blanks} are filled with (src/content/legal): the brand, the company's
 * facts, or a visible placeholder until the founders give them, and the policies in force, so a
 * text never says other than what the site does.
 */
export async function legalBlanks(policies: PublicPolicies): Promise<Record<string, string>> {
  const t = await getTranslations("Trust");
  const { booking } = policies;
  return {
    brand: brand.name,
    legalName: company.legalName ?? t("placeholder", { fact: t("facts.legalName") }),
    address: company.registeredAddress ?? t("placeholder", { fact: t("facts.registeredAddress") }),
    supportEmail: company.supportEmail ?? t("placeholder", { fact: t("facts.supportEmail") }),
    token: formatINR(booking.tokenPaise),
    freeCancelDays: String(booking.freeCancelDays),
    lateCancel: t(`lateCancel.${booking.lateCancelPolicy}`),
    confirmHours: String(booking.confirmDeadlineHours),
    checkHours: String(booking.checkWindowHours),
  };
}
