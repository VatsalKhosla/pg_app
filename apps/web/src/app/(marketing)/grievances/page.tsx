import type { Metadata } from "next";
import { headers } from "next/headers";
import { getFormatter, getTranslations } from "next-intl/server";

import { GrievanceForm } from "@/components/grievances/grievance-form";
import { Placeholder, TrustPage, TrustSection } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { company } from "@/config/company";
import { publicEnv } from "@/config/env";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { getSession } from "@/lib/auth/session";
import type { GrievanceCategory } from "@/lib/grievances/client";
import { trustMetadata } from "@/lib/trust/metadata";

const CATEGORIES: readonly GrievanceCategory[] = [
  "listing",
  "visit",
  "booking",
  "owner",
  "staff",
  "privacy",
  "account",
  "other",
];

const FORM_TEXT = [
  "category",
  "chooseCategory",
  "reference",
  "referenceHint",
  "details",
  "detailsHint",
  "name",
  "phone",
  "email",
  "contactHint",
  "humanCheck",
  "submit",
  "submitting",
  "needCategory",
  "needDetails",
  "tooLong",
  "needName",
  "needContact",
  "badPhone",
  "badEmail",
  "receivedTitle",
  "another",
] as const;

const ERRORS = [
  "generic",
  "RATE_LIMITED",
  "HUMAN_CHECK_FAILED",
  "CSRF_TOKEN_INVALID",
  "API_UNREACHABLE",
  "API_TIMEOUT",
  "SERVICE_UNAVAILABLE",
] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Grievances");
  return trustMetadata("grievances", t("title"), t("description", { brand: brand.name }));
}

/**
 * The grievance officer and the complaint form (step 3.8, ADR 0034), as the Consumer Protection
 * (E-Commerce) Rules, 2020 ask: the officer's name and contact details on the site, complaints
 * acknowledged within 48 hours and resolved within a month. Signed in, the person's own
 * complaints and their replies are listed too.
 */
export default async function GrievancesPage() {
  const [t, tTrust, format, me] = await Promise.all([
    getTranslations("Grievances"),
    getTranslations("Trust"),
    getFormatter(),
    getSession(),
  ]);
  const mine =
    me === null ? [] : (await unwrap((await getServerApi()).GET("/v1/me/grievances"))).items;
  const siteKey = publicEnv.turnstileSiteKey;
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const officer = company.grievanceOfficer;
  const when = (moment: string) => format.dateTime(new Date(moment), { dateStyle: "medium" });
  const text = {
    ...Object.fromEntries(FORM_TEXT.map((key) => [key, t(key)])),
    ticket: t.raw("ticket") as string,
    deadlines: t.raw("deadlines") as string,
    errors: Object.fromEntries(ERRORS.map((key) => [key, t(`errors.${key}`)])),
  } as Parameters<typeof GrievanceForm>[0]["text"];

  return (
    <TrustPage title={t("title")} intro={t("intro")}>
      <TrustSection id="officer" title={t("officerTitle")}>
        {officer === null ? (
          <p>
            <Placeholder fact={tTrust("facts.grievanceOfficer")} />
          </p>
        ) : (
          <div className="space-y-1 leading-7">
            <p className="font-semibold">{officer.name}</p>
            <p className="text-muted-foreground">{officer.designation}</p>
            <p>
              {t.rich("officerEmail", {
                email: () => (
                  <a
                    href={`mailto:${officer.email}`}
                    className="font-medium text-primary underline underline-offset-4"
                  >
                    {officer.email}
                  </a>
                ),
              })}
            </p>
            <p>
              {t.rich("officerPhone", {
                phone: () => (
                  <a
                    href={`tel:${officer.phone}`}
                    className="font-medium text-primary underline underline-offset-4"
                  >
                    {officer.phone}
                  </a>
                ),
              })}
            </p>
          </div>
        )}
      </TrustSection>
      <TrustSection id="complain" title={t("formTitle")}>
        <p className="text-muted-foreground">{me === null ? t("signedOut") : t("signedIn")}</p>
        <GrievanceForm
          text={text}
          categories={CATEGORIES.map((value) => ({ value, label: t(`categories.${value}`) }))}
          signedIn={me !== null}
          turnstile={siteKey === undefined ? undefined : { siteKey, nonce }}
        />
      </TrustSection>
      {me === null ? null : (
        <TrustSection id="mine" title={t("mineTitle")}>
          {mine.length === 0 ? (
            <p className="text-muted-foreground">{t("none")}</p>
          ) : (
            <ul className="space-y-4">
              {mine.map((grievance) => (
                <li key={grievance.ticketNumber} className="space-y-2 rounded-lg border p-4">
                  <p className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-mono font-semibold">{grievance.ticketNumber}</span>
                    <span className="text-sm font-medium">{t(`status.${grievance.status}`)}</span>
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {t(`categories.${grievance.category}`)} ·{" "}
                    {t("receivedOn", { when: when(grievance.receivedAt) })}
                    {grievance.status === "resolved"
                      ? null
                      : ` · ${t("dueBy", { when: when(grievance.resolveBy) })}`}
                  </p>
                  <p className="leading-7 whitespace-pre-line">{grievance.details}</p>
                  {grievance.reply === "" ? null : (
                    <p className="leading-7">{t("reply", { reply: grievance.reply })}</p>
                  )}
                  {grievance.resolution === "" ? null : (
                    <p className="leading-7">
                      {t("resolution", { resolution: grievance.resolution })}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </TrustSection>
      )}
      <p className="text-sm text-muted-foreground">{t("dataBoard")}</p>
    </TrustPage>
  );
}
