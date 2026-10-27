import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getPublicListing } from "@/lib/api/public";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/u;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Pg.visit");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

/** Where booking a visit will be (step 3.7); until then it says so, honestly. */
export default async function VisitPage({ params }: PageProps<"/pg/[slug]/visit">) {
  const { slug } = await params;
  if (!SLUG.test(slug) || slug.length > 80) notFound();
  const listing = await getPublicListing(slug);
  if (listing === null) notFound();
  const t = await getTranslations("Pg.visit");

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 px-4 py-10 sm:py-16">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
        {t("title", { name: listing.name })}
      </h1>
      <p className="text-muted-foreground">{t("soon")}</p>
      <Link
        href={`/pg/${slug}` as Route}
        className="inline-flex min-h-6 items-center text-sm font-medium text-primary underline underline-offset-4"
      >
        {t("back")}
      </Link>
    </div>
  );
}
