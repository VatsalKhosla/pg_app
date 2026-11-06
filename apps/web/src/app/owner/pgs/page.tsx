import type { Metadata, Route } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { NotSetUp } from "@/components/owner/not-set-up";
import { unwrap } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { OWNER_PGS_PATH } from "@/lib/auth/routes";
import { requireOwner } from "@/lib/auth/session";
import { getOwnProfile } from "@/lib/owner/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Owner.pgs");
  return { title: t("metaTitle") };
}

/** The owner's PGs (step 7.1), each opening onto how it's doing and what runs it. */
export default async function OwnerPgsPage() {
  await requireOwner(OWNER_PGS_PATH);
  const owner = await getOwnProfile();
  if (owner === null) return <NotSetUp />;
  const api = await getServerApi();
  const { items } = await unwrap(api.GET("/v1/owner/properties"));
  const t = await getTranslations("Owner.pgs");

  return (
    <>
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {items.length === 0 ? (
        <p>{t("none")}</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {items.map((place) => (
            <li key={place.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <Link
                  href={`${OWNER_PGS_PATH}/${place.id}` as Route}
                  aria-label={t("open", { name: place.name })}
                  className="font-medium text-primary underline underline-offset-4"
                >
                  {place.name}
                </Link>
                <p className="text-sm text-muted-foreground">
                  {t("place", { locality: place.locality })}
                </p>
              </div>
              <span className="text-sm">{t(`status.${place.status}`)}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
