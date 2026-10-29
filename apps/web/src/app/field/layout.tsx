import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations } from "next-intl/server";

import { OpsNav } from "@/components/ops/ops-nav";
import { FIELD_STUDENT_VISITS_PATH, FIELD_VISITS_PATH, STAFF_HOME_PATH } from "@/lib/auth/routes";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Field");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/**
 * Field agents' screens (ADR 0024): their verification visits, and the report from the building.
 * Each page checks for a field agent, ops or an admin; the API shows an agent only their own
 * visits. The report form formats its own messages, so this area gets the console's and the
 * field's messages only (ADR 0011).
 */
export default async function FieldLayout({ children }: LayoutProps<"/field">) {
  const t = await getTranslations("Field.nav");
  const messages = await getMessages();

  return (
    <NextIntlClientProvider messages={{ Ops: messages.Ops, Field: messages.Field }}>
      <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-8 sm:py-10">
        <OpsNav
          label={t("label")}
          links={[
            { href: FIELD_VISITS_PATH, label: t("visits"), exact: true },
            { href: FIELD_STUDENT_VISITS_PATH, label: t("studentVisits") },
            { href: STAFF_HOME_PATH, label: t("staffHome"), exact: true },
          ]}
        />
        {children}
      </div>
    </NextIntlClientProvider>
  );
}
