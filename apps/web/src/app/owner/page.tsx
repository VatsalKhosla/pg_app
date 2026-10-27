import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { NotSetUp } from "@/components/owner/not-set-up";
import { OWNER_AGREEMENT_PATH, OWNER_HOME_PATH } from "@/lib/auth/routes";
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
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{owner.businessName}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>

      <section aria-labelledby="business-title" className="space-y-4">
        <h2 id="business-title" className="text-lg font-semibold">
          {t("detailsTitle")}
        </h2>
        <dl className="divide-y rounded-md border">
          {details.map((detail) => (
            <div key={detail.term} className="grid gap-1 p-3 sm:grid-cols-3">
              <dt className="text-sm text-muted-foreground">{detail.term}</dt>
              <dd className="break-words sm:col-span-2">{detail.value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted-foreground">{t("changes")}</p>
      </section>

      <section aria-labelledby="agreement-title" className="space-y-3">
        <h2 id="agreement-title" className="text-lg font-semibold">
          {t("agreementTitle")}
        </h2>
        <p>{t("accepted", { version: owner.agreementVersion ?? "" })}</p>
        <Link
          href={OWNER_AGREEMENT_PATH}
          className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
        >
          {t("read")}
        </Link>
      </section>
    </>
  );
}
