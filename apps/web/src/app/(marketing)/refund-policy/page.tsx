import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { LegalText, TrustPage } from "@/components/trust/trust-page";
import { brand } from "@/config/brand";
import { legalDocuments } from "@/content/legal";
import { getPolicies } from "@/lib/api/public";
import { legalBlanks } from "@/lib/content/legal";
import { trustMetadata } from "@/lib/trust/metadata";

export async function generateMetadata(): Promise<Metadata> {
  const [tTrust, tLegal] = await Promise.all([getTranslations("Trust"), getTranslations("Legal")]);
  return trustMetadata(
    "refunds",
    tTrust("pages.refunds"),
    tLegal("refundsDescription", { brand: brand.name }),
  );
}

/** A legal text (step 3.8, ADR 0034): DRAFT until a lawyer has reviewed it. */
export default async function RefundPolicyPage() {
  const [t, policies] = await Promise.all([getTranslations("Trust"), getPolicies()]);
  return (
    <TrustPage title={t("pages.refunds")}>
      <LegalText document={legalDocuments.refunds} blanks={await legalBlanks(policies)} />
    </TrustPage>
  );
}
