import { ArrowLeft } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { MarkdownText } from "@/components/content/markdown-text";
import type { OwnerPoliceVerification, RentAgreement } from "@/lib/agreements/client";

import { PrintButton } from "./print-button";
import { TenantDetailsList } from "./tenant-details";

function Back({ href, label }: { href: Route; label: string }) {
  return (
    <Link
      href={href}
      data-print-hidden
      className="inline-flex min-h-8 items-center gap-1.5 text-sm font-semibold text-primary underline underline-offset-4"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      {label}
    </Link>
  );
}

/**
 * A booking's rent agreement as a document to print or save as PDF (ADR 0070): the whole text,
 * marked DRAFT while it is one, with both signatures and the text's SHA-256 fingerprint.
 */
export async function PrintableAgreement({
  agreement,
  back,
}: {
  agreement: RentAgreement;
  back: Route;
}) {
  const [t, format] = await Promise.all([getTranslations("Agreements"), getFormatter()]);
  const when = (moment: string) =>
    format.dateTime(new Date(moment), { dateStyle: "long", timeStyle: "short" });
  const signatures = new Map(agreement.signatures.map((each) => [each.signer, each]));
  return (
    <div className="space-y-6">
      <Back href={back} label={t("back")} />
      <article data-print-document className="space-y-6">
        <h1 className="text-title-1 font-semibold text-foreground">
          {t("printTitle", { code: agreement.booking })}
        </h1>
        <p className="text-sm text-muted-foreground">{t(`status.${agreement.status}`)}</p>
        {agreement.draft ? (
          <p className="rounded-xl bg-warning-soft p-4 text-sm font-medium text-warning-soft-foreground">
            {t("draft")}
          </p>
        ) : null}
        <MarkdownText text={agreement.text} className="space-y-4 text-foreground" />
        <section aria-labelledby="signatures-title" className="space-y-3 border-t pt-6">
          <h2 id="signatures-title" className="text-title-3 font-semibold text-foreground">
            {t("signaturesTitle")}
          </h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            {(["student", "owner"] as const).map((side) => {
              const signature = signatures.get(side);
              return (
                <div key={side} className="space-y-1 rounded-xl border p-4">
                  <dt className="text-sm text-muted-foreground">{t(`parties.${side}`)}</dt>
                  <dd className="text-sm font-medium text-foreground">
                    {signature === undefined
                      ? t("notSigned")
                      : t("signed", { name: signature.name, when: when(signature.signedAt) })}
                  </dd>
                </div>
              );
            })}
          </dl>
          <p className="text-xs break-all text-muted-foreground">
            {t("fingerprint", { version: agreement.templateVersion, sha: agreement.textSha256 })}
          </p>
        </section>
      </article>
      <PrintButton label={t("print")} />
    </div>
  );
}

/**
 * The tenant's details laid out to copy onto the Delhi Police portal, pre-filled, for the owner
 * to print (ADR 0070). The full identity number isn't here: the owner copies it from the
 * original document.
 */
export async function PrintablePoliceSummary({
  verification,
  back,
}: {
  verification: OwnerPoliceVerification;
  back: Route;
}) {
  const [t, format] = await Promise.all([getTranslations("PoliceVerification"), getFormatter()]);
  const day = (date: string) =>
    format.dateTime(new Date(`${date}T00:00:00+05:30`), { dateStyle: "long" });
  const { tenancy, details } = verification;
  const rows: [string, string][] = [
    [t("owner.licensor"), tenancy.licensor],
    [t("owner.pg"), `${tenancy.pgName}, ${tenancy.pgAddress}`],
    [t("owner.room"), tenancy.room],
    [
      t("owner.stay"),
      t("owner.stayValue", { from: day(tenancy.moveIn), to: day(tenancy.plannedMoveOut) }),
    ],
    [t("owner.booking"), tenancy.booking],
  ];
  return (
    <div className="space-y-6">
      <Back href={back} label={t("owner.back")} />
      <article data-print-document className="space-y-6">
        <h1 className="text-title-1 font-semibold text-foreground">
          {t("owner.printTitle", { code: tenancy.booking })}
        </h1>
        <p className="leading-relaxed text-foreground">{t("owner.portalSteps")}</p>
        <section aria-labelledby="tenancy-title" className="space-y-3">
          <h2 id="tenancy-title" className="text-title-3 font-semibold text-foreground">
            {t("owner.tenancy")}
          </h2>
          <dl className="divide-y divide-border/80 rounded-2xl border border-border/80">
            {rows.map(([term, value]) => (
              <div key={term} className="grid gap-1 px-4 py-3 sm:grid-cols-3">
                <dt className="text-sm font-medium text-muted-foreground">{term}</dt>
                <dd className="text-sm font-medium text-foreground sm:col-span-2">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section aria-labelledby="tenant-title" className="space-y-3">
          <h2 id="tenant-title" className="text-title-3 font-semibold text-foreground">
            {t("owner.tenant")}
          </h2>
          {details === null ? (
            <p className="text-sm text-muted-foreground">
              {verification.erased ? t("erased") : t("owner.notYet")}
            </p>
          ) : (
            <TenantDetailsList details={details} />
          )}
        </section>
        <p className="rounded-xl bg-warning-soft p-4 text-sm font-medium text-warning-soft-foreground">
          {t("owner.idReminder")}
        </p>
      </article>
      <PrintButton label={t("owner.print")} />
    </div>
  );
}
