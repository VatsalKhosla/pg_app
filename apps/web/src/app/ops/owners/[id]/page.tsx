import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getFormatter, getTranslations } from "next-intl/server";

import { OwnerForm } from "@/components/ops/owner-form";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { requireOps } from "@/lib/auth/session";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.ownerPage");
  return { title: t("metaTitle") };
}

async function load(id: string) {
  const api = await getServerApi();
  const path = { params: { path: { owner_id: id } } };
  try {
    return await Promise.all([
      unwrap(api.GET("/v1/ops/owners/{owner_id}", path)),
      unwrap(api.GET("/v1/ops/owners/{owner_id}/agreements", path)),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

/**
 * One owner: their business details, which ops edit, and every acceptance of the owner agreement
 * (ADR 0025), with when, from which IP and browser, and the hash of the text they accepted.
 */
export default async function OpsOwnerPage({ params }: PageProps<"/ops/owners/[id]">) {
  const { id } = await params;
  await requireOps(`/ops/owners/${id}` as Route);
  if (!UUID.test(id)) notFound();
  const [owner, acceptances] = await load(id);
  const t = await getTranslations("Ops");
  const format = await getFormatter();
  const standing =
    owner.agreementVersion === null
      ? t("ownerPage.never")
      : owner.agreementCurrent
        ? t("ownerPage.current", { version: owner.agreementVersion })
        : t("ownerPage.outdated", { version: owner.agreementVersion });

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{owner.businessName}</h1>
        <p className="text-muted-foreground">
          {[
            owner.legalName,
            owner.phone,
            t(`ownerPage.kyc.${owner.kycStatus}`),
            t(`ownerPage.status.${owner.status}`),
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>

      <section aria-labelledby="details-title" className="space-y-4">
        <h2 id="details-title" className="border-b pb-2 text-lg font-semibold">
          {t("ownerPage.details")}
        </h2>
        <OwnerForm owner={owner} />
      </section>

      <section aria-labelledby="agreement-title" className="space-y-4">
        <h2 id="agreement-title" className="border-b pb-2 text-lg font-semibold">
          {t("ownerPage.agreementTitle")}
        </h2>
        <p>{standing}</p>
        {acceptances.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("ownerPage.historyEmpty")}</p>
        ) : (
          <ol aria-label={t("ownerPage.history")} className="divide-y rounded-md border">
            {acceptances.items.map((acceptance) => (
              <li key={`${acceptance.version}-${acceptance.acceptedAt}`} className="p-3">
                <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                  <dt className="text-muted-foreground">{t("ownerPage.version")}</dt>
                  <dd className="font-medium">{acceptance.version}</dd>
                  <dt className="text-muted-foreground">{t("ownerPage.acceptedAt")}</dt>
                  <dd>
                    {format.dateTime(new Date(acceptance.acceptedAt), {
                      dateStyle: "medium",
                      timeStyle: "medium",
                    })}
                  </dd>
                  <dt className="text-muted-foreground">{t("ownerPage.ip")}</dt>
                  <dd className="break-all">{acceptance.ip}</dd>
                  <dt className="text-muted-foreground">{t("ownerPage.userAgent")}</dt>
                  <dd className="break-all">{acceptance.userAgent ?? t("ownerPage.unknown")}</dd>
                  <dt className="text-muted-foreground">{t("ownerPage.hash")}</dt>
                  <dd className="font-mono text-xs break-all">{acceptance.documentSha256}</dd>
                </dl>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
