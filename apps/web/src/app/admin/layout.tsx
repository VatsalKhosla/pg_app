import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations } from "next-intl/server";

import { OpsNav } from "@/components/ops/ops-nav";
import { ADMIN_POLICIES_PATH, ADMIN_RENT_BANDS_PATH, STAFF_HOME_PATH } from "@/lib/auth/routes";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Admin");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * The admin console (step 4.1, ADR 0036): the policies money follows and rent bands, admins'
 * alone. Each page checks for an admin (src/lib/auth/session.ts) after the proxy has sent people
 * without a session to sign in; the forms get the console's messages only (ADR 0011).
 */
export default async function AdminLayout({ children }: LayoutProps<"/admin">) {
  const t = await getTranslations("Admin.nav");
  const messages = await getMessages();

  return (
    <NextIntlClientProvider messages={{ Admin: messages.Admin }}>
      <div className="mx-auto w-full max-w-5xl space-y-8 px-4 py-8 sm:py-10">
        <OpsNav
          label={t("label")}
          links={[
            { href: ADMIN_POLICIES_PATH, label: t("policies") },
            { href: ADMIN_RENT_BANDS_PATH, label: t("rentBands") },
            { href: STAFF_HOME_PATH, label: t("staffHome"), exact: true },
          ]}
        />
        {children}
      </div>
    </NextIntlClientProvider>
  );
}
