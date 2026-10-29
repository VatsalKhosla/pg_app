import type { Metadata } from "next";
import Link from "next/link";
import { getFormatter, getTranslations } from "next-intl/server";

import { EndBandButton, RentBandForm } from "@/components/admin/rent-band-form";
import { unwrap } from "@/lib/api/client";
import { getSearchReference } from "@/lib/api/public";
import { getServerApi } from "@/lib/api/server";
import { ADMIN_RENT_BANDS_PATH } from "@/lib/auth/routes";
import { requireAdmin } from "@/lib/auth/session";
import { formatINR } from "@/lib/money";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Admin.bands");
  return { title: t("metaTitle") };
}

/**
 * Rent bands (step 4.1, ADR 0036; rule 6): the bands in force, newest first (ended ones too if
 * asked), ending one, and setting one. Admins only; the API checks again and audits each change.
 */
export default async function AdminRentBandsPage({ searchParams }: PageProps<"/admin/rent-bands">) {
  await requireAdmin(ADMIN_RENT_BANDS_PATH);
  const ended = (await searchParams).ended === "true";
  const api = await getServerApi();
  const [bands, reference, t, format] = await Promise.all([
    unwrap(api.GET("/v1/admin/rent-bands", { params: { query: { ended } } })),
    getSearchReference(),
    getTranslations("Admin.bands"),
    getFormatter(),
  ]);
  const when = (moment: string) => format.dateTime(new Date(moment), { dateStyle: "medium" });
  const tPolicies = await getTranslations("Admin.policies");

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <section aria-labelledby="bands-title" className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="bands-title" className="text-xl font-semibold">
            {t("title")}
          </h2>
          <Link
            href={ended ? ADMIN_RENT_BANDS_PATH : `${ADMIN_RENT_BANDS_PATH}?ended=true`}
            className="text-sm font-medium text-primary underline underline-offset-4"
          >
            {ended ? t("hideEnded") : t("showEnded")}
          </Link>
        </div>
        {bands.items.length === 0 ? (
          <p className="text-muted-foreground">{t("none")}</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {bands.items.map((band) => {
              const label = `${band.locality.name}, ${t(`occupancies.${band.occupancy}`)}`;
              return (
                <li key={band.id} className="flex flex-wrap items-start justify-between gap-3 p-4">
                  <div className="space-y-1">
                    <p className="font-semibold">{label}</p>
                    <p>
                      {t("range", {
                        min: formatINR(band.minRentPaise),
                        max: formatINR(band.maxRentPaise),
                      })}{" "}
                      · {t(band.source)}
                      {band.reference === "" ? null : ` · ${band.reference}`}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {t("since", { since: when(band.effectiveFrom) })}
                      {band.effectiveTo === null
                        ? null
                        : ` · ${t("until", { until: when(band.effectiveTo) })}`}
                      {" · "}
                      {t("by", {
                        by: band.changedBy?.name ?? tPolicies("someone"),
                      })}
                    </p>
                  </div>
                  {band.effectiveTo === null ? <EndBandButton id={band.id} label={label} /> : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section aria-labelledby="set-title" className="space-y-4 rounded-lg border p-5">
        <h2 id="set-title" className="text-xl font-semibold">
          {t("setTitle")}
        </h2>
        <RentBandForm
          localities={reference.localities.map((place) => ({ slug: place.slug, name: place.name }))}
        />
      </section>
    </div>
  );
}
