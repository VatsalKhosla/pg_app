import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { Placeholder, TrustPage, TrustSection } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { company } from "@/config/company";
import { VISITS_PATH } from "@/lib/auth/routes";
import { formatPhone } from "@/lib/format/phone";
import { trustMetadata } from "@/lib/trust/metadata";
import { trustPages } from "@/lib/trust/pages";

const linkClasses = "font-medium text-primary underline underline-offset-4";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Contact");
  return trustMetadata("contact", t("title"), t("description", { brand: brand.name }));
}

/** How to reach a person (step 3.8): the phone numbers a person answers, an email address and the
 * registered office, all from the founders (src/config/company.ts). Until the business is
 * registered, who runs it stands in for the office. */
export default async function ContactPage() {
  const t = await getTranslations("Contact");
  const tTrust = await getTranslations("Trust");
  const format = await getFormatter();
  const { supportPhones, supportHours, supportEmail, legalName, registeredAddress } = company;
  const founders = format.list(
    company.founders.map((founder) => founder.name),
    { type: "conjunction" },
  );
  return (
    <TrustPage title={t("title")} intro={t("intro")}>
      <div className="grid gap-8 sm:grid-cols-2">
        <TrustSection id="phone" title={t("phoneTitle")}>
          {supportPhones.length === 0 ? (
            <p className="text-lg">
              <Placeholder fact={tTrust("facts.supportPhones")} />
            </p>
          ) : (
            <ul className="space-y-1 text-lg">
              {supportPhones.map((phone) => (
                <li key={phone}>
                  <a href={`tel:${phone}`} className={linkClasses}>
                    {formatPhone(phone)}
                  </a>
                </li>
              ))}
            </ul>
          )}
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
      {legalName === null ? (
        <TrustSection id="office" title={t("runByTitle", { brand: brand.name })}>
          <p className="leading-7">{t("runBy", { founders })}</p>
        </TrustSection>
      ) : (
        <TrustSection id="office" title={t("officeTitle")}>
          <address className="space-y-1 not-italic leading-7">
            <p>{legalName}</p>
            <p>{registeredAddress ?? <Placeholder fact={tTrust("facts.registeredAddress")} />}</p>
          </address>
        </TrustSection>
      )}
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
