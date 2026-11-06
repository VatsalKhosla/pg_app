import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { OpsNav } from "@/components/ops/ops-nav";
import {
  OWNER_BOOKINGS_PATH,
  OWNER_HOME_PATH,
  OWNER_INVOICES_PATH,
  OWNER_PGS_PATH,
} from "@/lib/auth/routes";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * The owner area (ADR 0025; Phase 7, ADR 0063): owners, signed in by phone, run their PGs from
 * here: bookings, beds over time, pricing, documents, numbers and invoices. Each page checks for
 * an owner (src/lib/auth/session.ts); the proxy has already sent people without a session to sign
 * in. Pages translate on the server and pass plain strings to their forms (ADR 0011); the bed
 * calendar and the pricing editor, shared with ops, bring the console's messages with them.
 */
export default async function OwnerLayout({ children }: LayoutProps<"/owner">) {
  const t = await getTranslations("Owner.nav");
  return (
    <div className="mx-auto w-full max-w-3xl space-y-10 px-4 py-8 sm:py-12">
      <OpsNav
        label={t("label")}
        links={[
          { href: OWNER_HOME_PATH, label: t("home"), exact: true },
          { href: OWNER_BOOKINGS_PATH, label: t("bookings") },
          { href: OWNER_PGS_PATH, label: t("pgs") },
          { href: OWNER_INVOICES_PATH, label: t("invoices") },
        ]}
      />
      {children}
    </div>
  );
}
