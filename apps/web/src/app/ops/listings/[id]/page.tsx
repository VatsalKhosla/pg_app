import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AmenitiesForm } from "@/components/ops/amenities-form";
import { DetailsForm } from "@/components/ops/details-form";
import { ListingHistory } from "@/components/ops/listing-history";
import { MediaManager } from "@/components/ops/media-manager";
import { RoomsEditor } from "@/components/ops/rooms-editor";
import { StatusPanel } from "@/components/ops/status-panel";
import { VerificationPanel } from "@/components/ops/verification-panel";
import { VisitList } from "@/components/ops/visit-list";
import { unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getServerApi } from "@/lib/api/server";
import { requireOps } from "@/lib/auth/session";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("Ops.editor");
  return { title: t("metaTitle") };
}

/** Listings pinned within 30 m of a new one, passed on from its creation. */
function duplicatesOf(value: string | string[] | undefined): string[] {
  if (typeof value !== "string") return [];
  return value
    .split(",")
    .filter((id) => UUID.test(id))
    .slice(0, 10);
}

async function load(id: string) {
  const api = await getServerApi();
  const path = { params: { path: { property_id: id } } };
  try {
    return await Promise.all([
      unwrap(api.GET("/v1/ops/properties/{property_id}", path)),
      unwrap(api.GET("/v1/ops/properties/{property_id}/history", path)),
      unwrap(api.GET("/v1/amenities")),
      unwrap(
        api.GET("/v1/ops/properties/{property_id}/verification-visits", {
          params: { ...path.params, query: { limit: 20 } },
        }),
      ),
      unwrap(api.GET("/v1/ops/field-agents")),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

/**
 * One listing in full, and everything ops do to it: status, verification, details, rooms and
 * their pricing (its own page), amenities, media, and its history.
 */
export default async function OpsListingPage({
  params,
  searchParams,
}: PageProps<"/ops/listings/[id]">) {
  const { id } = await params;
  await requireOps(`/ops/listings/${id}` as Route);
  if (!UUID.test(id)) notFound();
  const [listing, history, amenities, visits, agents] = await load(id);
  const duplicates = duplicatesOf((await searchParams).duplicates);
  const t = await getTranslations("Ops");

  const sections = [
    { key: "status", title: t("publish.title"), body: <StatusPanel listing={listing} /> },
    {
      key: "verification",
      title: t("visits.title"),
      body: (
        <div className="space-y-6">
          <p className="font-medium">{t(`verification.${listing.verificationStatus}`)}</p>
          <VerificationPanel listing={listing} agents={agents.items} />
          <VisitList visits={visits.items} />
        </div>
      ),
    },
    { key: "details", title: t("details.title"), body: <DetailsForm listing={listing} /> },
    { key: "rooms", title: t("rooms.title"), body: <RoomsEditor listing={listing} /> },
    {
      key: "pricing",
      title: t("pricing.section"),
      body: (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">{t("pricing.linkHint")}</p>
          <Link
            href={`/ops/listings/${id}/pricing` as Route}
            className="inline-flex min-h-6 items-center font-medium text-primary underline underline-offset-4"
          >
            {t("pricing.link")}
          </Link>
        </div>
      ),
    },
    {
      key: "amenities",
      title: t("amenities.title"),
      body: <AmenitiesForm listing={listing} amenities={amenities.items} />,
    },
    { key: "media", title: t("media.title"), body: <MediaManager listing={listing} /> },
    { key: "history", title: t("history.title"), body: <ListingHistory entries={history.items} /> },
  ];

  return (
    <div className="space-y-10">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{listing.name}</h1>
        <p className="text-muted-foreground">
          {[
            listing.locality.name,
            t(`status.${listing.status}`),
            t(`verification.${listing.verificationStatus}`),
          ].join(" · ")}
        </p>
        <p className="text-sm text-muted-foreground">
          {t.rich("editor.owner", {
            business: listing.owner.businessName,
            phone: listing.owner.phone ?? "",
            link: (business) => (
              <Link
                href={`/ops/owners/${listing.owner.id}` as Route}
                className="font-medium text-primary underline underline-offset-4"
              >
                {business}
              </Link>
            ),
          })}
        </p>
      </div>

      {duplicates.length === 0 ? null : (
        <div role="alert" className="space-y-2 rounded-md border border-destructive/40 p-4 text-sm">
          <p>{t("duplicates")}</p>
          <ul className="list-disc pl-5">
            {duplicates.map((other) => (
              <li key={other}>
                {/* At least 24 px tall: links stacked in a list are touch targets (WCAG 2.5.8). */}
                <Link
                  href={`/ops/listings/${other}` as Route}
                  className="inline-flex min-h-6 items-center font-medium text-primary underline underline-offset-4"
                >
                  {t("editor.duplicate", { id: other.slice(0, 8) })}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {sections.map((section) => (
        <section key={section.key} aria-labelledby={`${section.key}-title`} className="space-y-4">
          <h2 id={`${section.key}-title`} className="border-b pb-2 text-lg font-semibold">
            {section.title}
          </h2>
          {section.body}
        </section>
      ))}
    </div>
  );
}
