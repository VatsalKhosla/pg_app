import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { PrintablePoliceSummary } from "@/components/agreements/printable";
import { ownerPoliceVerification } from "@/lib/agreements/server";
import { OWNER_BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";

// The API's limit.
const CODE_MAX_LENGTH = 32;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("PoliceVerification");
  return { title: t("owner.metaTitle") };
}

/**
 * A tenant's details, pre-filled for the Delhi Police portal, for the owner to print (ADR 0070).
 * Every look at them is audited by the API.
 */
export default async function PoliceSummaryPage({
  params,
}: PageProps<"/owner/bookings/[code]/police-verification">) {
  const { code } = await params;
  const booking = `${OWNER_BOOKINGS_PATH}/${code}` as Route;
  await requireOwner(`${booking}/police-verification` as Route);
  if (code.length > CODE_MAX_LENGTH) notFound();
  const verification = await ownerPoliceVerification(code);
  if (verification === null) notFound();
  return <PrintablePoliceSummary verification={verification} back={booking} />;
}
