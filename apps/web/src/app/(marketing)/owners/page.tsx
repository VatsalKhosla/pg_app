import {
  BadgeCheck,
  LayoutDashboard,
  LifeBuoy,
  MessageCircle,
  TrendingUp,
  UserCheck,
  Wallet,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { CtaBand } from "@/components/story/cta-band";
import { FeatureCard, FeatureGrid } from "@/components/story/feature-card";
import { SkyBand } from "@/components/story/sky-band";
import { buttonVariants } from "@/components/ui/button-variants";
import { getPolicies } from "@/lib/api/public";
import { trustPages } from "@/lib/trust/pages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owners");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/owners" },
  };
}

const BASIS_POINTS = 10_000;

/** What the site does for PG owners: the fee from the live policy, in the approved words. */
export default async function OwnersPage() {
  const [t, tHome, tPricing, format, policies] = await Promise.all([
    getTranslations("Owners"),
    getTranslations("Home"),
    getTranslations("Pricing"),
    getFormatter(),
    getPolicies().catch(() => null),
  ]);
  const percent = (bps: number) =>
    format.number(bps / BASIS_POINTS, { style: "percent", maximumFractionDigits: 2 });
  const talk = (
    <Link
      href={trustPages.contact}
      className={buttonVariants({ variant: "sun", size: "lg", shape: "pill" })}
    >
      <MessageCircle aria-hidden="true" />
      {t("contactCta")}
    </Link>
  );
  const fee = policies?.placementFee;

  return (
    <div className="pb-section">
      <SkyBand title={tHome("owners.title")} intro={tHome("owners.body")}>
        {talk}
        <Link
          href={trustPages.pricing}
          className={buttonVariants({ variant: "outline", size: "lg", shape: "pill" })}
        >
          {t("pricingCta")}
        </Link>
      </SkyBand>

      {fee === undefined ? null : (
        <section
          aria-labelledby="fee-title"
          className="mx-auto -mt-10 max-w-page px-gutter sm:-mt-14"
        >
          <div className="grid gap-8 rounded-[2rem] border border-border/70 bg-card/90 p-7 shadow-xl backdrop-blur-sm sm:p-10 lg:grid-cols-[auto_1fr] lg:items-center lg:gap-14">
            <p className="text-[clamp(4rem,10vw,7rem)] leading-none font-semibold text-primary tabular-nums">
              {percent(fee.rateBps)}
            </p>
            <div>
              <h2 id="fee-title" className="text-title-1 font-medium">
                {t("feeTitle")}
              </h2>
              <ul className="mt-4 space-y-2 text-lg leading-relaxed text-muted-foreground">
                <li>{tPricing("fee", { rate: percent(fee.rateBps) })}</li>
                <li>
                  {fee.gstMode === "exclusive"
                    ? tPricing("gstExclusive", { gst: percent(fee.gstRateBps) })
                    : tPricing("gstInclusive", { gst: percent(fee.gstRateBps) })}
                </li>
                <li>{tPricing("noListingFee")}</li>
              </ul>
            </div>
          </div>
        </section>
      )}

      <section aria-labelledby="why-title" className="mx-auto max-w-page px-gutter py-section">
        <h2 id="why-title" className="text-display font-medium">
          {t("whyTitle")}
        </h2>
        <div className="mt-10">
          <FeatureGrid>
            <FeatureCard icon={UserCheck} title={t("tenantsTitle")}>
              {t("tenantsBody")}
            </FeatureCard>
            <FeatureCard icon={TrendingUp} tone="sun" title={t("peakTitle")}>
              {tPricing("listedRent")}
            </FeatureCard>
            <FeatureCard icon={BadgeCheck} tone="green" title={t("verifiedTitle")}>
              {t("verifiedBody")}
            </FeatureCard>
            <FeatureCard icon={LayoutDashboard} tone="teal" title={t("toolsTitle")}>
              {t("toolsBody")}
            </FeatureCard>
            <FeatureCard icon={Wallet} tone="rose" title={t("noFeeTitle")}>
              {tPricing("noListingFee")}
            </FeatureCard>
            <FeatureCard icon={LifeBuoy} tone="violet" title={t("supportTitle")}>
              {t("supportBody")}
            </FeatureCard>
          </FeatureGrid>
        </div>
      </section>

      <CtaBand title={t("ctaTitle")} body={t("ctaBody")}>
        {talk}
      </CtaBand>
    </div>
  );
}
