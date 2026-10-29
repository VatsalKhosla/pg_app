import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations } from "next-intl/server";

import { OpsNav } from "@/components/ops/ops-nav";
import {
  OPS_LISTINGS_PATH,
  OPS_NEW_LISTING_PATH,
  OPS_OWNERS_PATH,
  OPS_GRIEVANCES_PATH,
  OPS_VISITS_PATH,
  STAFF_HOME_PATH,
} from "@/lib/auth/routes";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * The ops console (ADR 0023). Each page checks that an ops person or an admin is signed in
 * (src/lib/auth/session.ts); the proxy has already sent people without a session to sign in.
 *
 * The console's forms format their own messages (file names, room labels, counts), so this one
 * area gets a message provider, with the console's messages only (ADR 0011).
 */
export default async function OpsLayout({ children }: LayoutProps<"/ops">) {
  const t = await getTranslations("Ops.nav");
  const messages = await getMessages();

  return (
    <NextIntlClientProvider messages={{ Ops: messages.Ops }}>
      <div className="mx-auto w-full max-w-5xl space-y-8 px-4 py-8 sm:py-10">
        <OpsNav
          label={t("label")}
          links={[
            { href: OPS_LISTINGS_PATH, label: t("listings"), exact: true },
            { href: OPS_NEW_LISTING_PATH, label: t("newListing"), exact: true },
            { href: OPS_OWNERS_PATH, label: t("owners") },
            { href: OPS_VISITS_PATH, label: t("visits") },
            { href: OPS_GRIEVANCES_PATH, label: t("grievances") },
            { href: STAFF_HOME_PATH, label: t("staffHome"), exact: true },
          ]}
        />
        {children}
      </div>
    </NextIntlClientProvider>
  );
}
