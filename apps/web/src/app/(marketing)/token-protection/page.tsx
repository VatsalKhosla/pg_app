import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { TrustPage, TrustSection } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { getPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { trustMetadata } from "@/lib/trust/metadata";
import { trustPages } from "@/lib/trust/pages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("TokenProtection");
  return trustMetadata("tokenProtection", t("title"), t("description"));
}

/**
 * Why paying a token through us is safe (step 3.8; PRODUCT_CONTEXT §5, CLAUDE.md rules 8 to 10).
 * Every amount and period is the API's policy in force.
 */
export default async function TokenProtectionPage() {
  const [t, policies] = await Promise.all([getTranslations("TokenProtection"), getPolicies()]);
  const { booking } = policies;
  const checkHours = booking.checkWindowHours;
  const sections = [
    ["small", t("small", { token: formatINR(booking.tokenPaise) })],
    ["held", t("held", { checkHours })],
    ["notAsShown", t("notAsShown", { checkHours })],
    ["cancel", t("cancel", { freeCancelDays: booking.freeCancelDays })],
    ["confirm", t("confirm", { confirmHours: booking.confirmDeadlineHours })],
    ["safe", t("safe")],
    ["throughUs", t("throughUs", { brand: brand.name })],
  ] as const;
  return (
    <TrustPage title={t("title")} intro={t("intro")}>
      <p role="note" className="rounded-md border bg-muted/40 p-3 text-sm">
        {t("soon")}
      </p>
      {sections.map(([key, text]) => (
        <TrustSection key={key} id={key} title={t(`${key}Title`)}>
          <p className="leading-7">{text}</p>
        </TrustSection>
      ))}
      <p>
        <Link
          href={trustPages.refunds}
          className="font-medium text-primary underline underline-offset-4"
        >
          {t("policyLink")}
        </Link>
      </p>
    </TrustPage>
  );
}
