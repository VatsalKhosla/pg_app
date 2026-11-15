import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { PrintableAgreement } from "@/components/agreements/printable";
import { ownerAgreement } from "@/lib/agreements/server";
import { OWNER_BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";

// The API's limit.
const CODE_MAX_LENGTH = 32;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Agreements");
  return { title: t("metaTitle") };
}

/** A booking's rent agreement, for its owner to print or save as PDF (ADR 0070). */
export default async function OwnerAgreementPrintPage({
  params,
}: PageProps<"/owner/bookings/[code]/agreement">) {
  const { code } = await params;
  const booking = `${OWNER_BOOKINGS_PATH}/${code}` as Route;
  await requireOwner(`${booking}/agreement` as Route);
  if (code.length > CODE_MAX_LENGTH) notFound();
  const agreement = await ownerAgreement(code);
  if (agreement === null) notFound();
  return <PrintableAgreement agreement={agreement} back={booking} />;
}
