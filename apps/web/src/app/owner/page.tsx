import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { NotSetUp } from "@/components/owner/not-set-up";
import {
  OWNER_AGREEMENT_PATH,
  OWNER_BOOKINGS_PATH,
  OWNER_HOME_PATH,
  OWNER_INVOICES_PATH,
  OWNER_PGS_PATH,
} from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { getOwnProfile } from "@/lib/owner/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.home");
  return { title: t("metaTitle") };
}

/** The owner's business as we keep it, once they've accepted the current agreement. */
export default async function OwnerHomePage() {
  await requireOwner(OWNER_HOME_PATH);
  const owner = await getOwnProfile();
  if (owner === null) return <NotSetUp />;
  // None accepted yet, or a new version since: the agreement comes first.
  if (!owner.agreementCurrent) redirect(OWNER_AGREEMENT_PATH);
  const t = await getTranslations("Owner.home");
  const details = [
    { term: t("businessName"), value: owner.businessName },
    { term: t("legalName"), value: owner.legalName },
    { term: t("gstin"), value: owner.gstin ?? t("noGstin") },
    { term: t("phone"), value: owner.phone ?? "" },
  ];

  return (
    <>
      <div className="space-y-2">
        <h1 className="text-title-1 font-semibold tracking-tight text-foreground">
          {owner.businessName}
        </h1>
        <p className="text-body text-muted-foreground">{t("intro")}</p>
      </div>

      <section
        aria-labelledby="business-title"
        className="space-y-4 rounded-2xl border border-border/80 bg-card p-5 shadow-xs sm:p-6"
      >
        <h2 id="business-title" className="text-title-3 font-semibold tracking-tight">
          {t("detailsTitle")}
        </h2>
        <dl className="divide-y divide-border/80 rounded-xl border border-border/80 bg-surface/50">
          {details.map((detail) => (
            <div key={detail.term} className="grid gap-1 px-4 py-3 sm:grid-cols-3">
              <dt className="text-sm font-medium text-muted-foreground">{detail.term}</dt>
              <dd className="font-medium break-words text-foreground sm:col-span-2">
                {detail.value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted-foreground">{t("changes")}</p>
      </section>

      <div className="grid gap-6 sm:grid-cols-2">
        <section
          aria-labelledby="run-title"
          className="space-y-3 rounded-2xl border border-border/80 bg-card p-5 shadow-xs sm:p-6"
        >
          <h2 id="run-title" className="text-title-3 font-semibold tracking-tight">
            {t("runTitle")}
          </h2>
          <ul className="space-y-2">
            <li>
              <Link
                href={OWNER_BOOKINGS_PATH}
                className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
              >
                {t("bookingsLink")}
              </Link>
            </li>
            <li>
              <Link
                href={OWNER_PGS_PATH}
                className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
              >
                {t("pgsLink")}
              </Link>
            </li>
          </ul>
        </section>

        <section
          aria-labelledby="invoices-title"
          className="space-y-3 rounded-2xl border border-border/80 bg-card p-5 shadow-xs sm:p-6"
        >
          <h2 id="invoices-title" className="text-title-3 font-semibold tracking-tight">
            {t("invoicesTitle")}
          </h2>
          <Link
            href={OWNER_INVOICES_PATH}
            className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
          >
            {t("invoicesLink")}
          </Link>
        </section>
      </div>

      <section
        aria-labelledby="agreement-title"
        className="space-y-3 rounded-2xl border border-border/80 bg-card p-5 shadow-xs sm:p-6"
      >
        <h2 id="agreement-title" className="text-title-3 font-semibold tracking-tight">
          {t("agreementTitle")}
        </h2>
        <p className="text-sm text-muted-foreground">
          {t("accepted", { version: owner.agreementVersion ?? "" })}
        </p>
        <Link
          href={OWNER_AGREEMENT_PATH}
          className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4 hover:text-primary-hover"
        >
          {t("read")}
        </Link>
      </section>
    </>
  );
}
