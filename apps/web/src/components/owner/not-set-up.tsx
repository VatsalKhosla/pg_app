import { getTranslations } from "next-intl/server";

import { brand } from "@/config/brand";

/** For an owner whose business ops haven't added yet: the API knows them, but not as a business. */
export async function NotSetUp() {
  const t = await getTranslations("Owner.notSetUp");
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
      <p className="text-muted-foreground">{t("body", { brand: brand.name })}</p>
    </div>
  );
}
