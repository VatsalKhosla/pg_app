import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import type { CityChoice } from "@/components/ops/listing-fields";
import { NewListing } from "@/components/ops/new-listing";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OPS_NEW_LISTING_PATH } from "@/lib/auth/routes";
import { requireOps } from "@/lib/auth/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.new");
  return { title: t("title") };
}

export default async function NewListingPage() {
  await requireOps(OPS_NEW_LISTING_PATH);
  const api = await getServerApi();
  const [cities, localities] = await Promise.all([
    unwrap(api.GET("/v1/cities")),
    unwrap(api.GET("/v1/localities")),
  ]);
  // Localities by city, for the picker; their centres are where the map looks first.
  const choices: CityChoice[] = cities.items
    .map((city) => ({
      name: city.name,
      localities: localities.items
        .filter((locality) => locality.city === city.slug)
        .map(({ slug, name, center }) => ({ slug, name, center })),
    }))
    .filter((city) => city.localities.length > 0);
  const t = await getTranslations("Ops.new");

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <NewListing cities={choices} />
    </div>
  );
}
