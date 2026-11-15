import type { Metadata, Route } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { PrintableAgreement } from "@/components/agreements/printable";
import { studentAgreement } from "@/lib/agreements/server";
import { BOOKINGS_PATH } from "@/lib/auth/routes";
import { requireSession } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Agreements");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/** The student's rent agreement, to print or save as PDF (ADR 0070). */
export default async function StudentAgreementPage({
  params,
}: PageProps<"/bookings/[code]/agreement">) {
  const { code } = await params;
  const booking = `${BOOKINGS_PATH}/${code}` as Route;
  await requireSession(`${booking}/agreement` as Route);
  const agreement = await studentAgreement(code);
  if (agreement === null) notFound();
  return (
    <div className="mx-auto w-full max-w-3xl px-gutter py-10 sm:py-14">
      <PrintableAgreement agreement={agreement} back={booking} />
    </div>
  );
}
