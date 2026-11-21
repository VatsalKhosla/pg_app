import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ListingImport } from "@/components/ops/listing-import";
import { OPS_LISTING_IMPORT_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.import");
  return { title: t("title") };
}

/** Owners and their PGs from a file (ADR 0072): the template, then a check, then the import. */
export default async function ListingImportPage() {
  await requireOps(OPS_LISTING_IMPORT_PATH);
  const t = await getTranslations("Ops.import");
  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="font-display text-title-1 text-foreground">{t("title")}</h1>
        <p className="max-w-prose text-muted-foreground">{t("intro")}</p>
        <a
          href="/ops/listings/import/template"
          download
          className="inline-flex min-h-6 items-center text-sm font-semibold text-primary underline underline-offset-4"
        >
          {t("template")}
        </a>
      </div>
      <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-xs">
        <ListingImport />
      </div>
    </div>
  );
}
