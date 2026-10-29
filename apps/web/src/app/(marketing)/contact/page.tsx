import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Placeholder, TrustPage, TrustSection } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { company } from "@/config/company";
import { VISITS_PATH } from "@/lib/auth/routes";
import { trustMetadata } from "@/lib/trust/metadata";
import { trustPages } from "@/lib/trust/pages";

const linkClasses = "font-medium text-primary underline underline-offset-4";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Contact");
  return trustMetadata("contact", t("title"), t("description", { brand: brand.name }));
}

/** How to reach a person (step 3.8): a phone line a person answers, an email address and the
 * registered office, all from the founders (src/config/company.ts). */
export default async function ContactPage() {
  const t = await getTranslations("Contact");
  const tTrust = await getTranslations("Trust");
  const { supportPhone, supportHours, supportEmail, legalName, registeredAddress } = company;
  return (
    <TrustPage title={t("title")} intro={t("intro")}>
      <div className="grid gap-8 sm:grid-cols-2">
        <TrustSection id="phone" title={t("phoneTitle")}>
          <p className="text-lg">
            {supportPhone === null ? (
              <Placeholder fact={tTrust("facts.supportPhone")} />
            ) : (
              <a href={`tel:${supportPhone}`} className={linkClasses}>
                {supportPhone}
              </a>
            )}
          </p>
          <p className="text-muted-foreground">
            {supportHours === null ? (
              <Placeholder fact={tTrust("facts.supportHours")} />
            ) : (
              t("hours", { hours: supportHours })
            )}
          </p>
        </TrustSection>
        <TrustSection id="email" title={t("emailTitle")}>
          <p className="text-lg break-words">
            {supportEmail === null ? (
              <Placeholder fact={tTrust("facts.supportEmail")} />
            ) : (
              <a href={`mailto:${supportEmail}`} className={linkClasses}>
                {supportEmail}
              </a>
            )}
          </p>
        </TrustSection>
      </div>
      <TrustSection id="office" title={t("officeTitle")}>
        <address className="space-y-1 not-italic leading-7">
          <p>{legalName ?? <Placeholder fact={tTrust("facts.legalName")} />}</p>
          <p>{registeredAddress ?? <Placeholder fact={tTrust("facts.registeredAddress")} />}</p>
        </address>
      </TrustSection>
      <TrustSection id="visits" title={t("visitsTitle")}>
        <p className="leading-7">
          {t("visits")}{" "}
          <Link href={VISITS_PATH} className={linkClasses}>
            {t("visitsLink")}
          </Link>
        </p>
      </TrustSection>
      <TrustSection id="complaints" title={t("complaintsTitle")}>
        <p className="leading-7">
          {t("complaints")}{" "}
          <Link href={trustPages.grievances} className={linkClasses}>
            {t("complaintsLink")}
          </Link>
        </p>
      </TrustSection>
    </TrustPage>
  );
}
