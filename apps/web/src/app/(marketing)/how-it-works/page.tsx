import {
  CalendarCheck,
  Clock,
  KeyRound,
  MapPinned,
  Search,
  ShieldCheck,
  Undo2,
  UserCheck,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { CtaBand } from "@/components/story/cta-band";
import { FeatureCard, FeatureGrid } from "@/components/story/feature-card";
import { SkyBand } from "@/components/story/sky-band";
import { StaySimulatorSection, StepsList } from "@/components/story/stay-simulator-section";
import { buttonVariants } from "@/components/ui/button-variants";
import { getPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";
import { trustPages } from "@/lib/trust/pages";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("HowItWorks");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/how-it-works" },
  };
}

const STEPS = [
  { key: "find", Icon: MapPinned },
  { key: "visit", Icon: CalendarCheck },
  { key: "reserve", Icon: ShieldCheck },
  { key: "moveIn", Icon: KeyRound },
] as const;

/** How a stay works, from the first search to moving in, and how the token stays safe. */
export default async function HowItWorksPage() {
  const [t, tSteps, tToken, policies] = await Promise.all([
    getTranslations("HowItWorks"),
    getTranslations("Home.steps"),
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
      <SkyBand title={tSteps("title")} intro={tSteps("lead")}>
        {find}
      </SkyBand>

      <section aria-labelledby="steps-title" className="mx-auto max-w-page px-gutter py-section">
        <h2 id="steps-title" className="text-display font-medium">
          {t("stepsTitle")}
        </h2>
        <ol className="steps-rail mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(({ key, Icon }, index) => (
            <li key={key} className="relative">
              <span className="relative z-10 grid size-14 place-items-center rounded-2xl bg-linear-to-br from-primary to-[color-mix(in_oklch,var(--primary)_55%,var(--ember))] text-primary-foreground shadow-lg">
                <Icon aria-hidden="true" className="size-6" />
              </span>
              <p className="mt-5 text-sm font-semibold text-primary">
                {t("stepNumber", { number: index + 1 })}
              </p>
              <h3 className="mt-1 text-title-3 font-medium">{tSteps(`${key}.title`)}</h3>
              <p className="mt-2 leading-relaxed text-muted-foreground">{tSteps(`${key}.body`)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="sim-title" className="mx-auto max-w-page px-gutter">
        <div className="rounded-[2rem] border border-border/70 bg-card/90 p-6 shadow-xl backdrop-blur-sm sm:p-10">
          <h2 id="sim-title" className="text-title-1 font-medium">
            {t("simTitle")}
          </h2>
          <p className="mt-2 max-w-prose text-lg text-muted-foreground">{t("simLead")}</p>
          <div className="mt-8">
            <Suspense fallback={<StepsList />}>
              <StaySimulatorSection />
            </Suspense>
          </div>
        </div>
      </section>

      {policies === null ? null : (
        <section
          aria-labelledby="protect-title"
          className="mx-auto max-w-page px-gutter py-section"
        >
          <h2 id="protect-title" className="text-display font-medium">
            {tToken("title")}
          </h2>
          <p className="mt-3 max-w-prose text-lg text-muted-foreground">{tToken("intro")}</p>
          <div className="mt-10">
            <FeatureGrid>
              <FeatureCard icon={ShieldCheck} title={tToken("smallTitle")}>
                {tToken("small", { token: formatINR(policies.booking.tokenPaise) })}
              </FeatureCard>
              <FeatureCard icon={UserCheck} tone="teal" title={t("confirmTitle")}>
                {tToken("confirm", { confirmHours: policies.booking.confirmDeadlineHours })}
              </FeatureCard>
              <FeatureCard icon={Clock} tone="sun" title={t("heldTitle")}>
                {tToken("held", { checkHours: policies.booking.checkWindowHours })}
              </FeatureCard>
              <FeatureCard icon={KeyRound} tone="rose" title={t("notAsShownTitle")}>
                {tToken("notAsShown", { checkHours: policies.booking.checkWindowHours })}
              </FeatureCard>
              <FeatureCard icon={Undo2} tone="green" title={tToken("cancelTitle")}>
                {tToken("cancel", { freeCancelDays: policies.booking.freeCancelDays })}
              </FeatureCard>
              <FeatureCard icon={CalendarCheck} tone="violet" title={t("policyTitle")}>
                <Link
                  href={trustPages.refunds}
                  className="font-semibold text-primary underline underline-offset-4"
                >
                  {tToken("policyLink")}
                </Link>
              </FeatureCard>
            </FeatureGrid>
          </div>
        </section>
      )}

      <CtaBand title={t("ctaTitle")} body={t("ctaBody")}>
        {find}
      </CtaBand>
    </div>
  );
}
