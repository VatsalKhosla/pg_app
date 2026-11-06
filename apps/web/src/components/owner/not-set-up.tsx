import { getTranslations } from "next-intl/server";

import { brand } from "@/config/brand";

/** For an owner whose business ops haven't added yet: the API knows them, but not as a business. */
export async function NotSetUp() {
  const t = await getTranslations("Owner.notSetUp");
  return (
    <div className="space-y-2 rounded-2xl border border-dashed border-border bg-surface/60 p-6">
      <h1 className="text-title-2 font-semibold tracking-tight text-foreground">{t("title")}</h1>
      <p className="text-body text-muted-foreground">{t("body", { brand: brand.name })}</p>
    </div>
  );
}
