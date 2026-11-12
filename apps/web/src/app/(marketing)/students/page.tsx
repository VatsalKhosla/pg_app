import {
  BadgeCheck,
  CalendarCheck,
  Receipt,
  Search,
  ShieldCheck,
  Undo2,
  Wallet,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { CtaBand } from "@/components/story/cta-band";
import { FeatureCard, FeatureGrid } from "@/components/story/feature-card";
import { MetroLines } from "@/components/story/metro-lines";
import { PolicyFacts } from "@/components/story/policy-facts";
import { SkyBand } from "@/components/story/sky-band";
import { buttonVariants } from "@/components/ui/button-variants";
import { getPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { trustPages } from "@/lib/trust/pages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Students");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/students" },
  };
}

/** What the site does for students and their parents, as the business rules promise it. */
export default async function StudentsPage() {
  const [t, tHome, tPricing, tToken, policies] = await Promise.all([
    getTranslations("Students"),
    getTranslations("Home"),
    getTranslations("Pricing"),
    getTranslations("TokenProtection"),
    getPolicies().catch(() => null),
  ]);
  const find = (
    <Link href="/search" className={buttonVariants({ variant: "sun", size: "lg", shape: "pill" })}>
      <Search aria-hidden="true" />
      {t("findCta")}
    </Link>
  );

  return (
    <div className="pb-section">
      <SkyBand title={tHome("students.title")} intro={tHome("students.body")}>
        {find}
        <Link
          href={trustPages.tokenProtection}
          className={buttonVariants({ variant: "outline", size: "lg", shape: "pill" })}
        >
          {tToken("title")}
        </Link>
      </SkyBand>

      <div className="-mt-10 sm:-mt-14">
        <Suspense fallback={null}>
          <PolicyFacts />
        </Suspense>
      </div>

      <section aria-labelledby="promises-title" className="mx-auto max-w-page px-gutter py-section">
        <h2 id="promises-title" className="text-display font-medium">
          {t("promisesTitle")}
        </h2>
        <div className="mt-10">
          <FeatureGrid>
            <FeatureCard icon={BadgeCheck} tone="green" title={t("verifiedTitle")}>
              {t("verifiedBody")}
            </FeatureCard>
            <FeatureCard icon={Wallet} title={t("feeTitle")}>
              {tPricing("noFee")}
            </FeatureCard>
            <FeatureCard icon={Receipt} tone="teal" title={t("upfrontTitle")}>
              {tPricing("upfront")}
            </FeatureCard>
            <FeatureCard icon={CalendarCheck} tone="sun" title={t("visitTitle")}>
              {tPricing("visitsFree")}
            </FeatureCard>
            {policies === null ? null : (
              <FeatureCard icon={ShieldCheck} tone="violet" title={tToken("smallTitle")}>
                {tToken("small", { token: formatINR(policies.booking.tokenPaise) })}
              </FeatureCard>
            )}
            {policies === null ? null : (
              <FeatureCard icon={Undo2} tone="rose" title={tToken("cancelTitle")}>
                {tToken("cancel", { freeCancelDays: policies.booking.freeCancelDays })}
              </FeatureCard>
            )}
          </FeatureGrid>
        </div>
      </section>

      <Suspense fallback={null}>
        <MetroLines />
      </Suspense>

      <div className="pt-section">
        <CtaBand title={t("ctaTitle")} body={t("ctaBody")}>
          {find}
        </CtaBand>
      </div>
    </div>
  );
}
