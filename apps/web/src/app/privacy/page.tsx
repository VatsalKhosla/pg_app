import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Privacy");
  // A draft: kept out of search until the reviewed notice replaces it (step 3.8).
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/** A placeholder: the notice itself is legal text, written in step 3.8 and reviewed by a lawyer. */
export default async function PrivacyPage() {
  const t = await getTranslations("Privacy");
  const notice = await unwrap((await getServerApi()).GET("/v1/privacy-notice")).catch(() => null);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-10 sm:py-16">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
      <p
        role="note"
        className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm font-medium"
      >
        {t("draft")}
      </p>
      {notice === null ? null : (
        <p className="text-sm text-muted-foreground">{t("version", { version: notice.version })}</p>
      )}
      <section aria-labelledby="purposes-title" className="space-y-3">
        <h2 id="purposes-title" className="text-lg font-semibold">
          {t("purposes")}
        </h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>{t("account")}</li>
          <li>{t("marketing")}</li>
        </ul>
      </section>
      <p>{t("rights")}</p>
    </div>
  );
}
