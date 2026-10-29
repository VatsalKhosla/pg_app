import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { TrustPage, TrustSection } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { getPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { trustMetadata } from "@/lib/trust/metadata";
import { trustPages } from "@/lib/trust/pages";

const BASIS_POINTS = 10_000;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Pricing");
  return trustMetadata("pricing", t("title"), t("description", { brand: brand.name }));
}

/**
 * Who pays what (step 3.8; CLAUDE.md rules 1 to 4): students nothing, owners a one-time
 * placement fee. The rates and the token come from the API's policies in force, never from this
 * page, so the page can't say other than what the site charges.
 */
export default async function PricingPage() {
  const [t, format, policies] = await Promise.all([
    getTranslations("Pricing"),
    getFormatter(),
    getPolicies(),
  ]);
  const fee = policies.placementFee;
  const percent = (bps: number) =>
    format.number(bps / BASIS_POINTS, { style: "percent", maximumFractionDigits: 2 });
  return (
    <TrustPage title={t("title")} intro={t("intro", { brand: brand.name })}>
      <TrustSection id="students" title={t("studentsTitle")}>
        <ul className="list-disc space-y-2 pl-5 leading-7">
          <li>{t("noFee")}</li>
          <li>{t("visitsFree")}</li>
          <li>{t("token", { token: formatINR(policies.booking.tokenPaise) })}</li>
          <li>{t("upfront")}</li>
        </ul>
        <p>
          <Link
            href={trustPages.tokenProtection}
            className="font-medium text-primary underline underline-offset-4"
          >
            {t("tokenLink")}
          </Link>
        </p>
      </TrustSection>
      <TrustSection id="owners" title={t("ownersTitle")}>
        <ul className="list-disc space-y-2 pl-5 leading-7">
          <li>{t("fee", { rate: percent(fee.rateBps) })}</li>
          <li>
            {fee.gstMode === "exclusive"
              ? t("gstExclusive", { gst: percent(fee.gstRateBps) })
              : t("gstInclusive", { gst: percent(fee.gstRateBps) })}
          </li>
          <li>{t("listedRent")}</li>
          <li>{t("noListingFee")}</li>
        </ul>
      </TrustSection>
    </TrustPage>
  );
}
